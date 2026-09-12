from argparse import ArgumentTypeError
from types import SimpleNamespace

import pytest

from ble_sensors_mqtt.cli import (
    apply_device_names,
    bind_address,
    device_address,
    device_name,
    load_bindkeys,
    name_map,
    normalize,
    parser,
    positive_seconds,
    reading_payload,
    sensor_identifier,
    sensor_name,
    topic_part,
)
from ble_sensors_mqtt.plugin_api import SensorReading


def test_positive_seconds_rejects_invalid_values():
    for value in ("0", "nan", "inf", "86401", "text"):
        with pytest.raises(ArgumentTypeError):
            positive_seconds(value)


def test_topic_part_removes_separators():
    assert topic_part("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"


def test_normalize_extracts_payload():
    item = SimpleNamespace(
        data={"temperature": 21.5, "humidity": 48, "battery": 91},
        device=SimpleNamespace(name="Meter"),
        rssi=-62,
    )
    result = normalize("aa:bb:cc:dd:ee:ff", item)
    assert result["address"] == "AA:BB:CC:DD:EE:FF"
    assert result["name"] == "Meter"
    assert result["data"]["temperature"] == 21.5


def test_exporter_addresses_and_ports_are_configurable():
    args = parser().parse_args([
        "--mqtt-host", "192.0.2.10",
        "--prometheus", "--prometheus-host", "0.0.0.0", "--prometheus-port", "9200",
        "--snmp", "--snmp-host", "::", "--snmp-port", "2161",
        "--snmp-community-file", "/run/secrets/snmp-community",
    ])
    assert (args.prometheus_host, args.prometheus_port) == ("0.0.0.0", 9200)
    assert (args.snmp_host, args.snmp_port) == ("::", 2161)


def test_bind_address_accepts_ipv4_and_ipv6():
    assert bind_address("192.0.2.5") == "192.0.2.5"
    assert bind_address("::") == "::"


def test_device_name_is_normalized_and_applied():
    aliases = name_map([device_name("aa-bb-cc-dd-ee-ff=Sala Server")])
    devices = {
        "AA:BB:CC:DD:EE:FF": {"name": "Meter Plus", "data": {"temperature": 23.4}}
    }
    result = apply_device_names(devices, aliases)
    assert result["AA:BB:CC:DD:EE:FF"]["name"] == "Sala Server"
    assert result["AA:BB:CC:DD:EE:FF"]["bluetooth_name"] == "Meter Plus"


def test_duplicate_device_name_is_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        name_map([
            ("AA:BB:CC:DD:EE:FF", "Sala"),
            ("AA:BB:CC:DD:EE:FF", "Ufficio"),
        ])


def test_device_address_rejects_invalid_mac():
    with pytest.raises(ArgumentTypeError):
        device_address("not-a-mac")


def test_normalized_plugin_reading_always_has_identity():
    payload = reading_payload(SensorReading(
        address="TUYA:abc", name="Cantina", manufacturer="Tuya", model="TH01",
        protocol="Tuya Cloud", data={"temperature": 20.1},
    ))
    assert payload["manufacturer"] == "Tuya"
    assert payload["model"] == "TH01"
    assert payload["protocol"] == "Tuya Cloud"


def test_sensor_name_accepts_cloud_identifier():
    assert sensor_name("tuya:abc=Cantina") == ("TUYA:ABC", "Cantina")


def test_load_bindkeys_reads_protected_hex_file(tmp_path):
    secret = tmp_path / "bindkey"
    secret.write_text("00112233445566778899aabbccddeeff", encoding="utf-8")
    secret.chmod(0o600)
    result = load_bindkeys({"ble_keys": {"aa:bb:cc:dd:ee:ff": {
        "plugin": "bthome", "bindkey_file": str(secret),
    }}})
    assert result["bthome"]["AA:BB:CC:DD:EE:FF"] == bytes.fromhex(secret.read_text())


def test_sensor_identifier_accepts_ble_and_cloud_ids():
    assert sensor_identifier("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert sensor_identifier("tuya:abc123") == "TUYA:ABC123"


def test_device_option_accepts_cloud_identifier():
    args = parser().parse_args(["--mqtt-host", "127.0.0.1", "--device", "tuya:abc123"])
    assert args.device == ["TUYA:ABC123"]
