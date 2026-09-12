import argparse
import json
import urllib.error
import urllib.request

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
