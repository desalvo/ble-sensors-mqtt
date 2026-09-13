"""Encrypted full-configuration backup/import for the optional web frontend."""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

MAGIC = b"BSMQBK1\0"


def _derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode("utf-8"))


def _encrypt_file(source: Path, target: Path, password: str) -> None:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    salt, nonce = os.urandom(16), os.urandom(12)
    encryptor = Cipher(algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce)).encryptor()
    with source.open("rb") as src, target.open("wb") as dst:
        dst.write(MAGIC + salt + nonce)
        while chunk := src.read(1024 * 1024):
            dst.write(encryptor.update(chunk))
        dst.write(encryptor.finalize())
        dst.write(encryptor.tag)


def _decrypt_file(source: Path, target: Path, password: str) -> None:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    size = source.stat().st_size
    with source.open("rb") as src:
        if src.read(len(MAGIC)) != MAGIC:
            raise ValueError("not a ble-sensors-mqtt backup")
        salt, nonce = src.read(16), src.read(12)
        src.seek(-16, 2)
        tag = src.read(16)
        ciphertext_end = size - 16
        src.seek(len(MAGIC) + 16 + 12)
        decryptor = Cipher(algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce, tag)).decryptor()
        with target.open("wb") as dst:
            remaining = ciphertext_end - src.tell()
            while remaining > 0:
                chunk = src.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                dst.write(decryptor.update(chunk))
            dst.write(decryptor.finalize())


def create_backup(target: Path, password: str, *, config_path: Path, users: list[dict[str, Any]], files: dict[str, Path | None], references: dict[str, Path] | None = None) -> Path:
    if len(password) < 10:
        raise ValueError("backup password must contain at least 10 characters")
    with tempfile.TemporaryDirectory(prefix="ble-sensors-backup-") as temp:
        archive = Path(temp) / "backup.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            zf.writestr("manifest.json", json.dumps({"format": 1, "application": "ble-sensors-mqtt"}, indent=2))
            zf.writestr("users.json", json.dumps(users, indent=2, ensure_ascii=False))
            if config_path.exists():
                zf.write(config_path, "config/config.toml")
            for name, path in files.items():
                if path and path.exists() and path.is_file() and not path.is_symlink():
                    zf.write(path, f"files/{name}")
            reference_manifest: dict[str, str] = {}
            for index, (logical_name, path) in enumerate((references or {}).items()):
                if path.exists() and path.is_file() and not path.is_symlink():
                    archive_name = f"references/{index:03d}-{path.name}"
                    zf.write(path, archive_name)
                    reference_manifest[logical_name] = archive_name
            zf.writestr("references.json", json.dumps(reference_manifest, indent=2, ensure_ascii=False))
        target.parent.mkdir(parents=True, exist_ok=True)
        _encrypt_file(archive, target, password)
    return target


def extract_backup(source: Path, password: str, destination: Path) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "backup.zip"
    _decrypt_file(source, archive, password)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            resolved = (destination / info.filename).resolve()
            if destination.resolve() not in resolved.parents and resolved != destination.resolve():
                raise ValueError("unsafe path in backup")
        zf.extractall(destination)
    archive.unlink(missing_ok=True)
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("application") != "ble-sensors-mqtt":
        raise ValueError("backup is for another application")
    return manifest
