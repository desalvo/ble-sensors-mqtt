"""Small dependency-free Prometheus and health HTTP exporter."""

from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .binary import find_binary
from .metrics import SensorStore, find_number, scalar_values

LOG = logging.getLogger("ble_sensors_mqtt.prometheus")


def _escape(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def render(store: SensorStore) -> bytes:
    devices = store.snapshot()
    health = store.health()
    lines = [
        "# HELP ble_sensors_up Whether a sensor was observed with fresh data in the latest successful scan.",
        "# TYPE ble_sensors_up gauge",
        "# HELP ble_sensors_stale Whether the exported sensor snapshot is reused from a previous cycle.",
        "# TYPE ble_sensors_stale gauge",
        "# HELP ble_sensors_sensor_value Numeric or boolean value exposed by a sensor plugin.",
        "# TYPE ble_sensors_sensor_value gauge",
        "# HELP ble_sensors_sensor_info Non-numeric value exposed by a sensor plugin.",
        "# TYPE ble_sensors_sensor_info gauge",
        "# HELP ble_sensors_cycles_total Polling cycles attempted by the gateway.",
        "# TYPE ble_sensors_cycles_total counter",
        f"ble_sensors_cycles_total {health['cycles_total']}",
        "# HELP ble_sensors_cycles_failed_total Polling cycles that failed.",
        "# TYPE ble_sensors_cycles_failed_total counter",
        f"ble_sensors_cycles_failed_total {health['cycles_failed']}",
    ]
    definitions = (
        ("temperature_celsius", "Temperature in degrees Celsius.", ("temperature",)),
        ("humidity_percent", "Relative humidity in percent.", ("humidity",)),
        ("battery_percent", "Battery charge in percent.", ("battery", "battery_percent")),
        ("rssi_dbm", "Bluetooth received signal strength in dBm.", ("__rssi__",)),
    )
    binary_definitions = (
        ("presence", "Human/person presence state (1 present, 0 absent).", "presence"),
        ("motion", "Motion detection state (1 detected, 0 clear).", "motion"),
        ("occupancy", "Occupancy state (1 occupied, 0 unoccupied).", "occupancy"),
        ("moving", "Moving state (1 moving, 0 stationary).", "moving"),
    )
    for metric, help_text, _ in definitions:
        lines.extend((f"# HELP ble_sensors_{metric} {help_text}", f"# TYPE ble_sensors_{metric} gauge"))
    for metric, help_text, _ in binary_definitions:
        lines.extend((f"# HELP ble_sensors_{metric} {help_text}", f"# TYPE ble_sensors_{metric} gauge"))
    for address, payload in sorted(devices.items()):
        labels = ",".join((
            f'address="{_escape(address)}"', f'name="{_escape(payload.get("name"))}"',
            f'manufacturer="{_escape(payload.get("manufacturer"))}"',
            f'model="{_escape(payload.get("model"))}"',
            f'protocol="{_escape(payload.get("protocol"))}"',
        ))
        stale = bool(payload.get("stale"))
        lines.append(f"ble_sensors_up{{{labels}}} {0 if stale else 1}")
        lines.append(f"ble_sensors_stale{{{labels}}} {1 if stale else 0}")
        for metric, _, names in definitions:
            value = payload.get("rssi") if names == ("__rssi__",) else find_number(payload, *names)
            if isinstance(value, (int, float)):
                lines.append(f"ble_sensors_{metric}{{{labels}}} {value}")
        for metric, _, device_class in binary_definitions:
            value = find_binary(payload, device_class)
            if value is not None:
                lines.append(f"ble_sensors_{metric}{{{labels}}} {1 if value else 0}")
        for key, unit, value in scalar_values(payload):
            extra = f'{labels},key="{_escape(key)}",unit="{_escape(unit)}"'
            if isinstance(value, bool):
                lines.append(f"ble_sensors_sensor_value{{{extra}}} {int(value)}")
            elif isinstance(value, (int, float)):
                lines.append(f"ble_sensors_sensor_value{{{extra}}} {value}")
            elif value is not None:
                lines.append(f'ble_sensors_sensor_info{{{extra},value="{_escape(value)}"}} 1')
    lines.extend((
        "# HELP ble_sensors_devices Number of sensors in the latest successful scan.",
        "# TYPE ble_sensors_devices gauge",
        f"ble_sensors_devices {len(devices)}",
    ))
    return ("\n".join(lines) + "\n").encode("utf-8")


def start(
    store: SensorStore,
    host: str,
    port: int,
    ready_max_age: float = 180.0,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/metrics":
                self._send(200, render(store), "text/plain; version=0.0.4; charset=utf-8")
                return
            if path in ("/healthz", "/readyz"):
                health = store.health(ready_max_age if path == "/readyz" else None)
                status = 200 if path == "/healthz" or health["ready"] else 503
                body = (json.dumps(health, separators=(",", ":")) + "\n").encode("utf-8")
                self._send(status, body, "application/json; charset=utf-8")
                return
            self.send_error(404)

        def log_message(self, fmt: str, *args: object) -> None:
            LOG.debug(fmt, *args)

    server_class = ThreadingHTTPServer
    if ":" in host:
        class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
            address_family = socket.AF_INET6

        server_class = IPv6ThreadingHTTPServer
    server = server_class((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="prometheus-exporter", daemon=True).start()
    LOG.info("Prometheus/health HTTP server listening on http://%s:%d", host, port)
    return server
