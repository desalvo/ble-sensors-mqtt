#!/usr/bin/env python3
"""Exec ble-sensors-mqtt using a root-owned JSON argument vector."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_arguments(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("systemd argument file must contain a JSON array of strings")
    if any("\x00" in item for item in data):
        raise ValueError("systemd argument file contains a NUL byte")
    return data


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} ARGUMENTS.json", file=sys.stderr)
        return 2

    args = load_arguments(Path(sys.argv[1]))
    executable = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "ble-sensors-mqtt"
    if not executable.is_file():
        print(f"ble-sensors-mqtt executable not found: {executable}", file=sys.stderr)
        return 2

    os.execv(str(executable), [str(executable), *args])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
