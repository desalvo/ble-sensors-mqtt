"""Plugin registry and built-in local sensor adapters."""

from __future__ import annotations

import importlib
import logging
import time
from importlib.metadata import entry_points
from typing import Any

from .plugin_api import SensorPlugin, SensorReading

LOG = logging.getLogger("ble_sensors_mqtt.plugins")


DECODERS: dict[str, tuple[str, str, str]] = {
    "xiaomi": ("xiaomi_ble", "XiaomiBluetoothDeviceData", "Xiaomi/Mijia"),
    "govee": ("govee_ble", "GoveeBluetoothDeviceData", "Govee"),
    "inkbird": ("inkbird_ble", "INKBIRDBluetoothDeviceData", "Inkbird"),
    "thermopro": ("thermopro_ble", "ThermoProBluetoothDeviceData", "ThermoPro"),
    "qingping": ("qingping_ble", "QingpingBluetoothDeviceData", "Qingping/ClearGrass"),
    "bthome": ("bthome_ble", "BTHomeBluetoothDeviceData", "BTHome"),
    "sensorpush": ("sensorpush_ble", "SensorPushBluetoothDeviceData", "SensorPush"),
    "mopeka": ("mopeka_iot_ble", "MopekaIOTBluetoothDeviceData", "Mopeka"),
}


def _value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _update_to_readings(update: Any, service_info: Any, vendor: str) -> list[SensorReading]:
    readings: list[SensorReading] = []
    devices = update.devices or {None: None}
    for device_id, info in devices.items():
        data: dict[str, Any] = {}
        units: dict[str, str] = {}
        for key, item in update.entity_values.items():
            if key.device_id == device_id:
                data[key.key] = _value(item.native_value)
                description = update.entity_descriptions.get(key)
                unit = getattr(description, "native_unit_of_measurement", None)
                if unit is not None:
                    units[key.key] = str(_value(unit))
        for key, item in update.binary_entity_values.items():
            if key.device_id == device_id:
                data[key.key] = item.native_value
        for key, item in update.events.items():
            if key.device_id == device_id:
                data[f"event_{key.key}"] = {
                    "type": item.event_type,
                    "properties": item.event_properties or {},
                }
        if units:
            data["units"] = units
        model = getattr(info, "model", None) if info else None
        manufacturer = getattr(info, "manufacturer", None) if info else None
        name = getattr(info, "name", None) if info else None
        if info:
            if getattr(info, "sw_version", None):
                data["software_version"] = info.sw_version
            if getattr(info, "hw_version", None):
                data["hardware_version"] = info.hw_version
        if not data and not model:
            continue
        suffix = f"/{device_id}" if device_id else ""
        readings.append(SensorReading(
            address=f"{service_info.address.upper()}{suffix}",
            name=name or update.title or service_info.name or service_info.address,
            manufacturer=manufacturer or vendor,
            model=model or getattr(info, "hw_version", None) or "Unknown",
            protocol="Bluetooth LE",
            rssi=service_info.rssi,
            data=data,
            bluetooth_name=service_info.name,
        ))
    return readings


class SwitchBotPlugin:
    name = "switchbot"

    def decode(self, device: Any, advertisement: Any) -> list[SensorReading]:
        from switchbot.adv_parser import parse_advertisement_data

        parsed = parse_advertisement_data(device, advertisement)
        if not parsed:
            return []
        raw = dict(parsed.data)
        model = str(raw.get("modelName") or raw.get("model") or "Unknown")
        return [SensorReading(
            address=parsed.address.upper(),
            name=getattr(parsed.device, "name", None) or model,
            manufacturer="SwitchBot",
            model=model,
            protocol="SwitchBot BLE",
            rssi=parsed.rssi,
            data=raw,
            bluetooth_name=getattr(parsed.device, "name", None),
        )]


class SensorStatePlugin:
    def __init__(
        self, name: str, module: str, class_name: str, vendor: str,
        bindkeys: dict[str, bytes] | None = None,
    ) -> None:
        self.name = name
        self.module = module
        self.class_name = class_name
        self.vendor = vendor
        self.bindkeys = bindkeys or {}
        self._decoders: dict[str, Any] = {}

    def decode(self, device: Any, advertisement: Any) -> list[SensorReading]:
        module = importlib.import_module(self.module)
        decoder_type = getattr(module, self.class_name)
        if device.address not in self._decoders:
            key = self.bindkeys.get(device.address.upper())
            self._decoders[device.address] = decoder_type(bindkey=key) if key else decoder_type()
        decoder = self._decoders[device.address]
        try:
            from habluetooth import BluetoothServiceInfoBleak
        except ImportError:
            from home_assistant_bluetooth import BluetoothServiceInfo as BluetoothServiceInfoBleak
        try:
            service_info = BluetoothServiceInfoBleak(
                advertisement.local_name or device.name or device.address,
                device.address,
                advertisement.rssi,
                advertisement.manufacturer_data,
                advertisement.service_data,
                advertisement.service_uuids,
                "ble-sensors-mqtt",
                device,
                advertisement,
                True,
                time.monotonic(),
                advertisement.tx_power,
            )
        except TypeError:  # legacy home-assistant-bluetooth model
            service_info = BluetoothServiceInfoBleak.from_advertisement(
                device, advertisement, "ble-sensors-mqtt"
            )
        update = decoder.update(service_info)
        if not update.devices:
            return []
        readings = _update_to_readings(update, service_info, self.vendor)
        unhandled = getattr(decoder, "unhandled", None)
        if isinstance(unhandled, dict):
            for reading in readings:
                reading.data["unhandled"] = dict(unhandled)
        return readings


class RuuviPlugin:
    name = "ruuvi"

    def decode(self, device: Any, advertisement: Any) -> list[SensorReading]:
        manufacturer_data = advertisement.manufacturer_data.get(0x0499)
        if not manufacturer_data:
            return []
        from ruuvitag_sensor.decoder import get_decoder

        data = bytes(manufacturer_data)
        decoded = get_decoder(data[0]).decode_data(data)
        model = f"RuuviTag format {data[0]}"
        return [SensorReading(
            address=device.address.upper(), name=advertisement.local_name or "RuuviTag",
            manufacturer="Ruuvi", model=model, protocol="Ruuvi BLE",
            rssi=advertisement.rssi, data=dict(decoded),
            bluetooth_name=advertisement.local_name or device.name,
        )]


class AirthingsPlugin:
    name = "airthings"

    async def decode_async(self, device: Any, advertisement: Any) -> list[SensorReading]:
        name = advertisement.local_name or device.name or ""
        if not (name.startswith("Airthings") or "Wave" in name):
            return []
        from airthings_ble import AirthingsBluetoothDeviceData

        decoded = await AirthingsBluetoothDeviceData(LOG, max_attempts=1).update_device(device)
        model = getattr(decoded, "model", None)
        return [SensorReading(
            address=device.address.upper(), name=decoded.friendly_name(),
            manufacturer=getattr(decoded, "manufacturer", None) or "Airthings",
            model=getattr(model, "product_name", None) or str(model or "Unknown"),
            protocol="Airthings BLE GATT", rssi=advertisement.rssi,
            data=dict(decoded.sensors), bluetooth_name=name,
        )]

    def decode(self, device: Any, advertisement: Any) -> list[SensorReading]:
        return []


def builtin_plugins(bindkeys: dict[str, dict[str, bytes]] | None = None) -> list[SensorPlugin]:
    plugins: list[SensorPlugin] = [SwitchBotPlugin(), RuuviPlugin(), AirthingsPlugin()]
    plugins.extend(
        SensorStatePlugin(name, module, class_name, vendor, (bindkeys or {}).get(name))
        for name, (module, class_name, vendor) in DECODERS.items()
    )
    return plugins


def load_plugins(
    enabled: set[str] | None = None,
    bindkeys: dict[str, dict[str, bytes]] | None = None,
) -> tuple[list[SensorPlugin], dict[str, str]]:
    """Load available built-ins and package entry points without failing globally."""
    loaded: list[SensorPlugin] = []
    unavailable: dict[str, str] = {}
    candidates = builtin_plugins(bindkeys)
    reserved_names = {plugin.name for plugin in candidates}
    for ep in entry_points(group="ble_sensors_mqtt.sensor_plugins"):
        if ep.name in reserved_names:
            unavailable[ep.name] = "duplicate plugin name; built-in plugin takes precedence"
            continue
        try:
            plugin = ep.load()()
            if plugin.name in reserved_names:
                unavailable[ep.name] = "duplicate plugin name; built-in plugin takes precedence"
                continue
            reserved_names.add(plugin.name)
            candidates.append(plugin)
        except Exception as exc:  # noqa: BLE001 - third-party isolation boundary
            unavailable[ep.name] = f"load error: {exc}"
    for plugin in candidates:
        if enabled and plugin.name not in enabled:
            continue
        module = getattr(plugin, "module", None)
        if module:
            try:
                importlib.import_module(module)
            except ImportError:
                unavailable[plugin.name] = f"missing optional dependency: {module}"
                continue
        if plugin.name == "ruuvi":
            try:
                importlib.import_module("ruuvitag_sensor")
            except ImportError:
                unavailable[plugin.name] = "missing optional dependency: ruuvitag-sensor"
                continue
        if plugin.name == "airthings":
            try:
                importlib.import_module("airthings_ble")
            except ImportError:
                unavailable[plugin.name] = "missing optional dependency: airthings-ble"
                continue
        loaded.append(plugin)
    return loaded, unavailable


def plugin_catalog() -> dict[str, str]:
    result = {"switchbot": "SwitchBot BLE (base)"}
    result.update({name: vendor for name, (*_, vendor) in DECODERS.items()})
    result["ruuvi"] = "RuuviTag"
    result["airthings"] = "Airthings (active BLE; separate module)"
    return result
