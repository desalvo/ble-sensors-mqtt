import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ble_sensors_mqtt import __version__
from ble_sensors_mqtt.cli import (
    _safe,
    load_runtime_state,
    parser,
    read_secret,
    save_runtime_state,
    topic_part,
    topic_prefix,
    validate_runtime_security,
)
from ble_sensors_mqtt.metrics import SensorStore
from ble_sensors_mqtt.prometheus import start


def test_version_is_centralized(capsys):
    assert __version__ == "1.0.0"
    with pytest.raises(SystemExit) as exc:
        parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert "1.0.0" in capsys.readouterr().out


def test_topic_prefix_rejects_wildcards_and_empty_values():
    for value in ("", "/", "foo/#", "foo/+", "bad\x00topic"):
        with pytest.raises(argparse.ArgumentTypeError):
            topic_prefix(value)
    assert topic_prefix("/production/sensors/") == "production/sensors"



def test_non_mac_topic_parts_are_collision_resistant():
    assert topic_part("TUYA:a/b") != topic_part("TUYA:a_b")
    assert topic_part("TUYA:a/b").startswith("tuya_a_b_")


def test_safe_bounds_untrusted_plugin_strings_and_maps():
    payload = _safe({"message": "x" * 5000, **{f"k{i}": i for i in range(400)}})
    assert len(payload["message"]) == 4096
    assert len(payload) == 256


def test_secret_must_be_regular_and_private(tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("value", encoding="utf-8")
    secret.chmod(0o644)
    with pytest.raises(ValueError, match="0640"):
        read_secret(secret, "secret")
    secret.chmod(0o640)
    assert read_secret(secret, "secret") == "value"
    link = tmp_path / "secret-link"
    link.symlink_to(secret)
    with pytest.raises(ValueError, match="securely"):
        read_secret(link, "secret")



def test_runtime_security_is_fail_closed_for_network_exposure():
    args = parser().parse_args(["--mqtt-host", "192.0.2.10"])
    with pytest.raises(ValueError, match="plaintext MQTT"):
        validate_runtime_security(args)

    args = parser().parse_args(["--mqtt-host", "192.0.2.10", "--allow-insecure-mqtt"])
    validate_runtime_security(args)

    args = parser().parse_args([
        "--mqtt-host", "127.0.0.1",
        "--prometheus",
        "--prometheus-host", "0.0.0.0",
    ])
    with pytest.raises(ValueError, match="external Prometheus"):
        validate_runtime_security(args)

    args = parser().parse_args([
        "--mqtt-host", "127.0.0.1",
        "--snmp",
        "--snmp-host", "0.0.0.0",
    ])
    with pytest.raises(ValueError, match="external SNMPv2c"):
        validate_runtime_security(args)


def test_runtime_state_round_trip_is_atomic_and_private(tmp_path):
    path = tmp_path / "state.json"
    topics = {"ble-sensors/a/state", "ble-sensors/b/state"}
    missing = {"ble-sensors/b/state": 2}
    save_runtime_state(path, "ble-sensors", topics, missing)
    assert path.stat().st_mode & 0o777 == 0o600
    loaded_topics, loaded_missing = load_runtime_state(path, "ble-sensors")
    assert loaded_topics == topics
    assert loaded_missing == missing
    other_topics, other_missing = load_runtime_state(path, "other-prefix")
    assert other_topics == set()
    assert other_missing == {}


def test_health_state_transitions():
    store = SensorStore()
    health = store.health(30)
    assert health["alive"] is True
    assert health["ready"] is False
    store.mark_failure("temporary failure")
    assert store.health()["cycles_failed"] == 1
    store.mark_success()
    health = store.health(30)
    assert health["ready"] is True
    assert health["cycles_total"] == 2
    assert health["last_error"] is None


def test_http_health_and_readiness_endpoints():
    store = SensorStore()
    server = start(store, "127.0.0.1", 0, ready_max_age=30)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as response:
            assert response.status == 200
            assert json.load(response)["alive"] is True
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=2)
        assert exc.value.code == 503
        store.mark_success()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=2) as response:
            assert response.status == 200
            assert json.load(response)["ready"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_sync_plugin_decode_is_timeout_bounded(monkeypatch):
    import asyncio
    import time
    from types import SimpleNamespace

    import ble_sensors_mqtt.scanner as scanner_module

    class FakeScanner:
        def __init__(self, detection_callback):
            self.callback = detection_callback

        async def start(self):
            self.callback(
                SimpleNamespace(address="AA:BB:CC:DD:EE:FF"),
                SimpleNamespace(),
            )

        async def stop(self):
            return None

    class SlowPlugin:
        name = "slow"

        def decode(self, _device, _advertisement):
            time.sleep(0.2)
            return []

    fake_bleak = SimpleNamespace(BleakScanner=FakeScanner)
    monkeypatch.setitem(__import__("sys").modules, "bleak", fake_bleak)
    async def run_once():
        started = time.monotonic()
        result = await scanner_module.scan(0.01, [SlowPlugin()], decode_timeout=0.05)
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(run_once())
    assert result == []
    assert elapsed < 0.18



def test_scanner_keeps_latest_decoded_reading(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import ble_sensors_mqtt.scanner as scanner_module
    from ble_sensors_mqtt.plugin_api import SensorReading

    class FakeScanner:
        def __init__(self, detection_callback):
            self.callback = detection_callback

        async def start(self):
            device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF")
            self.callback(device, SimpleNamespace(temperature=20.0))
            self.callback(device, SimpleNamespace(temperature=21.5))

        async def stop(self):
            return None

    class TemperaturePlugin:
        name = "temperature"

        def decode(self, device, advertisement):
            return [
                SensorReading(
                    address=device.address,
                    name="Room",
                    manufacturer="Test",
                    model="T1",
                    protocol="BLE",
                    data={"temperature": advertisement.temperature},
                )
            ]

    monkeypatch.setitem(
        __import__("sys").modules, "bleak", SimpleNamespace(BleakScanner=FakeScanner)
    )
    readings = asyncio.run(scanner_module.scan(0.001, [TemperaturePlugin()]))
    assert len(readings) == 1
    assert readings[0].data["temperature"] == 21.5

def test_stale_reuse_cli_and_payload_behavior():
    from ble_sensors_mqtt.cli import apply_stale_fallback

    args = parser().parse_args(["--mqtt-host", "127.0.0.1", "--reuse-stale-data"])
    assert args.reuse_stale_data is True

    previous = {
        "AA:BB:CC:DD:EE:FF": {
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Room",
            "observed_at": "2026-09-13T00:00:00+00:00",
            "data": {"temperature": 22.5},
        }
    }
    counters: dict[str, int] = {}
    for missed_cycle in range(1, 10):
        reused = apply_stale_fallback({}, previous, True, counters, 10)
        assert reused["AA:BB:CC:DD:EE:FF"]["stale"] is False
        assert counters["AA:BB:CC:DD:EE:FF"] == missed_cycle
    reused = apply_stale_fallback({}, previous, True, counters, 10)
    assert reused["AA:BB:CC:DD:EE:FF"]["stale"] is True
    assert counters["AA:BB:CC:DD:EE:FF"] == 10
    assert reused["AA:BB:CC:DD:EE:FF"]["data"]["temperature"] == 22.5
    assert reused["AA:BB:CC:DD:EE:FF"]["observed_at"] == "2026-09-13T00:00:00+00:00"

    fresh = apply_stale_fallback(
        {
            "AA:BB:CC:DD:EE:FF": {
                "address": "AA:BB:CC:DD:EE:FF",
                "data": {"temperature": 23.0},
            }
        },
        previous,
        True,
        counters,
        10,
    )
    assert fresh["AA:BB:CC:DD:EE:FF"]["stale"] is False
    assert fresh["AA:BB:CC:DD:EE:FF"]["data"]["temperature"] == 23.0
    assert "AA:BB:CC:DD:EE:FF" not in counters

    disabled = apply_stale_fallback({}, previous, False)
    assert disabled == {}



def test_sensor_retry_and_stale_defaults():
    args = parser().parse_args(["--mqtt-host", "127.0.0.1"])
    assert args.sensor_retry_attempts == 3
    assert args.scan_duration == 10.0
    assert args.sensor_stale_cycles == 10

def test_mqtt_cache_is_bounded_fifo_and_private(tmp_path):
    from ble_sensors_mqtt.mqtt_cache import MQTTCache

    path = tmp_path / "mqtt-cache.sqlite3"
    cache = MQTTCache(path, 1_048_576)
    try:
        assert path.stat().st_mode & 0o777 == 0o600
        cache.enqueue("a/topic", b"one", 1, True)
        cache.enqueue("b/topic", b"two", 0, False)
        messages = cache.oldest()
        assert [item.topic for item in messages] == ["a/topic", "b/topic"]
        assert messages[0].payload == b"one"
        cache.delete(messages[0].id)
        assert [item.topic for item in cache.oldest()] == ["b/topic"]
    finally:
        cache.close()


def test_mqtt_cache_cli_defaults_and_size_parser(tmp_path):
    from ble_sensors_mqtt.cli import byte_size, mqtt_cache_path

    assert byte_size("1GiB") == 1024**3
    assert byte_size("500MB") == 500_000_000
    args = parser().parse_args([
        "--mqtt-host", "127.0.0.1",
        "--state-file", str(tmp_path / "state.json"),
    ])
    assert args.mqtt_cache is True
    assert args.mqtt_cache_max_size == 1024**3
    assert mqtt_cache_path(args) == tmp_path / "mqtt-cache.sqlite3"


def test_linux_adapter_is_forwarded_to_bleak(monkeypatch):
    import sys
    import types

    from ble_sensors_mqtt import scanner as scanner_module

    captured = {}

    class FakeScanner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def start(self):
            return None

        async def stop(self):
            return None

    fake_bleak = types.SimpleNamespace(BleakScanner=FakeScanner)
    monkeypatch.setitem(sys.modules, "bleak", fake_bleak)
    monkeypatch.setattr(scanner_module.sys, "platform", "linux")

    class Plugin:
        name = "dummy"

        def decode(self, _device, _advertisement):
            return []

    import asyncio
    assert asyncio.run(scanner_module.scan(0.001, [Plugin()], adapter="hci1")) == []
    assert captured["bluez"] == {"adapter": "hci1"}


def test_sensor_store_exposes_polling_idle_margin():
    from ble_sensors_mqtt.metrics import SensorStore

    store = SensorStore()
    store.record_cycle_timing(20.0, 10.0, 30.0)
    store.record_cycle_timing(21.0, 9.0, 30.0)
    health = store.health()
    assert health["average_idle_seconds"] == 9.5
    assert health["poll_interval_seconds"] == 30.0
    assert health["polling_margin_status"] == "sufficient"

    tight = SensorStore()
    tight.record_cycle_timing(28.0, 2.0, 30.0)
    assert tight.health()["polling_margin_status"] == "tight"

    insufficient = SensorStore()
    insufficient.record_cycle_timing(31.0, 0.0, 30.0)
    assert insufficient.health()["polling_margin_status"] == "insufficient"



def test_sensor_store_exposes_average_internal_retries():
    from ble_sensors_mqtt.metrics import SensorStore

    store = SensorStore()
    store.record_internal_retries(0, 2)
    store.record_internal_retries(1, 2)
    health = store.health()
    assert health["average_internal_retries"] == 0.5
    assert health["max_internal_retries"] == 2
    assert health["internal_retry_status"] == "tight"

    low = SensorStore()
    low.record_internal_retries(0, 2)
    assert low.health()["internal_retry_status"] == "sufficient"

    high = SensorStore()
    high.record_internal_retries(2, 2)
    assert high.health()["internal_retry_status"] == "insufficient"

def test_stale_fallback_records_stale_since_and_clears_it_on_fresh_data():
    from ble_sensors_mqtt.cli import apply_stale_fallback

    previous = {"AA": {"data": {"temperature": 21.0}, "observed_at": "2026-09-13T00:00:00+00:00", "stale": False}}
    counters = {}
    current = apply_stale_fallback({}, previous, True, counters, 2)
    assert current["AA"]["stale"] is False
    assert "stale_since" not in current["AA"]
    current = apply_stale_fallback({}, current, True, counters, 2)
    assert current["AA"]["stale"] is True
    assert current["AA"]["stale_since"]
    stale_since = current["AA"]["stale_since"]
    current = apply_stale_fallback({}, current, True, counters, 2)
    assert current["AA"]["stale_since"] == stale_since
    fresh = apply_stale_fallback({"AA": {"data": {"temperature": 22.0}}}, current, True, counters, 2)
    assert fresh["AA"]["stale"] is False
    assert "stale_since" not in fresh["AA"]


def test_dashboard_shows_stale_duration_and_polling_margin():
    template = Path("src/ble_sensors_mqtt/web_templates/dashboard.html").read_text(encoding="utf-8")
    assert "stale_since" in template
    assert "average_idle_seconds" in template
    assert "polling_margin_status" in template
    assert "Insufficient polling interval" in template
    assert "polling-idle-seconds" in template
    assert "average_internal_retries" in template
    assert "internal_retry_status" in template
    assert "Average retries" in template
