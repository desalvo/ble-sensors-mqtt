"""Optional cloud providers and the cloud plugin registry.

Cloud providers are isolated from BLE adapters and can be extended by third-party
packages through the ``ble_sensors_mqtt.cloud_plugins`` Python entry-point group.
Secrets are always supplied by a caller-provided protected-file reader.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from .plugin_api import CloudPlugin, SensorReading

LOG = logging.getLogger("ble_sensors_mqtt.cloud")


class TuyaCloudPlugin:
    """Poll sensors exposed through the Tuya IoT Cloud API."""

    name = "tuya-cloud"
    config_key = "tuya"
    description = "Tuya Cloud (TOML configuration)"
    dependency = "tinytuya"

    def __init__(self, config: dict[str, Any], read_secret: Any) -> None:
        self.config = config
        self.read_secret = read_secret

    async def poll(self) -> list[SensorReading]:
        return await asyncio.to_thread(self._poll_sync)

    def _poll_sync(self) -> list[SensorReading]:
        import tinytuya

        cfg = self.config
        cloud = tinytuya.Cloud(
            apiRegion=str(cfg.get("region", "eu")),
            apiKey=self.read_secret(Path(cfg["api_key_file"]), "Tuya API key"),
            apiSecret=self.read_secret(Path(cfg["api_secret_file"]), "Tuya API secret"),
            apiDeviceID=str(cfg["api_device_id"]),
        )
        devices = cloud.getdevices()
        if not isinstance(devices, list):
            raise TypeError(f"invalid Tuya getdevices response: {devices!r}")
        allowed = {str(item) for item in cfg.get("device_ids", [])}
        readings: list[SensorReading] = []
        for device in devices:
            device_id = str(device.get("id", ""))
            if not device_id or (allowed and device_id not in allowed):
                continue
            response = cloud.getstatus(device_id)
            status = response.get("result", []) if isinstance(response, dict) else []
            data = {
                str(item.get("code")): item.get("value")
                for item in status if isinstance(item, dict) and item.get("code")
            }
            readings.append(SensorReading(
                address=f"TUYA:{device_id}",
                name=str(device.get("name") or device_id),
                manufacturer=str(device.get("brand") or "Tuya"),
                model=str(device.get("product_name") or device.get("product_id") or "Unknown"),
                protocol="Tuya Cloud",
                data={"category": device.get("category"), "online": device.get("online"), **data},
            ))
        return readings


BUILTIN_CLOUD_PLUGINS: tuple[type[TuyaCloudPlugin], ...] = (TuyaCloudPlugin,)


def _instantiate_external(
    factory: Callable[..., CloudPlugin], config: dict[str, Any], read_secret: Any
) -> CloudPlugin:
    """Instantiate a third-party cloud plugin using the public constructor contract."""
    return factory(config, read_secret)


def load_cloud_plugins(
    config: dict[str, Any] | None,
    enabled: set[str] | None,
    read_secret: Any,
) -> tuple[list[CloudPlugin], dict[str, str]]:
    """Load enabled/configured built-in and third-party cloud providers.

    Third-party providers register an entry point in ``ble_sensors_mqtt.cloud_plugins``.
    The entry-point name is the public plugin name (for example ``acme-cloud``), while
    configuration is read from ``[cloud.acme]`` by default. A plugin class may expose a
    ``config_key`` attribute to select a different TOML table.
    """
    cloud_config = (config or {}).get("cloud", {})
    if not isinstance(cloud_config, dict):
        raise ValueError("cloud must be a TOML table")

    loaded: list[CloudPlugin] = []
    unavailable: dict[str, str] = {}
    candidates: list[tuple[str, Any, str | None]] = [
        (plugin_type.name, plugin_type, plugin_type.dependency)
        for plugin_type in BUILTIN_CLOUD_PLUGINS
    ]

    reserved_names = {name for name, _, _ in candidates}
    for ep in entry_points(group="ble_sensors_mqtt.cloud_plugins"):
        if ep.name in reserved_names:
            unavailable[ep.name] = "duplicate plugin name; built-in provider takes precedence"
            continue
        try:
            factory = ep.load()
            public_name = str(getattr(factory, "name", ep.name))
            if public_name in reserved_names:
                unavailable[ep.name] = "duplicate plugin name; built-in provider takes precedence"
                continue
            reserved_names.add(public_name)
            candidates.append((public_name, factory, None))
        except Exception as exc:  # noqa: BLE001 - third-party isolation boundary
            unavailable[ep.name] = f"load error: {exc}"

    for public_name, factory, dependency in candidates:
        if enabled and public_name not in enabled:
            continue
        config_key = str(getattr(factory, "config_key", public_name.removesuffix("-cloud")))
        provider_config = cloud_config.get(config_key, {})
        if not isinstance(provider_config, dict):
            unavailable[public_name] = f"cloud.{config_key} must be a TOML table"
            continue
        if not provider_config.get("enabled", False):
            unavailable.setdefault(public_name, f"disabled; configure [cloud.{config_key}]")
            continue
        if dependency:
            try:
                importlib.import_module(dependency)
            except ImportError:
                unavailable[public_name] = f"missing optional dependency: {dependency}"
                continue
        try:
            loaded.append(_instantiate_external(factory, provider_config, read_secret))
        except Exception as exc:  # noqa: BLE001 - provider isolation boundary
            unavailable[public_name] = f"configuration error: {exc}"
    return loaded, unavailable


def cloud_plugin_catalog() -> dict[str, str]:
    """Return built-in plus discoverable third-party cloud plugin descriptions."""
    result = {plugin.name: plugin.description for plugin in BUILTIN_CLOUD_PLUGINS}
    for ep in entry_points(group="ble_sensors_mqtt.cloud_plugins"):
        result.setdefault(ep.name, "Third-party cloud plugin")
    return result


def cloud_help() -> str:
    return """Cloud plugins:
Third-party providers can register the ble_sensors_mqtt.cloud_plugins entry-point group.
Each provider reads its configuration from a [cloud.<provider>] TOML table and is isolated
from BLE collection failures.

Tuya Cloud:
1. Create a Smart Home project in the Tuya IoT portal and link the mobile app account.
2. Copy the Access ID, Access Secret, region, and one reference device ID.
3. Store the ID and secret in separate files and run chmod 600 on each file.
4. Create the TOML file shown in README.en.md and start with --cloud-config /path/cloud.toml.
Tuya sensors advertising BTHome may instead work locally through the bthome plugin.
"""
