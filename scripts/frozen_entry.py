#!/usr/bin/env python3
"""PyInstaller entry point for native Windows/macOS bundles."""

import sys

# Bleak's WinRT backend needs an MTA in non-GUI processes. This also prevents a
# later pywin32/pythoncom import from implicitly forcing the daemon into STA.
if sys.platform == "win32":
    sys.coinit_flags = 0

from ble_sensors_mqtt.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
