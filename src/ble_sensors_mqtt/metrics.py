"""Thread-safe sensor snapshot and runtime health shared by exporters."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


class SensorStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: dict[str, dict[str, Any]] = {}
        self._started_monotonic = time.monotonic()
        self._last_success_monotonic: float | None = None
        self._last_success_at: str | None = None
        self._last_error_at: str | None = None
        self._last_error: str | None = None
        self._cycles_total = 0
        self._cycles_failed = 0
        self._cycle_durations: deque[float] = deque(maxlen=30)
        self._idle_durations: deque[float] = deque(maxlen=30)
        self._poll_interval_seconds: float | None = None
        self._internal_retries: deque[int] = deque(maxlen=30)
        self._max_internal_retries: int = 0

    def replace(self, devices: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            self._devices = deepcopy(devices)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return deepcopy(self._devices)

    def mark_success(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._cycles_total += 1
            self._last_success_monotonic = time.monotonic()
            self._last_success_at = now
            self._last_error = None

    def mark_failure(self, error: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._cycles_total += 1
            self._cycles_failed += 1
            self._last_error_at = now
            self._last_error = error[:512]


    def record_cycle_timing(self, cycle_duration: float, idle_duration: float, poll_interval: float) -> None:
        """Record recent runtime timing used to expose actual polling headroom."""
        with self._lock:
            self._cycle_durations.append(max(0.0, float(cycle_duration)))
            self._idle_durations.append(max(0.0, float(idle_duration)))
            self._poll_interval_seconds = max(0.0, float(poll_interval))

    def record_internal_retries(self, retries: int, max_retries: int) -> None:
        """Record acquisition retry windows used by a completed polling cycle."""
        with self._lock:
            self._internal_retries.append(max(0, int(retries)))
            self._max_internal_retries = max(0, int(max_retries))

    def health(self, ready_max_age: float | None = None) -> dict[str, Any]:
        with self._lock:
            age = (
                None
                if self._last_success_monotonic is None
                else max(0.0, time.monotonic() - self._last_success_monotonic)
            )
            ready = self._last_success_monotonic is not None
            if ready and ready_max_age is not None and age is not None:
                ready = age <= ready_max_age
            avg_idle = (sum(self._idle_durations) / len(self._idle_durations)) if self._idle_durations else None
            avg_cycle = (sum(self._cycle_durations) / len(self._cycle_durations)) if self._cycle_durations else None
            poll_interval = self._poll_interval_seconds
            avg_retries = (
                sum(self._internal_retries) / len(self._internal_retries)
                if self._internal_retries
                else None
            )
            max_retries = self._max_internal_retries
            if avg_retries is None:
                retry_status = "unknown"
            elif avg_retries <= 0.25:
                retry_status = "sufficient"
            elif max_retries > 0 and avg_retries >= max_retries * 0.80:
                retry_status = "insufficient"
            else:
                retry_status = "tight"
            idle_ratio = None if avg_idle is None or not poll_interval else avg_idle / poll_interval
            if avg_idle is None:
                margin_status = "unknown"
            elif avg_idle <= 0.01:
                margin_status = "insufficient"
            elif idle_ratio is not None and idle_ratio < 0.10:
                margin_status = "tight"
            else:
                margin_status = "sufficient"
            return {
                "alive": True,
                "ready": ready,
                "uptime_seconds": max(0.0, time.monotonic() - self._started_monotonic),
                "last_success_age_seconds": age,
                "last_success_at": self._last_success_at,
                "last_error_at": self._last_error_at,
                "last_error": self._last_error,
                "cycles_total": self._cycles_total,
                "cycles_failed": self._cycles_failed,
                "average_cycle_duration_seconds": avg_cycle,
                "average_idle_seconds": avg_idle,
                "poll_interval_seconds": poll_interval,
                "polling_idle_ratio": idle_ratio,
                "polling_margin_status": margin_status,
                "average_internal_retries": avg_retries,
                "max_internal_retries": max_retries,
                "internal_retry_status": retry_status,
                "devices": len(self._devices),
            }


def find_number(payload: dict[str, Any], *names: str) -> float | None:
    """Find a finite numeric field recursively, case-insensitively."""
    wanted = {name.lower() for name in names}
    stack: list[Any] = [payload.get("data", {})]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if (
                    str(key).lower() in wanted
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                ):
                    number = float(value)
                    if math.isfinite(number):
                        return number
                if isinstance(value, (dict, list, tuple)):
                    stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current[:100])
    return None


def scalar_values(payload: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """Flatten all bounded scalar sensor values as (path, unit, value)."""
    result: list[tuple[str, str, Any]] = []
    units = payload.get("data", {}).get("units", {})
    stack: list[tuple[str, Any]] = [("", payload.get("data", {}))]
    while stack and len(result) < 256:
        prefix, current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key == "units":
                    continue
                path = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, (dict, list, tuple)):
                    stack.append((path, value))
                elif value is None or isinstance(value, (str, bool, int, float)):
                    unit = str(units.get(key, "")) if isinstance(units, dict) else ""
                    result.append((path, unit, value))
        elif isinstance(current, (list, tuple)):
            for index, value in enumerate(current[:100]):
                stack.append((f"{prefix}.{index}", value))
    return sorted(result)
