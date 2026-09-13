"""Authentication, roles and portable TOTP MFA for the optional web frontend."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
import struct
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PBKDF2_ROUNDS = 310_000


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS, dklen=32)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, digest = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        raw_salt = base64.urlsafe_b64decode(salt)
        expected = base64.urlsafe_b64decode(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), raw_salt, int(rounds), dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def generate_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp(secret: str, *, now: int | None = None, step: int = 30, digits: int = 6) -> str:
    counter = (int(time.time()) if now is None else now) // step
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()  # noqa: S324 - TOTP standard
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return f"{value:0{digits}d}"


def verify_totp(secret: str, code: str, *, window: int = 1) -> bool:
    candidate = "".join(ch for ch in str(code) if ch.isdigit())
    if len(candidate) != 6:
        return False
    now = int(time.time())
    return any(hmac.compare_digest(totp(secret, now=now + offset * 30), candidate) for offset in range(-window, window + 1))


def otpauth_uri(secret: str, username: str, issuer: str = "ble-sensors-mqtt") -> str:
    label = urllib.parse.quote(f"{issuer}:{username}")
    query = urllib.parse.urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": 6, "period": 30})
    return f"otpauth://totp/{label}?{query}"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    auth_source: str
    active: bool
    must_change_password: bool
    mfa_enabled: bool
    mfa_secret: str | None
    email: str | None


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE COLLATE NOCASE,
              password_hash TEXT,
              role TEXT NOT NULL CHECK(role IN ('admin','reader')),
              auth_source TEXT NOT NULL CHECK(auth_source IN ('local','ldap','oidc')),
              active INTEGER NOT NULL DEFAULT 1,
              must_change_password INTEGER NOT NULL DEFAULT 0,
              mfa_enabled INTEGER NOT NULL DEFAULT 0,
              mfa_secret TEXT,
              email TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              username TEXT,
              action TEXT NOT NULL,
              detail TEXT
            );
            """
        )
        self.db.commit()
        if not self.db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            self.create_user("admin", "admin", auth_source="local", password="password", must_change=True)

    def close(self) -> None:
        self.db.close()

    def audit(self, username: str | None, action: str, detail: str = "") -> None:
        self.db.execute("INSERT INTO audit(username, action, detail) VALUES(?,?,?)", (username, action, detail[:1000]))
        self.db.commit()

    def _user(self, row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(row["id"], row["username"], row["role"], row["auth_source"], bool(row["active"]), bool(row["must_change_password"]), bool(row["mfa_enabled"]), row["mfa_secret"], row["email"])

    def get(self, username: str) -> User | None:
        return self._user(self.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone())

    def list_users(self) -> list[User]:
        return [self._user(row) for row in self.db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()]  # type: ignore[list-item]

    def authenticate_local(self, username: str, password: str) -> User | None:
        row = self.db.execute("SELECT * FROM users WHERE username=? AND auth_source='local'", (username,)).fetchone()
        if row is None or not row["active"] or not row["password_hash"] or not verify_password(password, row["password_hash"]):
            return None
        return self._user(row)

    def create_user(self, username: str, role: str, *, auth_source: str = "local", password: str | None = None, must_change: bool = False, email: str | None = None) -> User:
        username = username.strip()
        if not username or role not in {"admin", "reader"} or auth_source not in {"local", "ldap", "oidc"}:
            raise ValueError("invalid user")
        if auth_source == "local" and not password:
            raise ValueError("local users require a password")
        password_hash = _password_hash(password) if password else None
        self.db.execute(
            "INSERT INTO users(username,password_hash,role,auth_source,must_change_password,email) VALUES(?,?,?,?,?,?)",
            (username, password_hash, role, auth_source, int(must_change), email),
        )
        self.db.commit()
        return self.get(username)  # type: ignore[return-value]

    def upsert_external(self, username: str, source: str, *, default_role: str = "reader", email: str | None = None) -> User:
        existing = self.get(username)
        if existing:
            if existing.auth_source != source:
                raise ValueError(
                    f"username {username!r} is already owned by {existing.auth_source} authentication"
                )
            return existing
        return self.create_user(username, default_role, auth_source=source, email=email)

    def update_user(self, username: str, *, role: str | None = None, active: bool | None = None) -> None:
        if role is not None:
            if role not in {"admin", "reader"}:
                raise ValueError("invalid role")
            self.db.execute("UPDATE users SET role=?, updated_at=CURRENT_TIMESTAMP WHERE username=?", (role, username))
        if active is not None:
            self.db.execute("UPDATE users SET active=?, updated_at=CURRENT_TIMESTAMP WHERE username=?", (int(active), username))
        self.db.commit()

    def set_password(self, username: str, password: str, *, must_change: bool = False) -> None:
        if len(password) < 8:
            raise ValueError("password must contain at least 8 characters")
        self.db.execute("UPDATE users SET password_hash=?, must_change_password=?, updated_at=CURRENT_TIMESTAMP WHERE username=? AND auth_source='local'", (_password_hash(password), int(must_change), username))
        self.db.commit()

    def ensure_mfa_secret(self, username: str) -> str:
        user = self.get(username)
        if not user:
            raise KeyError(username)
        secret = user.mfa_secret or generate_totp_secret()
        self.db.execute("UPDATE users SET mfa_secret=?, updated_at=CURRENT_TIMESTAMP WHERE username=?", (secret, username))
        self.db.commit()
        return secret

    def set_mfa(self, username: str, enabled: bool, *, secret: str | None = None) -> None:
        if enabled:
            secret = secret or self.ensure_mfa_secret(username)
        self.db.execute("UPDATE users SET mfa_enabled=?, mfa_secret=?, updated_at=CURRENT_TIMESTAMP WHERE username=?", (int(enabled), secret if enabled else None, username))
        self.db.commit()

    def delete_user(self, username: str) -> None:
        if username.lower() == "admin":
            raise ValueError("the bootstrap admin cannot be deleted")
        self.db.execute("DELETE FROM users WHERE username=?", (username,))
        self.db.commit()

    def export_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT * FROM users ORDER BY id")]

    def import_rows(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            username = str(row.get("username", "")).strip()
            if not username:
                continue
            self.db.execute(
                """INSERT INTO users(username,password_hash,role,auth_source,active,must_change_password,mfa_enabled,mfa_secret,email)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash, role=excluded.role, auth_source=excluded.auth_source,
                active=excluded.active, must_change_password=excluded.must_change_password,
                mfa_enabled=excluded.mfa_enabled, mfa_secret=excluded.mfa_secret, email=excluded.email,
                updated_at=CURRENT_TIMESTAMP""",
                (username, row.get("password_hash"), row.get("role", "reader"), row.get("auth_source", "local"), int(bool(row.get("active", 1))), int(bool(row.get("must_change_password", 0))), int(bool(row.get("mfa_enabled", 0))), row.get("mfa_secret"), row.get("email")),
            )
        self.db.commit()
