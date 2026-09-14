"""Native graphical configuration utility for ble-sensors-mqtt."""

from __future__ import annotations

import ctypes
import os
import plistlib
import subprocess  # nosec B404 - fixed local OS service-management commands only
import sys
import tempfile
from pathlib import Path
from typing import Any

from .config import atomic_write_config, default_config, default_config_path, load_config

APP = "ble-sensors-mqtt"
WINDOWS_SERVICE = "ble-sensors-mqtt"
MAC_LABEL = "com.desalvo.ble-sensors-mqtt"

WINDOWS_SC = str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "sc.exe")
MAC_LAUNCHCTL = "/bin/launchctl"
MAC_OPEN = "/usr/bin/open"
LINUX_SYSTEMCTL = "/usr/bin/systemctl"
LINUX_XDG_OPEN = "/usr/bin/xdg-open"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = {key: (dict(value) if isinstance(value, dict) else value) for key, value in base.items()}
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def daemon_executable() -> Path:
    override = os.environ.get("BLE_SENSORS_MQTT_EXECUTABLE")
    if override:
        return Path(override)
    if os.name == "nt":
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        candidate = program_files / APP / "runtime" / f"{APP}.exe"
        if candidate.exists():
            return candidate
    if sys.platform == "darwin":
        candidate = Path("/Library/Application Support") / APP / "runtime" / APP
        if candidate.exists():
            return candidate
    # Development / portable fallback.
    sibling = Path(sys.executable).resolve().with_name(f"{APP}.exe" if os.name == "nt" else APP)
    return sibling if sibling.exists() else Path(APP)


def _windows_service(action: str) -> subprocess.CompletedProcess[str]:
    mapping = {"start": "start", "stop": "stop", "restart": None, "status": "query"}
    if action == "restart":
        subprocess.run([WINDOWS_SC, "stop", WINDOWS_SERVICE], capture_output=True, text=True)  # nosec B603
        return subprocess.run([WINDOWS_SC, "start", WINDOWS_SERVICE], capture_output=True, text=True)  # nosec B603
    return subprocess.run(  # nosec B603
        [WINDOWS_SC, mapping[action], WINDOWS_SERVICE], capture_output=True, text=True
    )


def _mac_agent_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def _mac_write_agent() -> Path:
    plist = _mac_agent_plist()
    plist.parent.mkdir(parents=True, exist_ok=True)
    config_path = default_config_path()
    logs = Path.home() / "Library" / "Logs" / APP
    logs.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": MAC_LABEL,
        "ProgramArguments": [str(daemon_executable()), "--config", str(config_path)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    with plist.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=True)
    return plist


def _mac_service(action: str) -> subprocess.CompletedProcess[str]:
    uid = os.getuid()
    domain = f"gui/{uid}"
    target = f"{domain}/{MAC_LABEL}"
    plist = _mac_agent_plist()
    if action == "start":
        plist = _mac_write_agent()
        subprocess.run([MAC_LAUNCHCTL, "bootout", target], capture_output=True, text=True)  # nosec B603
        return subprocess.run([MAC_LAUNCHCTL, "bootstrap", domain, str(plist)], capture_output=True, text=True)  # nosec B603
    if action == "stop":
        return subprocess.run([MAC_LAUNCHCTL, "bootout", target], capture_output=True, text=True)  # nosec B603
    if action == "restart":
        if not plist.exists():
            _mac_write_agent()
            subprocess.run([MAC_LAUNCHCTL, "bootstrap", domain, str(plist)], capture_output=True, text=True)  # nosec B603
        return subprocess.run([MAC_LAUNCHCTL, "kickstart", "-k", target], capture_output=True, text=True)  # nosec B603
    return subprocess.run([MAC_LAUNCHCTL, "print", target], capture_output=True, text=True)  # nosec B603


def service_action(action: str) -> tuple[bool, str]:
    try:
        if os.name == "nt":
            result = _windows_service(action)
        elif sys.platform == "darwin":
            result = _mac_service(action)
        else:
            result = subprocess.run(  # nosec B603
                [LINUX_SYSTEMCTL, action if action != "status" else "status", APP],
                capture_output=True,
                text=True,
            )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except OSError as exc:
        return False, str(exc)


def _is_windows_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def _windows_elevate(args: list[str]) -> None:
    params = subprocess.list2cmdline(args)
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    if int(result) <= 32:
        raise OSError(f"UAC elevation failed: ShellExecuteW={result}")


def _windows_elevate_apply(temp_path: Path, restart: bool) -> None:
    args = ["--apply-elevated", str(temp_path)]
    if restart:
        args.append("--restart-service")
    _windows_elevate(args)


def apply_elevated(source: Path, *, restart: bool) -> int:
    config = load_config(source, required=True)
    atomic_write_config(default_config_path(), config)
    if restart:
        ok, text = service_action("restart")
        if not ok:
            print(text, file=sys.stderr)
            return 2
    return 0


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.replace(",", "\n").splitlines() if line.strip()]


def run_gui() -> int:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    path = default_config_path()
    try:
        loaded = load_config(path)
    except Exception as exc:
        messagebox.showerror(APP, f"Cannot load {path}:\n{exc}")
        loaded = {}
    config = _deep_merge(default_config(), loaded)

    root = tk.Tk()
    root.title(f"{APP} Settings")
    root.geometry("820x690")
    root.minsize(760, 600)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=(12, 6))

    vars_: dict[str, tk.Variable] = {}
    entries: dict[str, tk.Widget] = {}

    def section(name: str) -> dict[str, Any]:
        return config.setdefault(name, {})

    def add_entry(parent: tk.Widget, row: int, key: str, label: str, value: Any, width: int = 48) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
        var = tk.StringVar(value="" if value is None else str(value))
        vars_[key] = var
        widget = ttk.Entry(parent, textvariable=var, width=width)
        widget.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        entries[key] = widget

    def add_bool(parent: tk.Widget, row: int, key: str, label: str, value: Any) -> None:
        var = tk.BooleanVar(value=bool(value))
        vars_[key] = var
        ttk.Checkbutton(parent, text=label, variable=var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=8, pady=5
        )

    general = ttk.Frame(notebook)
    general.columnconfigure(1, weight=1)
    notebook.add(general, text="General")
    add_entry(general, 0, "bluetooth.poll_interval", "Polling interval (s)", section("bluetooth").get("poll_interval", 30))
    add_entry(general, 1, "bluetooth.scan_duration", "BLE scan duration (s)", section("bluetooth").get("scan_duration", 8))
    add_entry(general, 2, "bluetooth.plugin_timeout", "Plugin timeout (s)", section("bluetooth").get("plugin_timeout", 15))
    add_bool(general, 3, "runtime.reuse_stale_data", "Reuse previous data while a sensor is temporarily missing", section("runtime").get("reuse_stale_data", False))
    add_entry(general, 4, "runtime.sensor_retry_attempts", "BLE acquisition attempts per polling cycle", section("runtime").get("sensor_retry_attempts", 10))
    add_entry(general, 5, "runtime.sensor_stale_cycles", "Missing cycles before a reused reading becomes stale", section("runtime").get("sensor_stale_cycles", 10))
    add_entry(general, 6, "runtime.log_level", "Log level", section("runtime").get("log_level", "INFO"))
    add_entry(general, 7, "runtime.state_file", "Runtime state file (optional)", section("runtime").get("state_file", ""))
    ttk.Label(general, text=f"Configuration file: {path}", wraplength=700).grid(row=8, column=0, columnspan=2, sticky="w", padx=8, pady=12)

    mqtt = ttk.Frame(notebook)
    mqtt.columnconfigure(1, weight=1)
    notebook.add(mqtt, text="MQTT")
    mq = section("mqtt")
    add_entry(mqtt, 0, "mqtt.host", "Broker host", mq.get("host", ""))
    add_entry(mqtt, 1, "mqtt.port", "Broker port", mq.get("port", 1883))
    add_entry(mqtt, 2, "mqtt.username", "Username", mq.get("username", ""))
    add_entry(mqtt, 3, "mqtt.password_file", "Password file", mq.get("password_file", ""))
    add_bool(mqtt, 4, "mqtt.tls", "Use verified MQTT TLS", mq.get("tls", False))
    add_entry(mqtt, 5, "mqtt.ca_file", "CA file (optional)", mq.get("ca_file", ""))
    add_bool(mqtt, 6, "mqtt.allow_insecure", "Allow plaintext MQTT explicitly", mq.get("allow_insecure", False))
    add_entry(mqtt, 7, "mqtt.topic_prefix", "Topic prefix", mq.get("topic_prefix", "ble-sensors"))
    add_bool(mqtt, 8, "mqtt.home_assistant_discovery", "Enable Home Assistant MQTT Discovery", mq.get("home_assistant_discovery", False))
    add_entry(mqtt, 9, "mqtt.home_assistant_discovery_prefix", "HA discovery prefix", mq.get("home_assistant_discovery_prefix", "homeassistant"))

    cache_tab = ttk.Frame(notebook)
    cache_tab.columnconfigure(1, weight=1)
    notebook.add(cache_tab, text="Cache")
    mc = section("mqtt_cache")
    add_bool(cache_tab, 0, "mqtt_cache.enabled", "Enable persistent MQTT disk cache", mc.get("enabled", True))
    add_entry(cache_tab, 1, "mqtt_cache.path", "SQLite cache path (optional)", mc.get("path", ""))
    add_entry(cache_tab, 2, "mqtt_cache.max_size", "Maximum cache size (bytes or e.g. 1GiB)", mc.get("max_size", 1024**3))

    monitor = ttk.Frame(notebook)
    monitor.columnconfigure(1, weight=1)
    notebook.add(monitor, text="Monitoring")
    pr = section("prometheus")
    sn = section("snmp")
    add_bool(monitor, 0, "prometheus.enabled", "Enable Prometheus / health HTTP endpoint", pr.get("enabled", False))
    add_entry(monitor, 1, "prometheus.host", "Prometheus bind address", pr.get("host", "127.0.0.1"))
    add_entry(monitor, 2, "prometheus.port", "Prometheus port", pr.get("port", 9105))
    add_bool(monitor, 3, "prometheus.allow_external", "Allow external Prometheus binding", pr.get("allow_external", False))
    ttk.Separator(monitor).grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
    add_bool(monitor, 5, "snmp.enabled", "Enable read-only SNMPv2c", sn.get("enabled", False))
    add_entry(monitor, 6, "snmp.host", "SNMP bind address", sn.get("host", "127.0.0.1"))
    add_entry(monitor, 7, "snmp.port", "SNMP UDP port", sn.get("port", 1161))
    add_entry(monitor, 8, "snmp.community_file", "SNMP community file", sn.get("community_file", ""))
    add_entry(monitor, 9, "snmp.base_oid", "SNMP base OID", sn.get("base_oid", "1.3.6.1.4.1.32473.1.1"))
    add_bool(monitor, 10, "snmp.allow_external", "Allow external plaintext SNMP binding", sn.get("allow_external", False))

    bluetooth = ttk.Frame(notebook)
    bluetooth.columnconfigure(1, weight=1)
    notebook.add(bluetooth, text="Bluetooth & sensors")
    bt = section("bluetooth")
    add_entry(bluetooth, 0, "bluetooth.adapter", "Linux adapter (e.g. hci1; blank = default)", bt.get("adapter", ""))
    add_entry(bluetooth, 1, "bluetooth.plugins", "Plugins (comma separated; blank = all installed)", ", ".join(bt.get("plugins", [])))
    ttk.Label(bluetooth, text="Allowed sensor IDs, one per line").grid(row=2, column=0, sticky="nw", padx=8, pady=5)
    devices = scrolledtext.ScrolledText(bluetooth, height=5, width=50)
    devices.insert("1.0", "\n".join(bt.get("devices", [])))
    devices.grid(row=2, column=1, sticky="nsew", padx=8, pady=5)
    entries["bluetooth.devices"] = devices
    ttk.Label(bluetooth, text="BLE aliases MAC=Name, one per line").grid(row=3, column=0, sticky="nw", padx=8, pady=5)
    device_names = scrolledtext.ScrolledText(bluetooth, height=5, width=50)
    device_names.insert("1.0", "\n".join(bt.get("device_names", [])))
    device_names.grid(row=3, column=1, sticky="nsew", padx=8, pady=5)
    entries["bluetooth.device_names"] = device_names
    ttk.Label(bluetooth, text="Cloud/multi-channel aliases ID=Name, one per line").grid(row=4, column=0, sticky="nw", padx=8, pady=5)
    sensor_names = scrolledtext.ScrolledText(bluetooth, height=5, width=50)
    sensor_names.insert("1.0", "\n".join(bt.get("sensor_names", [])))
    sensor_names.grid(row=4, column=1, sticky="nsew", padx=8, pady=5)
    entries["bluetooth.sensor_names"] = sensor_names
    bluetooth.rowconfigure(4, weight=1)

    frontend = ttk.Frame(notebook)
    frontend.columnconfigure(1, weight=1)
    notebook.add(frontend, text="Web frontend")
    fe = section("frontend")
    add_bool(frontend, 0, "frontend.enabled", "Enable authenticated web frontend", fe.get("enabled", False))
    add_entry(frontend, 1, "frontend.host", "Frontend bind address", fe.get("host", "127.0.0.1"))
    add_entry(frontend, 2, "frontend.port", "Frontend HTTPS/HTTP port", fe.get("port", 8080))
    add_bool(frontend, 3, "frontend.allow_external", "Allow non-loopback frontend binding", fe.get("allow_external", False))
    add_entry(frontend, 4, "frontend.data_dir", "Frontend auth/state directory (optional)", fe.get("data_dir", ""))
    add_entry(frontend, 5, "frontend.tls_cert", "TLS certificate PEM (optional)", fe.get("tls_cert", ""))
    add_entry(frontend, 6, "frontend.tls_key", "TLS private key PEM (optional)", fe.get("tls_key", ""))

    advanced = ttk.Frame(notebook)
    advanced.columnconfigure(1, weight=1)
    notebook.add(advanced, text="Advanced")
    add_entry(advanced, 0, "cloud.config_file", "Cloud/BLE keys TOML file", section("cloud").get("config_file", ""))
    add_entry(advanced, 1, "mqtt.client_id", "MQTT client ID (blank = automatic)", mq.get("client_id", ""))
    add_entry(advanced, 2, "mqtt.qos", "MQTT QoS", mq.get("qos", 1))
    add_entry(advanced, 3, "mqtt.stale_cycles", "Retained cleanup after missing cycles", mq.get("stale_cycles", 3))
    add_entry(advanced, 4, "mqtt.connect_timeout", "MQTT connect/publish timeout (s)", mq.get("connect_timeout", 15))
    add_bool(advanced, 5, "mqtt.retain", "Retain sensor states", mq.get("retain", True))

    status_var = tk.StringVar(value="Service status not checked")
    ttk.Label(root, textvariable=status_var, anchor="w").pack(fill="x", padx=14, pady=(0, 4))

    def get_text_widget(key: str) -> str:
        widget = entries[key]
        return str(widget.get("1.0", "end")).strip()  # type: ignore[attr-defined]

    def parse_number(text: str, kind: type[int] | type[float]) -> int | float:
        return kind(text.strip())

    def collect() -> dict[str, Any]:
        merged = _deep_merge(loaded, default_config())
        # Start from defaults, then preserve unknown keys from the loaded file.
        merged = _deep_merge(default_config(), loaded)
        def setv(section_name: str, key: str, value: Any) -> None:
            merged.setdefault(section_name, {})[key] = value
        for dotted, var in vars_.items():
            sec, key = dotted.split(".", 1)
            raw: Any = var.get()
            if dotted in {
                "bluetooth.poll_interval", "bluetooth.scan_duration", "bluetooth.plugin_timeout",
                "mqtt.connect_timeout",
            }:
                raw = parse_number(str(raw), float)
            elif dotted in {"mqtt.port", "mqtt.qos", "mqtt.stale_cycles", "runtime.sensor_retry_attempts", "runtime.sensor_stale_cycles", "prometheus.port", "snmp.port", "frontend.port"}:
                raw = parse_number(str(raw), int)
            elif dotted == "mqtt_cache.max_size":
                text = str(raw).strip()
                raw = int(text) if text.isdigit() else text
            elif dotted == "bluetooth.plugins":
                raw = _split_lines(str(raw))
            setv(sec, key, raw)
        for dotted in ("bluetooth.devices", "bluetooth.device_names", "bluetooth.sensor_names"):
            sec, key = dotted.split(".", 1)
            setv(sec, key, _split_lines(get_text_widget(dotted)))
        return merged

    def save(restart: bool = False) -> None:
        try:
            new_config = collect()
            if os.name == "nt" and not _is_windows_admin():
                fd, temp = tempfile.mkstemp(suffix=".toml", prefix="ble-sensors-mqtt-")
                os.close(fd)
                temp_path = Path(temp)
                atomic_write_config(temp_path, new_config)
                _windows_elevate_apply(temp_path, restart)
                messagebox.showinfo(APP, "Windows requested administrator approval to save the system configuration.")
                return
            atomic_write_config(path, new_config)
            if restart:
                ok, text = service_action("restart")
                if not ok:
                    raise RuntimeError(text or "service restart failed")
            messagebox.showinfo(APP, f"Configuration saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror(APP, str(exc))

    def update_status() -> None:
        ok, text = service_action("status")
        first = text.splitlines()[0] if text else ("running" if ok else "not running")
        status_var.set(first[:180])

    def do_service(action: str) -> None:
        if os.name == "nt" and action != "status" and not _is_windows_admin():
            try:
                _windows_elevate(["--service-action", action])
                status_var.set(f"Windows requested administrator approval to {action} the service")
            except Exception as exc:
                messagebox.showerror(APP, str(exc))
            return
        ok, text = service_action(action)
        if not ok:
            messagebox.showerror(APP, text or f"Service {action} failed")
        update_status()

    def test_bluetooth() -> None:
        try:
            exe = daemon_executable()
            cmd = [str(exe), "--scan", "--scan-duration", "5", "--config", str(path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)  # nosec B603
            output = (result.stdout or result.stderr or "No output")[:10000]
            messagebox.showinfo("Bluetooth test", output)
        except Exception as exc:
            messagebox.showerror("Bluetooth test", str(exc))

    def open_folder() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(path.parent)  # type: ignore[attr-defined]  # nosec B606
        elif sys.platform == "darwin":
            subprocess.Popen([MAC_OPEN, str(path.parent)])  # nosec B603
        else:
            subprocess.Popen([LINUX_XDG_OPEN, str(path.parent)])  # nosec B603

    buttons = ttk.Frame(root)
    buttons.pack(fill="x", padx=12, pady=(4, 12))
    ttk.Button(buttons, text="Save", command=lambda: save(False)).pack(side="left", padx=3)
    ttk.Button(buttons, text="Save & restart service", command=lambda: save(True)).pack(side="left", padx=3)
    ttk.Button(buttons, text="Start service", command=lambda: do_service("start")).pack(side="left", padx=3)
    ttk.Button(buttons, text="Stop service", command=lambda: do_service("stop")).pack(side="left", padx=3)
    ttk.Button(buttons, text="Test Bluetooth", command=test_bluetooth).pack(side="left", padx=3)
    ttk.Button(buttons, text="Open config folder", command=open_folder).pack(side="right", padx=3)

    update_status()
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-elevated", type=Path)
    parser.add_argument("--restart-service", action="store_true")
    parser.add_argument("--service-action", choices=("start", "stop", "restart"))
    args = parser.parse_args(argv)
    if args.apply_elevated:
        return apply_elevated(args.apply_elevated, restart=args.restart_service)
    if args.service_action:
        ok, text = service_action(args.service_action)
        if not ok:
            print(text, file=sys.stderr)
            return 2
        return 0
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
