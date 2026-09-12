"""Public API for built-in and third-party sensor plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class SensorReading:
    """Normalized reading exported by every plugin."""

    address: str
    name: str
    manufacturer: str
    model: str
    protocol: str
    rssi: int | float | None = None
    data: dict[str, Any] = field(default_factory=dict)
    bluetooth_name: str | None = None


class SensorPlugin(Protocol):
    """Interface implemented by local BLE plugins."""

    name: str

    def decode(self, device: Any, advertisement: Any) -> list[SensorReading]: ...


class CloudPlugin(Protocol):
    """Interface implemented by cloud polling plugins."""

    name: str

    async def poll(self) -> list[SensorReading]: ...

