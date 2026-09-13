"""Plugin-based BLE/cloud sensor gateway for MQTT, Prometheus, and SNMP."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import hashlib
import json
import logging
import math
import os
import re
import signal
import ssl
import stat
import sys
import tempfile
import threading
import time
import tomllib
from collections.abc import Mapping
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from .metrics import SensorStore
from .plugin_api import SensorReading
from .version import __version__

LOG = logging.getLogger("ble_sensors_mqtt")
MAX_INTERVAL = 86_400.0
MAX_SAFE_STRING = 4096
MAX_JSON_PAYLOAD = 262_144
MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def positive_seconds(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or not 1 <= parsed <= MAX_INTERVAL:
        raise argparse.ArgumentTypeError("must be between 1 and 86400 seconds")
    return parsed


def mqtt_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid port") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return port


def bind_address(value: str) -> str:
    """Accept a literal IPv4 or IPv6 listen address."""
    try:
        return str(ip_address(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a literal IPv4 or IPv6 address") from exc


def is_external_bind(value: str) -> bool:
    address = ip_address(value)
    return address.is_unspecified or not address.is_loopback


def is_local_mqtt_host(value: str) -> bool:
    candidate = value.strip().lower()
    if candidate in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return False


def topic_prefix(value: str) -> str:
    candidate = value.strip("/").strip()
    if not candidate or len(candidate) > 256:
        raise argparse.ArgumentTypeError("MQTT topic prefix must contain 1 to 256 characters")
    if any(ch in candidate for ch in ("#", "+", "\x00")) or not candidate.isprintable():
        raise argparse.ArgumentTypeError("MQTT topic prefix contains invalid MQTT characters")
    return candidate


def device_address(value: str) -> str:
    if not MAC_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("invalid MAC address; use AA:BB:CC:DD:EE:FF")
    return value.replace("-", ":").upper()


def sensor_identifier(value: str) -> str:
    """Normalize a BLE MAC or a printable cloud/plugin sensor identifier."""
    candidate = value.strip()
    if MAC_PATTERN.fullmatch(candidate):
        return device_address(candidate)
    if not 1 <= len(candidate) <= 160 or not candidate.isprintable():
        raise argparse.ArgumentTypeError("sensor ID must contain 1 to 160 printable characters")
    return candidate.upper()


def device_name(value: str) -> tuple[str, str]:
    address, separator, name = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("use MAC=NAME")
    canonical = device_address(address.strip())
    name = name.strip()
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise argparse.ArgumentTypeError("name must contain 1 to 64 printable characters")
    return canonical, name


def sensor_name(value: str) -> tuple[str, str]:
    identifier, separator, name = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("use ID=NAME with a printable ID")
    identifier, name = sensor_identifier(identifier), name.strip()
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise argparse.ArgumentTypeError("name must contain 1 to 64 printable characters")
    return identifier, name


def name_map(items: list[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for address, name in items:
        if address in result:
            raise ValueError(f"duplicate name for device {address}")
        result[address] = name
    return result


def apply_device_names(
    devices: dict[str, dict[str, Any]], aliases: dict[str, str]
) -> dict[str, dict[str, Any]]:
    for address, payload in devices.items():
        alias = aliases.get(address.upper())
        if alias is None:
            continue
        payload["bluetooth_name"] = payload.get("bluetooth_name", payload.get("name"))
        payload["name"] = alias
    return devices


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--scan", action="store_true", help="discover nearby devices and exit")
    result.add_argument("--list-plugins", action="store_true", help="list plugins and exit")
    result.add_argument("--cloud-help", action="store_true", help="show cloud setup help and exit")
    result.add_argument(
        "--plugin", action="append", default=[], metavar="NOME",
        help="enable only the named plugin; repeatable",
    )
    result.add_argument(
        "--sensor-name", action="append", default=[], type=sensor_name, metavar="ID=NOME",
        help="name a cloud or multi-channel sensor; repeatable",
    )
    result.add_argument("--cloud-config", type=Path, help="cloud provider TOML configuration")
    result.add_argument("--scan-duration", type=positive_seconds, default=8.0)
    result.add_argument("--poll-interval", type=positive_seconds, default=30.0)
    result.add_argument("--plugin-timeout", type=positive_seconds, default=15.0, help="maximum seconds for one plugin decode/cloud poll")
    result.add_argument(
        "--device",
        action="append",
        default=[],
        type=sensor_identifier,
        metavar="ID",
        help="allowed sensor ID (BLE MAC or cloud/plugin ID); repeatable",
    )
    result.add_argument(
        "--device-name",
        action="append",
        default=[],
        type=device_name,
        metavar="MAC=NOME",
        help="custom sensor name; repeatable",
    )
    result.add_argument("--mqtt-host", help="broker hostname or IP address")
    result.add_argument("--mqtt-port", type=mqtt_port, default=None)
    result.add_argument("--mqtt-client-id", default=f"ble-sensors-mqtt-{os.uname().nodename}")
    result.add_argument("--mqtt-topic-prefix", type=topic_prefix, default="ble-sensors")
    result.add_argument(
        "--home-assistant-discovery", action="store_true",
        help="publish retained Home Assistant MQTT Discovery configuration",
    )
    result.add_argument(
        "--home-assistant-discovery-prefix", type=topic_prefix, default="homeassistant",
        help="Home Assistant MQTT Discovery prefix (default: homeassistant)",
    )
    result.add_argument("--mqtt-username")
    result.add_argument("--mqtt-password-file", type=Path)
    result.add_argument(
        "--mqtt-tls", action="store_true", help="enable TLS and certificate verification"
    )
    result.add_argument("--mqtt-ca-file", type=Path)
    result.add_argument("--mqtt-connect-timeout", type=positive_seconds, default=15.0)
    result.add_argument("--allow-insecure-mqtt", action="store_true", help="explicitly allow plaintext MQTT (required with credentials or remote brokers)")
    result.add_argument("--retain", action=argparse.BooleanOptionalAction, default=True)
    result.add_argument("--stale-cycles", type=int, default=3, metavar="N", help="clear retained sensor state after N consecutive missing cycles")
    result.add_argument("--state-file", type=Path, help="persist retained-topic cleanup state across restarts")
    result.add_argument("--qos", choices=(0, 1, 2), type=int, default=1)
    result.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    result.add_argument("--once", action="store_true", help="run one polling cycle and exit")
    result.add_argument("--prometheus", action="store_true", help="expose Prometheus metrics")
    result.add_argument(
        "--prometheus-host", type=bind_address, default="127.0.0.1", metavar="IP"
    )
    result.add_argument("--prometheus-port", type=mqtt_port, default=9105)
    result.add_argument("--allow-external-prometheus", action="store_true", help="allow unauthenticated Prometheus/health HTTP on a non-loopback address")
    result.add_argument("--snmp", action="store_true", help="expose a read-only SNMPv2c agent")
    result.add_argument("--snmp-host", type=bind_address, default="127.0.0.1", metavar="IP")
    result.add_argument("--snmp-port", type=mqtt_port, default=1161)
    result.add_argument("--snmp-community-file", type=Path)
    result.add_argument("--snmp-base-oid", default="1.3.6.1.4.1.32473.1.1")
    result.add_argument("--allow-external-snmp", action="store_true", help="allow plaintext SNMPv2c on a non-loopback address")
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return result


def _safe(value: Any, depth: int = 0) -> Any:
    """Convert library models into bounded, JSON-safe data."""
    if depth > 6:
        return None
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return value[:MAX_SAFE_STRING]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 256:
                break
            text_key = str(key)[:256]
            if not text_key.startswith("_"):
                result[text_key] = _safe(item, depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_safe(item, depth + 1) for item in list(value)[:100]]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _safe(dataclasses.asdict(value), depth + 1)
    if hasattr(value, "value") and isinstance(value.value, (str, int)):
        return value.value
    return str(value)[:MAX_SAFE_STRING]


def normalize(address: str, advertisement: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for attribute in ("data", "device_data", "advertisement_data"):
        candidate = getattr(advertisement, attribute, None)
        if candidate is not None:
            safe = _safe(candidate)
            if isinstance(safe, dict):
                raw.update(safe)
    device = getattr(advertisement, "device", None)
    name = getattr(device, "name", None) or raw.get("modelName") or raw.get("model")
    rssi = getattr(advertisement, "rssi", None)
    if rssi is None:
        rssi = getattr(getattr(advertisement, "advertisement_data", None), "rssi", None)
    payload: dict[str, Any] = {
        "address": address.upper(),
        "name": name,
        "rssi": rssi,
        "observed_at": datetime.now(UTC).isoformat(),
        "data": raw,
    }
    return _safe(payload)


async def discover(duration: float) -> dict[str, dict[str, Any]]:
    return await discover_with_plugins(duration, None, None)


def reading_payload(reading: SensorReading) -> dict[str, Any]:
    return _safe({
        "address": reading.address,
        "name": reading.name,
        "bluetooth_name": reading.bluetooth_name,
        "manufacturer": reading.manufacturer or "Unknown",
        "model": reading.model or "Unknown",
        "protocol": reading.protocol or "Unknown",
        "rssi": reading.rssi,
        "observed_at": datetime.now(UTC).isoformat(),
        "data": reading.data,
    })


def load_cloud_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("configuration must be stored in a regular file")
    mode = info.st_mode & 0o777
    if mode & 0o027:
        raise ValueError("configuration must have permissions 0640 or more restrictive")
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    return config


def load_bindkeys(config: dict[str, Any]) -> dict[str, dict[str, bytes]]:
    result: dict[str, dict[str, bytes]] = {}
    entries = config.get("ble_keys", {})
    if not isinstance(entries, dict):
        raise ValueError("ble_keys must be a TOML table")  # noqa: TRY004
    for address, item in entries.items():
        canonical = device_address(str(address))
        if not isinstance(item, dict) or item.get("plugin") not in ("xiaomi", "bthome"):
            raise ValueError(f"ble_keys.{address}: plugin must be xiaomi or bthome")
        plugin_name = str(item["plugin"])
        secret = read_secret(Path(item["bindkey_file"]), f"bind key {canonical}")
        try:
            key = bytes.fromhex(secret)
        except ValueError as exc:
            raise ValueError(f"bind key {canonical}: invalid hexadecimal format") from exc
        if (plugin_name == "bthome" and len(key) != 16) or (
            plugin_name == "xiaomi" and len(key) not in (12, 16)
        ):
            raise ValueError(f"bind key {canonical}: invalid length for {plugin_name}")
        result.setdefault(plugin_name, {})[canonical] = key
    return result


async def discover_with_plugins(
    duration: float, enabled: set[str] | None, cloud_config: dict[str, Any] | None,
    plugin_timeout: float = 15.0,
) -> dict[str, dict[str, Any]]:
    from .plugins import load_plugins
    from .scanner import scan

    config = cloud_config or {}
    plugins, unavailable = load_plugins(enabled, load_bindkeys(config))
    for name, reason in unavailable.items():
        LOG.info("plugin %s was not loaded: %s", name, reason)
    readings = await scan(duration, plugins, decode_timeout=plugin_timeout)

    from .cloud import load_cloud_plugins

    cloud_plugins, cloud_unavailable = load_cloud_plugins(config, enabled, read_secret)
    for name, reason in cloud_unavailable.items():
        LOG.info("cloud plugin %s was not loaded: %s", name, reason)
    async def poll_cloud(cloud_plugin: Any) -> list[SensorReading]:
        try:
            return await asyncio.wait_for(cloud_plugin.poll(), timeout=plugin_timeout)
        except TimeoutError:
            LOG.error("cloud plugin %s timed out after %.1fs", cloud_plugin.name, plugin_timeout)
        except Exception:
            LOG.exception(
                "cloud plugin %s failed; data from other plugins is preserved",
                cloud_plugin.name,
            )
        return []

    if cloud_plugins:
        cloud_results = await asyncio.gather(*(poll_cloud(item) for item in cloud_plugins))
        for result in cloud_results:
            readings.extend(result)
    devices: dict[str, dict[str, Any]] = {}
    for reading in readings:
        key = reading.address.upper()
        if key in devices:
            LOG.warning("duplicate sensor identifier %s; keeping the first reading", key)
            continue
        devices[key] = reading_payload(reading)
    return devices


def topic_part(address: str) -> str:
    if MAC_PATTERN.fullmatch(address):
        return "".join(c for c in address.lower() if c in "0123456789abcdef")
    normalized = re.sub(r"[^a-z0-9_-]+", "_", address.lower()).strip("_") or "sensor"
    digest = hashlib.sha256(address.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:110]}_{digest}"



def load_runtime_state(path: Path | None, prefix: str) -> tuple[set[str], dict[str, int]]:
    if path is None or not path.exists():
        return set(), {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("runtime state path must be a regular non-symlink file")
    if path.stat().st_size > 1_048_576:
        raise ValueError("runtime state file is unexpectedly large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("runtime state file has an unsupported format")
    if data.get("topic_prefix") != prefix:
        LOG.warning("ignoring runtime state created for a different MQTT topic prefix")
        return set(), {}
    raw_topics = data.get("published_topics", [])
    raw_missing = data.get("missing_cycles", {})
    if not isinstance(raw_topics, list) or not isinstance(raw_missing, dict):
        raise ValueError("runtime state file is malformed")
    topics = {str(item) for item in raw_topics[:10_000] if isinstance(item, str)}
    missing: dict[str, int] = {}
    for topic, count in list(raw_missing.items())[:10_000]:
        if isinstance(topic, str) and topic in topics and isinstance(count, int) and 0 <= count <= 1000:
            missing[topic] = count
    return topics, missing


def save_runtime_state(
    path: Path | None, prefix: str, published_topics: set[str], missing_cycles: dict[str, int]
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "topic_prefix": prefix,
        "published_topics": sorted(published_topics),
        "missing_cycles": {key: missing_cycles[key] for key in sorted(missing_cycles)},
    }
    encoded = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > 1_048_576:
        raise ValueError("runtime state exceeds 1 MiB")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1
        os.replace(temp_name, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if fd >= 0:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)


def make_client(args: argparse.Namespace) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.mqtt_client_id)
    if args.mqtt_username:
        password = None
        if args.mqtt_password_file:
            password = read_secret(args.mqtt_password_file, "MQTT password")
        client.username_pw_set(args.mqtt_username, password)
    if args.mqtt_tls:
        client.tls_set(ca_certs=str(args.mqtt_ca_file) if args.mqtt_ca_file else None,
                       cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    return client


def read_secret(path: Path, description: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"{description} cannot be opened securely: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{description} must be stored in a regular file")
        mode = info.st_mode & 0o777
        if mode & 0o027:
            raise ValueError(f"{description} must have permissions 0640 or more restrictive")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            value = handle.read(513).strip()
        if not value or len(value) > 512 or "\x00" in value:
            raise ValueError(f"{description} has invalid content")
        return value
    finally:
        os.close(fd)


def validate_runtime_security(args: argparse.Namespace) -> None:
    """Validate fail-closed production transport and bind policies."""
    if args.stale_cycles < 1 or args.stale_cycles > 1000:
        raise ValueError("--stale-cycles must be between 1 and 1000")
    if not args.mqtt_tls and not args.allow_insecure_mqtt:
        if args.mqtt_username or not is_local_mqtt_host(args.mqtt_host):
            raise ValueError(
                "plaintext MQTT to a remote/credentialed broker requires --allow-insecure-mqtt; "
                "use --mqtt-tls in production"
            )
        LOG.warning("MQTT is using plaintext transport on a loopback broker")
    if args.prometheus and is_external_bind(args.prometheus_host) and not args.allow_external_prometheus:
        raise ValueError(
            "external Prometheus/health binding requires --allow-external-prometheus because the HTTP endpoint has no authentication or TLS"
        )
    if args.snmp and is_external_bind(args.snmp_host) and not args.allow_external_snmp:
        raise ValueError(
            "external SNMPv2c binding requires --allow-external-snmp because SNMPv2c is plaintext"
        )


async def bridge(args: argparse.Namespace) -> int:
    validate_runtime_security(args)

    allowed = set(args.device)
    aliases = name_map(args.device_name + args.sensor_name)
    cloud_config = load_cloud_config(args.cloud_config)
    enabled = set(args.plugin) or None
    prefix = args.mqtt_topic_prefix
    client = make_client(args)
    port = args.mqtt_port or (8883 if args.mqtt_tls else 1883)
    connected = threading.Event()

    def on_connect(_client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if reason_code == 0:
            connected.set()
            LOG.info("connected to MQTT broker %s:%d", args.mqtt_host, port)
        else:
            connected.clear()
            LOG.error("MQTT broker rejected connection: %s", reason_code)

    def on_disconnect(_client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        connected.clear()
        if reason_code != 0:
            LOG.warning("unexpected MQTT disconnect: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.will_set(f"{prefix}/bridge/status", "offline", qos=1, retain=True)
    client.connect(args.mqtt_host, port, keepalive=60)
    client.loop_start()
    if not await asyncio.to_thread(connected.wait, args.mqtt_connect_timeout):
        client.loop_stop()
        client.disconnect()
        raise OSError(f"MQTT CONNACK was not received within {args.mqtt_connect_timeout:.1f}s")
    online = client.publish(f"{prefix}/bridge/status", "online", qos=1, retain=True)
    if online.rc != mqtt.MQTT_ERR_SUCCESS:
        raise OSError(f"failed to queue MQTT online status: rc={online.rc}")
    online.wait_for_publish(args.mqtt_connect_timeout)

    store = SensorStore()
    prometheus_server = None
    snmp_transport = None
    if args.prometheus:
        from .prometheus import start as start_prometheus

        prometheus_server = start_prometheus(
            store, args.prometheus_host, args.prometheus_port,
            ready_max_age=max(args.poll_interval * 3, args.scan_duration * 3),
        )
    if args.snmp:
        from .snmp import start as start_snmp

        community = read_secret(args.snmp_community_file, "SNMP community")
        snmp_transport = await start_snmp(
            store, args.snmp_host, args.snmp_port, community, args.snmp_base_oid
        )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signum, stop.set)

    try:
        previously_published, missing_cycles = load_runtime_state(args.state_file, prefix)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.warning("runtime state could not be loaded and will be rebuilt: %s", exc)
        previously_published, missing_cycles = set(), {}
    try:
        while not stop.is_set():
            started = time.monotonic()
            try:
                devices = apply_device_names(
                    await discover_with_plugins(
                        args.scan_duration, enabled, cloud_config, args.plugin_timeout
                    ),
                    aliases,
                )
                exported = {
                    address: payload
                    for address, payload in devices.items()
                    if not allowed or address in allowed
                }
                store.replace(exported)
                current_topics: set[str] = set()
                current_discovery_topics: set[str] = set()
                for address, payload in sorted(exported.items()):
                    topic = f"{prefix}/{topic_part(address)}/state"
                    current_topics.add(topic)
                    encoded = json.dumps(
                        payload, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    if len(encoded) > MAX_JSON_PAYLOAD:
                        raise ValueError(
                            f"MQTT payload for {address} exceeds {MAX_JSON_PAYLOAD} bytes"
                        )
                    info = client.publish(topic, encoded, qos=args.qos, retain=args.retain)
                    if info.rc != mqtt.MQTT_ERR_SUCCESS:
                        raise OSError(f"publish was not queued for {address}: rc={info.rc}")
                    info.wait_for_publish(args.mqtt_connect_timeout)
                    missing_cycles.pop(topic, None)

                    if args.home_assistant_discovery:
                        from .homeassistant import discovery_messages

                        configs = discovery_messages(
                            discovery_prefix=args.home_assistant_discovery_prefix,
                            mqtt_prefix=prefix,
                            address=address,
                            payload=payload,
                        )
                        for config_topic, config_payload in sorted(configs.items()):
                            current_discovery_topics.add(config_topic)
                            discovery_info = client.publish(
                                config_topic, config_payload, qos=1, retain=True
                            )
                            if discovery_info.rc != mqtt.MQTT_ERR_SUCCESS:
                                raise OSError(
                                    f"Home Assistant discovery publish was not queued for {address}: "
                                    f"rc={discovery_info.rc}"
                                )
                            discovery_info.wait_for_publish(args.mqtt_connect_timeout)
                            missing_cycles.pop(config_topic, None)

                previous_discovery_topics = {
                    topic for topic in previously_published if topic.endswith("/config")
                }
                for stale_discovery_topic in previous_discovery_topics - current_discovery_topics:
                    discovery_info = client.publish(
                        stale_discovery_topic, b"", qos=1, retain=True
                    )
                    if discovery_info.rc == mqtt.MQTT_ERR_SUCCESS:
                        discovery_info.wait_for_publish(args.mqtt_connect_timeout)
                        missing_cycles.pop(stale_discovery_topic, None)
                        LOG.info(
                            "cleared stale Home Assistant discovery topic %s",
                            stale_discovery_topic,
                        )

                if args.retain:
                    for topic in (previously_published - current_topics) - previous_discovery_topics:
                        misses = missing_cycles.get(topic, 0) + 1
                        missing_cycles[topic] = misses
                        if misses >= args.stale_cycles:
                            info = client.publish(topic, b"", qos=args.qos, retain=True)
                            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                                info.wait_for_publish(args.mqtt_connect_timeout)
                                missing_cycles.pop(topic, None)
                                LOG.info("cleared stale retained MQTT topic %s", topic)
                    previously_published = (
                        current_topics | current_discovery_topics | set(missing_cycles)
                    )
                else:
                    previously_published = current_topics | current_discovery_topics

                save_runtime_state(args.state_file, prefix, previously_published, missing_cycles)
                store.mark_success()
                LOG.info("polling cycle completed: %d sensors exported", len(exported))
            except Exception as exc:
                store.mark_failure(str(exc))
                LOG.exception("polling cycle failed; retrying at the next interval")
            if args.once:
                break
            remaining = max(0.0, args.poll_interval - (time.monotonic() - started))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=remaining)
    finally:
        if prometheus_server:
            prometheus_server.shutdown()
            prometheus_server.server_close()
        if snmp_transport:
            snmp_transport.close()
        if connected.is_set():
            offline = client.publish(f"{prefix}/bridge/status", "offline", qos=1, retain=True)
            if offline.rc == mqtt.MQTT_ERR_SUCCESS:
                offline.wait_for_publish(3)
        client.disconnect()
        client.loop_stop()
    return 0


async def async_main(args: argparse.Namespace) -> int:
    if args.list_plugins:
        from .cloud import cloud_plugin_catalog
        from .plugins import load_plugins, plugin_catalog

        loaded, unavailable = load_plugins(set(args.plugin) or None)
        active = {item.name for item in loaded}
        catalog = plugin_catalog() | cloud_plugin_catalog()
        for name, description in catalog.items():
            if name in active:
                status = "available"
            elif name in cloud_plugin_catalog():
                status = "cloud; enable in TOML configuration"
            else:
                status = unavailable.get(name, "configurable")
            print(f"{name:14} {status:55} {description}")
        return 0
    if args.cloud_help:
        from .cloud import cloud_help

        print(cloud_help())
        return 0
    aliases = name_map(args.device_name + args.sensor_name)
    if args.scan:
        devices = apply_device_names(await discover_with_plugins(
            args.scan_duration, set(args.plugin) or None, load_cloud_config(args.cloud_config)
        ), aliases)
        print(json.dumps(list(devices.values()), indent=2, ensure_ascii=False))
        return 0
    if not args.mqtt_host:
        raise ValueError("--mqtt-host is required unless using --scan, --list-plugins, or --cloud-help")
    if args.mqtt_password_file and not args.mqtt_username:
        raise ValueError("--mqtt-password-file requires --mqtt-username")
    if args.snmp and not args.snmp_community_file:
        raise ValueError("--snmp requires --snmp-community-file")
    return await bridge(args)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        return asyncio.run(async_main(args))
    except (ValueError, OSError) as exc:
        LOG.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
