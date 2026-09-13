"""Cross-platform application configuration helpers."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

APP_NAME = "ble-sensors-mqtt"


def default_config_path() -> Path:
    """Return the native persistent configuration path for the current OS."""
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        return base / APP_NAME / "config.toml"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "config.toml"
    return Path("/etc") / APP_NAME / "config.toml"


def default_frontend_data_dir() -> Path:
    """Writable persistent state used by the optional web frontend and runtime overrides."""
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / APP_NAME / "frontend"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "frontend"
    system_state = Path("/var/lib") / APP_NAME
    if (system_state.exists() and os.access(system_state, os.W_OK)) or (hasattr(os, "geteuid") and os.geteuid() == 0):
        return system_state / "frontend"
    state_home = os.environ.get("XDG_STATE_HOME")
    return (Path(state_home) if state_home else Path.home() / ".local" / "state") / APP_NAME / "frontend"


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate_config_file(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("application configuration must not be a symlink")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("application configuration must be stored in a regular file")
    if os.name == "posix" and sys.platform != "darwin" and info.st_mode & 0o027:
        raise ValueError("application configuration must have permissions 0640 or more restrictive")


def load_config(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return {}
    _validate_config_file(path)
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise ValueError("application configuration root must be a TOML table")
    return value


def _path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value)).expanduser()


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ValueError("configuration list value must be a TOML array")


def cli_defaults(config: dict[str, Any]) -> dict[str, Any]:
    """Map config.toml sections to argparse destinations.

    Types are intentionally native Python values because argparse does not re-run ``type=``
    converters for defaults installed programmatically.
    """
    result: dict[str, Any] = {}

    def section(name: str) -> dict[str, Any]:
        value = config.get(name, {})
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"[{name}] must be a TOML table")
        return value

    bluetooth = section("bluetooth")
    runtime = section("runtime")
    mqtt = section("mqtt")
    cache = section("mqtt_cache")
    prometheus = section("prometheus")
    snmp = section("snmp")
    frontend = section("frontend")
    cloud = section("cloud")

    scalar_map = [
        (bluetooth, "adapter", "bluetooth_adapter"),
        (bluetooth, "scan_duration", "scan_duration"),
        (bluetooth, "poll_interval", "poll_interval"),
        (bluetooth, "plugin_timeout", "plugin_timeout"),
        (runtime, "reuse_stale_data", "reuse_stale_data"),
        (runtime, "state_file", "state_file"),
        (runtime, "log_level", "log_level"),
        (mqtt, "host", "mqtt_host"),
        (mqtt, "port", "mqtt_port"),
        (mqtt, "client_id", "mqtt_client_id"),
        (mqtt, "topic_prefix", "mqtt_topic_prefix"),
        (mqtt, "username", "mqtt_username"),
        (mqtt, "password_file", "mqtt_password_file"),
        (mqtt, "tls", "mqtt_tls"),
        (mqtt, "ca_file", "mqtt_ca_file"),
        (mqtt, "connect_timeout", "mqtt_connect_timeout"),
        (mqtt, "allow_insecure", "allow_insecure_mqtt"),
        (mqtt, "retain", "retain"),
        (mqtt, "qos", "qos"),
        (mqtt, "stale_cycles", "stale_cycles"),
        (mqtt, "home_assistant_discovery", "home_assistant_discovery"),
        (mqtt, "home_assistant_discovery_prefix", "home_assistant_discovery_prefix"),
        (cache, "enabled", "mqtt_cache"),
        (cache, "path", "mqtt_cache_path"),
        (cache, "max_size", "mqtt_cache_max_size"),
        (prometheus, "enabled", "prometheus"),
        (prometheus, "host", "prometheus_host"),
        (prometheus, "port", "prometheus_port"),
        (prometheus, "allow_external", "allow_external_prometheus"),
        (snmp, "enabled", "snmp"),
        (snmp, "host", "snmp_host"),
        (snmp, "port", "snmp_port"),
        (snmp, "community_file", "snmp_community_file"),
        (snmp, "base_oid", "snmp_base_oid"),
        (snmp, "allow_external", "allow_external_snmp"),
        (frontend, "enabled", "frontend"),
        (frontend, "host", "frontend_host"),
        (frontend, "port", "frontend_port"),
        (frontend, "data_dir", "frontend_data_dir"),
        (frontend, "tls_cert", "frontend_tls_cert"),
        (frontend, "tls_key", "frontend_tls_key"),
        (frontend, "allow_external", "allow_external_frontend"),
        (cloud, "config_file", "cloud_config"),
    ]
    path_dests = {
        "state_file", "mqtt_password_file", "mqtt_ca_file", "mqtt_cache_path",
        "snmp_community_file", "frontend_data_dir", "frontend_tls_cert", "frontend_tls_key", "cloud_config",
    }
    for source, key, dest in scalar_map:
        if key not in source:
            continue
        value = source[key]
        if dest in {"bluetooth_adapter", "mqtt_client_id"} and value in (None, ""):
            continue
        if dest in path_dests:
            value = _path(value)
        result[dest] = value

    # Repeatable fields use their CLI spelling in TOML arrays. Validation remains in cli.py.
    for key, dest in (
        ("plugins", "plugin"),
        ("devices", "device"),
        ("device_names", "device_name"),
        ("sensor_names", "sensor_name"),
    ):
        if key in bluetooth:
            result[dest] = _list(bluetooth[key])

    return result


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, Path):
        return _quote(str(value))
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def dump_config(config: dict[str, Any]) -> str:
    """Serialize the application configuration schema to TOML, including nested tables."""
    lines: list[str] = []

    def write_table(prefix: str, table: dict[str, Any]) -> None:
        scalars = {key: value for key, value in table.items() if not isinstance(value, dict)}
        nested = {key: value for key, value in table.items() if isinstance(value, dict)}
        if prefix:
            lines.append(f"[{prefix}]")
            for key, value in scalars.items():
                if value is not None:
                    lines.append(f"{key} = {_toml_value(value)}")
            lines.append("")
        for key, value in nested.items():
            write_table(f"{prefix}.{key}" if prefix else key, value)

    for section_name, section_value in config.items():
        if isinstance(section_value, dict):
            write_table(section_name, section_value)
    return "\n".join(lines).rstrip() + "\n"


def atomic_write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dump_config(config)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix":
            os.chmod(temp_path, 0o640)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def default_config() -> dict[str, Any]:
    return {
        "bluetooth": {
            "adapter": "",
            "scan_duration": 8.0,
            "poll_interval": 30.0,
            "plugin_timeout": 15.0,
            "plugins": [],
            "devices": [],
            "device_names": [],
            "sensor_names": [],
        },
        "runtime": {
            "reuse_stale_data": False,
            "state_file": "",
            "log_level": "INFO",
        },
        "mqtt": {
            "host": "",
            "port": 1883,
            "client_id": "",
            "topic_prefix": "ble-sensors",
            "username": "",
            "password_file": "",  # nosec B105 - empty path, not a credential
            "tls": False,
            "ca_file": "",
            "connect_timeout": 15.0,
            "allow_insecure": False,
            "retain": True,
            "qos": 1,
            "stale_cycles": 3,
            "home_assistant_discovery": False,
            "home_assistant_discovery_prefix": "homeassistant",
        },
        "mqtt_cache": {"enabled": True, "path": "", "max_size": 1024**3},
        "prometheus": {
            "enabled": False, "host": "127.0.0.1", "port": 9105, "allow_external": False,
        },
        "snmp": {
            "enabled": False,
            "host": "127.0.0.1",
            "port": 1161,
            "community_file": "",
            "base_oid": "1.3.6.1.4.1.32473.1.1",
            "allow_external": False,
        },
        "frontend": {
            "enabled": False,
            "host": "127.0.0.1",
            "port": 8080,
            "allow_external": False,
            "data_dir": "",
            "tls_cert": "",
            "tls_key": "",
            "ldap": {
                "enabled": False, "uri": "", "bind_dn": "", "bind_password_file": "",  # nosec B105 - empty path, not a credential
                "base_dn": "", "user_filter": "(uid={username})", "user_dn_template": "",
                "default_role": "reader", "start_tls": False,
            },
            "oidc": {
                "enabled": False, "name": "SSO", "metadata_url": "", "client_id": "",
                "client_secret_file": "",  # nosec B105 - empty path, not a credential
                "scopes": "openid profile email",
                "username_claim": "preferred_username", "default_role": "reader",
            },
        },
        "cloud": {"config_file": ""},
    }


def config_from_namespace(args: Any) -> dict[str, Any]:
    """Convert a fully parsed CLI namespace into the persistent TOML schema."""
    def text_path(value: Any) -> str:
        return "" if value in (None, "") else str(value)

    return {
        "bluetooth": {
            "adapter": getattr(args, "bluetooth_adapter", None) or "",
            "scan_duration": args.scan_duration,
            "poll_interval": args.poll_interval,
            "plugin_timeout": args.plugin_timeout,
            "plugins": list(getattr(args, "plugin", [])),
            "devices": list(getattr(args, "device", [])),
            "device_names": [f"{item[0]}={item[1]}" for item in getattr(args, "device_name", [])],
            "sensor_names": [f"{item[0]}={item[1]}" for item in getattr(args, "sensor_name", [])],
        },
        "runtime": {
            "reuse_stale_data": args.reuse_stale_data,
            "state_file": text_path(args.state_file),
            "log_level": args.log_level,
        },
        "mqtt": {
            "host": args.mqtt_host or "",
            "port": args.mqtt_port or (8883 if args.mqtt_tls else 1883),
            "client_id": args.mqtt_client_id,
            "topic_prefix": args.mqtt_topic_prefix,
            "username": args.mqtt_username or "",
            "password_file": text_path(args.mqtt_password_file),
            "tls": args.mqtt_tls,
            "ca_file": text_path(args.mqtt_ca_file),
            "connect_timeout": args.mqtt_connect_timeout,
            "allow_insecure": args.allow_insecure_mqtt,
            "retain": args.retain,
            "qos": args.qos,
            "stale_cycles": args.stale_cycles,
            "home_assistant_discovery": args.home_assistant_discovery,
            "home_assistant_discovery_prefix": args.home_assistant_discovery_prefix,
        },
        "mqtt_cache": {
            "enabled": args.mqtt_cache,
            "path": text_path(args.mqtt_cache_path),
            "max_size": args.mqtt_cache_max_size,
        },
        "prometheus": {
            "enabled": args.prometheus,
            "host": args.prometheus_host,
            "port": args.prometheus_port,
            "allow_external": args.allow_external_prometheus,
        },
        "snmp": {
            "enabled": args.snmp,
            "host": args.snmp_host,
            "port": args.snmp_port,
            "community_file": text_path(args.snmp_community_file),
            "base_oid": args.snmp_base_oid,
            "allow_external": args.allow_external_snmp,
        },
        "frontend": {
            "enabled": getattr(args, "frontend", False),
            "host": getattr(args, "frontend_host", "127.0.0.1"),
            "port": getattr(args, "frontend_port", 8080),
            "allow_external": getattr(args, "allow_external_frontend", False),
            "data_dir": text_path(getattr(args, "frontend_data_dir", None)),
            "tls_cert": text_path(getattr(args, "frontend_tls_cert", None)),
            "tls_key": text_path(getattr(args, "frontend_tls_key", None)),
            "ldap": {},
            "oidc": {},
        },
        "cloud": {"config_file": text_path(args.cloud_config)},
    }
