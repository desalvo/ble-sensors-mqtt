#!/usr/bin/env python3
"""Build deterministic deployment/source archives and SHA-256 files."""

from __future__ import annotations

import gzip
import hashlib
import os
import stat
import tarfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXCLUDED_PARTS = {".git", ".venv", "dist", "build", "release", "native-dist", "__pycache__", ".pytest_cache", ".ruff_cache"}


def epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return int(time.time())
    value = int(raw)
    if value < 315532800:  # ZIP cannot represent dates before 1980.
        return 315532800
    return value


def files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in rel.parts):
            continue
        rel_text = rel.as_posix()
        if rel_text in {"docker/.env", "docker/arguments"} or rel_text.startswith("docker/secrets/"):
            continue
        if path.is_file() and not path.is_symlink() and not path.name.endswith(".pyc"):
            result.append(path)
    return sorted(result, key=lambda item: item.relative_to(ROOT).as_posix())


def mode_for(path: Path) -> int:
    executable = bool(path.stat().st_mode & stat.S_IXUSR)
    return 0o755 if executable else 0o644


def build_tar(output: Path, timestamp: int, members: list[Path]) -> None:
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=timestamp) as gz,
        tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for path in members:
            rel = path.relative_to(ROOT).as_posix()
            info = tarfile.TarInfo(f"ble-sensors-mqtt/{rel}")
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = timestamp
            info.mode = mode_for(path)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            archive.addfile(info, __import__("io").BytesIO(data))


def build_zip(output: Path, timestamp: int, members: list[Path]) -> None:
    dt = datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
    zip_time = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in members:
            rel = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"ble-sensors-mqtt/{rel}", date_time=zip_time)
            info.create_system = 3
            info.external_attr = mode_for(path) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def checksum(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="ascii")


def main() -> None:
    timestamp = epoch()
    build_id = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d-%H%M")
    (ROOT / "BUILD").write_text(build_id + "\n", encoding="ascii")
    members = files()
    release_dir_raw = os.environ.get("RELEASE_DIR")
    release_dir = Path(release_dir_raw) if release_dir_raw else ROOT / "release"
    if not release_dir.is_absolute():
        release_dir = ROOT / release_dir
    release_dir.mkdir(parents=True, exist_ok=True)
    tar_path = release_dir / f"ble-sensors-mqtt-v{VERSION}-{build_id}.tar.gz"
    zip_path = release_dir / f"ble-sensors-mqtt-v{VERSION}-{build_id}.zip"
    build_tar(tar_path, timestamp, members)
    build_zip(zip_path, timestamp, members)
    checksum(tar_path)
    checksum(zip_path)
    print(tar_path)
    print(zip_path)


if __name__ == "__main__":
    main()
