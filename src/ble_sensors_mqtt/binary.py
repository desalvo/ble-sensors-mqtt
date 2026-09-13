"""Shared binary-sensor semantics for presence, occupancy, and motion."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


def _key(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


BINARY_CLASSES: dict[str, tuple[str, ...]] = {
    "presence": (
        "presence",
        "presence_detected",
        "human_presence",
        "human_detected",
        "person_present",
        "person_detected",
        "detected",
    ),
    "motion": (
        "motion",
        "motion_detected",
        "move_detected",
        "movedetected",
        "pir",
        "pir_detected",
        "detection_state",
    ),
    "occupancy": (
        "occupancy",
        "occupied",
        "occupancy_detected",
        "room_occupied",
    ),
    "moving": (
        "moving",
        "movement",
        "movement_detected",
        "is_moving",
    ),
}

_ALIAS_TO_CLASS = {
    _key(alias): device_class
    for device_class, aliases in BINARY_CLASSES.items()
    for alias in aliases
}

_TRUE_STRINGS = {
    "1", "true", "on", "yes", "active", "detected", "present", "occupied", "moving",
}
_FALSE_STRINGS = {
    "0", "false", "off", "no", "inactive", "clear", "not_detected", "not detected",
    "absent", "not_present", "not present", "unoccupied", "not_occupied", "not occupied",
    "stationary", "not_moving", "not moving",
}


def binary_device_class(name: str) -> str | None:
    """Return Home Assistant binary-sensor class for a known key."""
    return _ALIAS_TO_CLASS.get(_key(name))


def coerce_binary(value: Any) -> bool | None:
    """Coerce a conventional binary sensor value without guessing arbitrary strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 0:
            return False
        if value == 1:
            return True
        return None
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_")
        if normalized in _TRUE_STRINGS:
            return True
        if normalized in _FALSE_STRINGS:
            return False
    return None


def find_binary(payload: Mapping[str, Any], device_class: str) -> bool | None:
    """Find the first recognized binary state for one semantic class recursively."""
    aliases = {_key(alias) for alias in BINARY_CLASSES.get(device_class, ())}
    if not aliases:
        return None
    stack: list[Any] = [payload.get("data", {})]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key, value in current.items():
                if _key(str(key)) in aliases:
                    state = coerce_binary(value)
                    if state is not None:
                        return state
                if isinstance(value, (Mapping, list, tuple)):
                    stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current[:100])
    return None
