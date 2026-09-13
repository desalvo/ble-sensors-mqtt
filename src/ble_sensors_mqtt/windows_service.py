"""Windows Service wrapper for the frozen ble-sensors-mqtt runtime."""

from __future__ import annotations

import os
import subprocess  # nosec B404 - launches only the fixed installed gateway executable
import sys
from pathlib import Path

if sys.platform == "win32":
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
else:  # pragma: no cover - Windows-only module
    servicemanager = win32event = win32service = win32serviceutil = None

SERVICE_NAME = "ble-sensors-mqtt"
DISPLAY_NAME = "ble-sensors-mqtt sensor gateway"
DESCRIPTION = "BLE/cloud sensor gateway publishing MQTT, Prometheus and SNMP data"


def _runtime() -> Path:
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    return program_files / SERVICE_NAME / "runtime" / f"{SERVICE_NAME}.exe"


def _config() -> Path:
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / SERVICE_NAME / "config.toml"


if sys.platform == "win32":
    class BleSensorsMqttService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = DISPLAY_NAME
        _svc_description_ = DESCRIPTION

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.process: subprocess.Popen[bytes] | None = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)
            if self.process and self.process.poll() is None:
                self.process.terminate()

        def SvcDoRun(self):
            servicemanager.LogInfoMsg(f"Starting {DISPLAY_NAME}")
            command = [str(_runtime()), "--config", str(_config())]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(  # nosec B603 - command is a fixed installed executable/config path
                command, creationflags=creationflags
            )
            while True:
                if win32event.WaitForSingleObject(self.stop_event, 500) == win32event.WAIT_OBJECT_0:
                    break
                code = self.process.poll()
                if code is not None:
                    servicemanager.LogErrorMsg(
                        f"{SERVICE_NAME} exited unexpectedly with code {code}"
                    )
                    break
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            servicemanager.LogInfoMsg(f"Stopped {DISPLAY_NAME}")


def service_main() -> int:
    if sys.platform != "win32":
        raise SystemExit("Windows service wrapper is only available on Windows")
    if len(sys.argv) > 1:
        win32serviceutil.HandleCommandLine(BleSensorsMqttService)
        return 0
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(BleSensorsMqttService)
    servicemanager.StartServiceCtrlDispatcher()
    return 0


if __name__ == "__main__":
    raise SystemExit(service_main())
