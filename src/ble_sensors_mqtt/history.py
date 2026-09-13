"""Persistent sensor history for the optional web frontend."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _scalar_values(value: Any, prefix: str = "", limit: int = 256) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    stack: list[tuple[str, Any]] = [(prefix, value)]
    while stack and len(result) < limit:
        current_prefix, current = stack.pop()
        if isinstance(current, dict):
            for key, child in reversed(list(current.items())):
                if key == "units":
                    continue
                path = f"{current_prefix}.{key}" if current_prefix else str(key)
                if isinstance(child, (dict, list, tuple)):
                    stack.append((path, child))
                elif child is None or isinstance(child, (str, bool, int, float)):
                    if isinstance(child, float) and not math.isfinite(child):
                        continue
                    result.append((path, child))
        elif isinstance(current, (list, tuple)):
            for index, child in reversed(list(enumerate(current[:100]))):
                stack.append((f"{current_prefix}.{index}", child))
    return sorted(result)


class HistoryStore:
    def __init__(self, path: Path, retention_days: int = 30) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                manufacturer TEXT NOT NULL,
                model TEXT NOT NULL,
                protocol TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                observed_at TEXT,
                stale INTEGER NOT NULL,
                data_json TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_samples_sensor_time ON samples(sensor_id, recorded_at)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_samples_recorded_at ON samples(recorded_at)"
        )
        self._conn.commit()
        self.retention_days = 30
        self.set_retention_days(retention_days)
        self._last_purge = 0.0

    def set_retention_days(self, days: int) -> None:
        value = int(days)
        if value < 1 or value > 36500:
            raise ValueError("history retention days must be between 1 and 36500")
        self.retention_days = value

    def append_snapshot(self, devices: dict[str, dict[str, Any]]) -> None:
        recorded = _iso(_utc_now())
        rows = []
        for sensor_id, payload in devices.items():
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            rows.append(
                (
                    str(sensor_id),
                    str(payload.get("name") or sensor_id),
                    str(payload.get("manufacturer") or ""),
                    str(payload.get("model") or ""),
                    str(payload.get("protocol") or ""),
                    recorded,
                    str(payload.get("observed_at") or "") or None,
                    1 if payload.get("stale") else 0,
                    json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                )
            )
        if not rows:
            self.purge_expired()
            return
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO samples(
                    sensor_id,name,manufacturer,model,protocol,recorded_at,observed_at,stale,data_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )
            self._conn.commit()
        self.purge_expired()

    def purge_expired(self, *, force: bool = False) -> int:
        now = time.monotonic()
        if not force and now - self._last_purge < 3600:
            return 0
        threshold = _iso(_utc_now() - timedelta(days=self.retention_days))
        with self._lock:
            cur = self._conn.execute("DELETE FROM samples WHERE recorded_at < ?", (threshold,))
            self._conn.commit()
        self._last_purge = now
        return int(cur.rowcount if cur.rowcount is not None else 0)

    def sensors(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT s.sensor_id,s.name,s.manufacturer,s.model,s.protocol,
                       MAX(s.recorded_at) AS last_recorded_at, COUNT(*) AS samples
                FROM samples AS s
                GROUP BY s.sensor_id
                ORDER BY lower(s.name), s.sensor_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def query(
        self,
        sensor_ids: list[str],
        start: str | None = None,
        end: str | None = None,
        *,
        deduplicate: bool = True,
        limit: int = 20000,
    ) -> list[dict[str, Any]]:
        if not sensor_ids:
            return []
        bounded_limit = max(1, min(int(limit), 100000))
        rows: list[sqlite3.Row] = []
        with self._lock:
            for sensor_id in sensor_ids:
                if start and end:
                    selected = self._conn.execute(
                        """
                        SELECT sensor_id,name,manufacturer,model,protocol,recorded_at,
                               observed_at,stale,data_json
                        FROM samples
                        WHERE sensor_id = ? AND recorded_at >= ? AND recorded_at <= ?
                        ORDER BY recorded_at
                        LIMIT ?
                        """,
                        (sensor_id, start, end, bounded_limit),
                    ).fetchall()
                elif start:
                    selected = self._conn.execute(
                        """
                        SELECT sensor_id,name,manufacturer,model,protocol,recorded_at,
                               observed_at,stale,data_json
                        FROM samples
                        WHERE sensor_id = ? AND recorded_at >= ?
                        ORDER BY recorded_at
                        LIMIT ?
                        """,
                        (sensor_id, start, bounded_limit),
                    ).fetchall()
                elif end:
                    selected = self._conn.execute(
                        """
                        SELECT sensor_id,name,manufacturer,model,protocol,recorded_at,
                               observed_at,stale,data_json
                        FROM samples
                        WHERE sensor_id = ? AND recorded_at <= ?
                        ORDER BY recorded_at
                        LIMIT ?
                        """,
                        (sensor_id, end, bounded_limit),
                    ).fetchall()
                else:
                    selected = self._conn.execute(
                        """
                        SELECT sensor_id,name,manufacturer,model,protocol,recorded_at,
                               observed_at,stale,data_json
                        FROM samples
                        WHERE sensor_id = ?
                        ORDER BY recorded_at
                        LIMIT ?
                        """,
                        (sensor_id, bounded_limit),
                    ).fetchall()
                rows.extend(selected)

        rows.sort(key=lambda row: (str(row["sensor_id"]), str(row["recorded_at"])))
        rows = rows[:bounded_limit]
        result: list[dict[str, Any]] = []
        previous: dict[str, tuple[str, int]] = {}
        for row in rows:
            sensor_id = str(row["sensor_id"])
            key = (str(row["data_json"]), int(row["stale"]))
            if deduplicate and previous.get(sensor_id) == key:
                continue
            previous[sensor_id] = key
            data = json.loads(row["data_json"])
            result.append(
                {
                    "sensor_id": sensor_id,
                    "name": row["name"],
                    "manufacturer": row["manufacturer"],
                    "model": row["model"],
                    "protocol": row["protocol"],
                    "recorded_at": row["recorded_at"],
                    "observed_at": row["observed_at"],
                    "stale": bool(row["stale"]),
                    "data": data,
                    "values": [{"path": path, "value": value} for path, value in _scalar_values(data)],
                }
            )
        return result

    def delete(self, sensor_ids: list[str], start: str | None = None, end: str | None = None) -> int:
        if not sensor_ids:
            return 0
        deleted = 0
        with self._lock:
            for sensor_id in sensor_ids:
                if start and end:
                    cur = self._conn.execute(
                        "DELETE FROM samples WHERE sensor_id = ? AND recorded_at >= ? AND recorded_at <= ?",
                        (sensor_id, start, end),
                    )
                elif start:
                    cur = self._conn.execute(
                        "DELETE FROM samples WHERE sensor_id = ? AND recorded_at >= ?",
                        (sensor_id, start),
                    )
                elif end:
                    cur = self._conn.execute(
                        "DELETE FROM samples WHERE sensor_id = ? AND recorded_at <= ?",
                        (sensor_id, end),
                    )
                else:
                    cur = self._conn.execute(
                        "DELETE FROM samples WHERE sensor_id = ?",
                        (sensor_id,),
                    )
                deleted += int(cur.rowcount if cur.rowcount is not None else 0)
            self._conn.commit()
        return deleted

    def snapshot_to(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            destination = sqlite3.connect(target)
            try:
                self._conn.backup(destination)
            finally:
                destination.close()
        if os.name == "posix":
            os.chmod(target, 0o600)

    def restore_from(self, source: Path) -> None:
        with self._lock:
            incoming = sqlite3.connect(source)
            try:
                incoming.backup(self._conn)
                self._conn.commit()
            finally:
                incoming.close()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
