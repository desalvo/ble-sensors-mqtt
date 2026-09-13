"""Bounded transactional on-disk spool for MQTT messages."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class CachedMessage:
    id: int
    topic: str
    payload: bytes
    qos: int
    retain: bool
    size: int
    created_at: str


class MQTTCache:
    """SQLite-backed FIFO cache with a bounded logical payload size."""

    def __init__(self, path: Path, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("MQTT cache maximum size must be positive")
        if path.exists() and path.is_symlink():
            raise ValueError("MQTT cache path must not be a symlink")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        self.max_bytes = max_bytes
        self._db = sqlite3.connect(path, timeout=10)
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA temp_store=MEMORY")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload BLOB NOT NULL,
                qos INTEGER NOT NULL,
                retain INTEGER NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_messages_id ON messages(id)")
        self._db.commit()
        os.chmod(path, 0o600)

    @staticmethod
    def message_size(topic: str, payload: bytes) -> int:
        return len(topic.encode("utf-8")) + len(payload) + 64

    def stats(self) -> tuple[int, int]:
        row = self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM messages"
        ).fetchone()
        assert row is not None
        return int(row[0]), int(row[1])

    def enqueue(self, topic: str, payload: bytes, qos: int, retain: bool) -> tuple[int, int]:
        size = self.message_size(topic, payload)
        if size > self.max_bytes:
            raise ValueError(
                f"MQTT message requires {size} bytes, larger than cache limit {self.max_bytes}"
            )
        dropped = 0
        dropped_bytes = 0
        with self._db:
            _count, used = self.stats()
            while used + size > self.max_bytes:
                row = self._db.execute(
                    "SELECT id, size FROM messages ORDER BY id LIMIT 1"
                ).fetchone()
                if row is None:
                    break
                self._db.execute("DELETE FROM messages WHERE id = ?", (int(row[0]),))
                dropped += 1
                dropped_bytes += int(row[1])
                used -= int(row[1])
            self._db.execute(
                "INSERT INTO messages(topic, payload, qos, retain, size, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    topic,
                    sqlite3.Binary(payload),
                    int(qos),
                    1 if retain else 0,
                    size,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return dropped, dropped_bytes

    def oldest(self, limit: int = 256) -> list[CachedMessage]:
        rows = self._db.execute(
            "SELECT id, topic, payload, qos, retain, size, created_at "
            "FROM messages ORDER BY id LIMIT ?",
            (max(1, min(limit, 10_000)),),
        ).fetchall()
        return [
            CachedMessage(
                id=int(row[0]),
                topic=str(row[1]),
                payload=bytes(row[2]),
                qos=int(row[3]),
                retain=bool(row[4]),
                size=int(row[5]),
                created_at=str(row[6]),
            )
            for row in rows
        ]

    def delete(self, message_id: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM messages WHERE id = ?", (message_id,))


    def snapshot_to(self, target: Path) -> None:
        """Create a transactionally consistent SQLite snapshot for backup/export."""
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(target)
        try:
            self._db.backup(destination)
            destination.commit()
        finally:
            destination.close()

    def restore_from(self, source: Path) -> None:
        """Replace the queue from a validated SQLite cache while keeping this connection alive."""
        incoming = sqlite3.connect(source)
        try:
            rows = incoming.execute(
                "SELECT topic,payload,qos,retain,size,created_at FROM messages ORDER BY id"
            ).fetchall()
        finally:
            incoming.close()
        with self._db:
            self._db.execute("DELETE FROM messages")
            for topic, payload, qos, retain, size, created_at in rows:
                if int(size) > self.max_bytes:
                    continue
                self._db.execute(
                    "INSERT INTO messages(topic,payload,qos,retain,size,created_at) VALUES(?,?,?,?,?,?)",
                    (str(topic), sqlite3.Binary(bytes(payload)), int(qos), int(bool(retain)), int(size), str(created_at)),
                )
            # Enforce the current instance limit by dropping oldest rows.
            _count, used = self.stats()
            while used > self.max_bytes:
                row = self._db.execute("SELECT id,size FROM messages ORDER BY id LIMIT 1").fetchone()
                if row is None:
                    break
                self._db.execute("DELETE FROM messages WHERE id=?", (int(row[0]),))
                used -= int(row[1])

    def close(self) -> None:
        self._db.close()
