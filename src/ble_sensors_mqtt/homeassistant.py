"""Home Assistant MQTT Discovery support."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .binary import binary_device_class, coerce_binary
from .version import __version__

_MAX_DEPTH = 5
_RESERVED_DATA_KEYS = {"units", "unhandled"}


@dataclass(frozen=True)
class EntityMetadata:
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    icon: str | None = None


KNOWN_ENTITIES: dict[str, EntityMetadata] = {
    "temperature": EntityMetadata("temperature", "°C", "measurement"),
    "humidity": EntityMetadata("humidity", "%", "measurement"),
    "battery": EntityMetadata("battery", "%", "measurement"),
    "battery_percent": EntityMetadata("battery", "%", "measurement"),
    "co2": EntityMetadata("carbon_dioxide", "ppm", "measurement"),
    "carbon_dioxide": EntityMetadata("carbon_dioxide", "ppm", "measurement"),
    "pressure": EntityMetadata("pressure", "Pa", "measurement"),
    "voltage": EntityMetadata("voltage", "V", "measurement"),
    "current": EntityMetadata("current", "A", "measurement"),
    "power": EntityMetadata("power", "W", "measurement"),
    "illuminance": EntityMetadata("illuminance", "lx", "measurement"),
    "pm2_5": EntityMetadata("pm25", "µg/m³", "measurement"),
    "pm10": EntityMetadata("pm10", "µg/m³", "measurement"),
    "rssi": EntityMetadata("signal_strength", "dBm", "measurement"),
    "radon_1day_avg": EntityMetadata(None, "Bq/m³", "measurement"),
    "radon_longterm_avg": EntityMetadata(None, "Bq/m³", "measurement"),
}


def _slug(value: str, *, limit: int = 80) -> str:
    result = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return (result or "value")[:limit]


def _device_id(address: str) -> str:
    readable = _slug(address, limit=64)
    digest = hashlib.sha256(address.encode("utf-8")).hexdigest()[:10]
    return f"{readable}_{digest}"


def _entity_id(path: tuple[str, ...]) -> str:
    readable = _slug("_".join(path), limit=72)
    digest = hashlib.sha256("\x00".join(path).encode("utf-8")).hexdigest()[:8]
    return f"{readable}_{digest}"


def _scalar(value: Any) -> bool:
    if value is None or isinstance(value, (dict, list, tuple, set, bytes, bytearray)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return isinstance(value, (str, bool, int, float))


def _flatten_scalars(
    value: Mapping[str, Any], prefix: tuple[str, ...] = (), depth: int = 0
) -> list[tuple[tuple[str, ...], Any]]:
    if depth > _MAX_DEPTH:
        return []
    result: list[tuple[tuple[str, ...], Any]] = []
    for raw_key, item in value.items():
        key = str(raw_key)
        if not prefix and key in _RESERVED_DATA_KEYS:
            continue
        path = (*prefix, key)
        if _scalar(item):
            result.append((path, item))
        elif isinstance(item, Mapping):
            result.extend(_flatten_scalars(item, path, depth + 1))
    return result


def _jinja_path(path: tuple[str, ...]) -> str:
    return "".join(f"[{json.dumps(part, ensure_ascii=False)}]" for part in path)


def _unit_for(payload: Mapping[str, Any], path: tuple[str, ...], metadata: EntityMetadata) -> str | None:
    data = payload.get("data")
    if isinstance(data, Mapping):
        units = data.get("units")
        if isinstance(units, Mapping):
            dotted = ".".join(path)
            candidates = (dotted, path[-1])
            for candidate in candidates:
                unit = units.get(candidate)
                if isinstance(unit, str) and unit:
                    return unit[:32]
    return metadata.unit


def _metadata_for(path: tuple[str, ...], value: Any) -> EntityMetadata:
    metadata = KNOWN_ENTITIES.get(path[-1].lower(), EntityMetadata())
    if metadata.state_class and not isinstance(value, (int, float)):
        return EntityMetadata(metadata.device_class, metadata.unit, None, metadata.icon)
    return metadata


def discovery_messages(
    *,
    discovery_prefix: str,
    mqtt_prefix: str,
    address: str,
    payload: Mapping[str, Any],
) -> dict[str, bytes]:
    """Return retained Home Assistant discovery config messages for one sensor."""
    device_id = _device_id(address)
    state_topic = f"{mqtt_prefix}/{_mqtt_device_part(address)}/state"
    availability_topic = f"{mqtt_prefix}/bridge/status"
    device_name = str(payload.get("name") or payload.get("bluetooth_name") or address)
    manufacturer = str(payload.get("manufacturer") or "Unknown")
    model = str(payload.get("model") or "Unknown")
    data = payload.get("data")

    device: dict[str, Any] = {
        "identifiers": [f"ble_sensors_mqtt_{device_id}"],
        "name": device_name,
        "manufacturer": manufacturer,
        "model": model,
    }
    if isinstance(data, Mapping):
        sw_version = data.get("software_version")
        hw_version = data.get("hardware_version")
        if isinstance(sw_version, (str, int, float)):
            device["sw_version"] = str(sw_version)
        if isinstance(hw_version, (str, int, float)):
            device["hw_version"] = str(hw_version)

    scalars: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(data, Mapping):
        scalars.extend(_flatten_scalars(data))
    rssi = payload.get("rssi")
    if _scalar(rssi):
        scalars.append((("rssi",), rssi))

    messages: dict[str, bytes] = {}
    seen: set[tuple[str, ...]] = set()
    for path, value in scalars:
        if path in seen:
            continue
        seen.add(path)
        leaf = path[-1]
        metadata = _metadata_for(path, value)
        binary_class = binary_device_class(leaf) if coerce_binary(value) is not None else None
        domain = "binary_sensor" if binary_class else "sensor"
        unique_id = f"ble_sensors_mqtt_{device_id}_{_entity_id(path)}"
        object_id = f"{device_id}_{_slug('_'.join(path), limit=64)}"
        config_topic = f"{discovery_prefix}/{domain}/{device_id}/{_entity_id(path)}/config"
        source_path = ("rssi",) if path == ("rssi",) else ("data", *path)
        raw_template = "value_json" + _jinja_path(source_path)
        value_template = "{{ " + raw_template + " }}"
        if binary_class:
            value_template = (
                "{% set v = " + raw_template + " %}"
                "{{ 'ON' if v == true or v == 1 or (v|string|lower) in "
                "['true','on','yes','active','detected','present','occupied','moving'] else 'OFF' }}"
            )
        config: dict[str, Any] = {
            "name": _friendly_name(leaf),
            "object_id": object_id,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "value_template": value_template,
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
            "origin": {
                "name": "ble-sensors-mqtt",
                "sw_version": __version__,
                "support_url": "https://github.com/desalvo/ble-sensors-mqtt",
            },
            "entity_category": "diagnostic" if leaf.lower() in {"rssi", "software_version", "hardware_version"} else None,
        }
        if binary_class:
            config["device_class"] = binary_class
            config["payload_on"] = "ON"
            config["payload_off"] = "OFF"
        if not binary_class:
            unit = _unit_for(payload, path, metadata)
            if unit:
                config["unit_of_measurement"] = unit
            if metadata.device_class:
                config["device_class"] = metadata.device_class
            if metadata.state_class:
                config["state_class"] = metadata.state_class
            if metadata.icon:
                config["icon"] = metadata.icon
        config = {key: item for key, item in config.items() if item is not None}
        messages[config_topic] = json.dumps(
            config, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

    # Expose protocol once as a diagnostic sensor even though it is top-level metadata.
    protocol_path = ("protocol",)
    protocol_topic = f"{discovery_prefix}/sensor/{device_id}/{_entity_id(protocol_path)}/config"
    protocol_config = {
        "name": "Protocol",
        "object_id": f"{device_id}_protocol",
        "unique_id": f"ble_sensors_mqtt_{device_id}_{_entity_id(protocol_path)}",
        "state_topic": state_topic,
        "value_template": "{{ value_json[\"protocol\"] }}",
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device,
        "entity_category": "diagnostic",
        "origin": {
            "name": "ble-sensors-mqtt",
            "sw_version": __version__,
            "support_url": "https://github.com/desalvo/ble-sensors-mqtt",
        },
    }
    messages[protocol_topic] = json.dumps(
        protocol_config, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")

    if "stale" in payload:
        stale_path = ("stale",)
        stale_topic = f"{discovery_prefix}/sensor/{device_id}/{_entity_id(stale_path)}/config"
        stale_config = {
            "name": "Stale",
            "object_id": f"{device_id}_stale",
            "unique_id": f"ble_sensors_mqtt_{device_id}_{_entity_id(stale_path)}",
            "state_topic": state_topic,
            "value_template": "{{ 1 if value_json.get(\"stale\", false) else 0 }}",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device,
            "entity_category": "diagnostic",
            "origin": {
                "name": "ble-sensors-mqtt",
                "sw_version": __version__,
                "support_url": "https://github.com/desalvo/ble-sensors-mqtt",
            },
        }
        messages[stale_topic] = json.dumps(
            stale_config, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    return messages


def _friendly_name(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title() or "Value"


def _mqtt_device_part(address: str) -> str:
    # Kept local to avoid a cli -> homeassistant -> cli import cycle.
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", address):
        return "".join(c for c in address.lower() if c in "0123456789abcdef")
    normalized = re.sub(r"[^a-z0-9_-]+", "_", address.lower()).strip("_") or "sensor"
    digest = hashlib.sha256(address.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:110]}_{digest}"
