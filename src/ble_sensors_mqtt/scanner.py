"""Single-pass BLE scanner dispatching advertisements to isolated plugins."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from .plugin_api import SensorPlugin, SensorReading

LOG = logging.getLogger("ble_sensors_mqtt.scanner")


async def _decode_with_timeout(
    plugin: SensorPlugin,
    device: Any,
    advertisement: Any,
    timeout: float,
) -> list[SensorReading]:
    decoder = getattr(plugin, "decode_async", None)
    if decoder:
        return await asyncio.wait_for(decoder(device, advertisement), timeout=timeout)
    return await asyncio.wait_for(
        asyncio.to_thread(plugin.decode, device, advertisement), timeout=timeout
    )


async def scan(
    duration: float,
    plugins: list[SensorPlugin],
    decode_timeout: float = 15.0,
    adapter: str | None = None,
) -> list[SensorReading]:
    if not plugins:
        return []

    from bleak import BleakScanner

    advertisements: dict[str, tuple[Any, Any]] = {}

    def detected(device: Any, advertisement: Any) -> None:
        advertisements[device.address.upper()] = (device, advertisement)

    scanner_kwargs: dict[str, Any] = {}
    if adapter:
        if not sys.platform.startswith("linux"):
            raise ValueError("--bluetooth-adapter is currently supported only on Linux/BlueZ")
        scanner_kwargs["bluez"] = {"adapter": adapter}
    scanner = BleakScanner(detection_callback=detected, **scanner_kwargs)
    await scanner.start()
    try:
        await asyncio.sleep(duration)
    finally:
        await scanner.stop()

    readings: dict[str, SensorReading] = {}
    for device, advertisement in advertisements.values():
        for plugin in plugins:
            try:
                decoded = await _decode_with_timeout(plugin, device, advertisement, decode_timeout)
                for reading in decoded:
                    readings.setdefault(reading.address.upper(), reading)
            except TimeoutError:
                LOG.warning("plugin %s timed out decoding %s", plugin.name, device.address)
            except Exception as exc:  # noqa: BLE001 - isolate third-party plugins
                LOG.debug("plugin %s did not decode %s: %s", plugin.name, device.address, exc)
    return list(readings.values())
