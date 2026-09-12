"""Version helpers with a source-tree fallback."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def get_version() -> str:
    try:
        return version("ble-sensors-mqtt")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[2] / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "0+unknown"


__version__ = get_version()
