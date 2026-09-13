import json

from ble_sensors_mqtt.cli import parser
from ble_sensors_mqtt.homeassistant import discovery_messages


def sample_payload():
    return {
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "Sala Server",
        "bluetooth_name": "Meter Plus",
        "manufacturer": "SwitchBot",
        "model": "Meter Plus",
        "protocol": "SwitchBot BLE",
        "rssi": -61,
        "observed_at": "2026-09-13T00:00:00+00:00",
        "data": {
            "temperature": 22.4,
            "humidity": 49,
            "battery": 87,
            "co2": 612,
            "units": {"temperature": "°C", "humidity": "%", "co2": "ppm"},
            "nested": {"channel_1": 12.3},
            "software_version": "1.2.3",
        },
    }


def decode_messages():
    messages = discovery_messages(
        discovery_prefix="homeassistant",
        mqtt_prefix="ble-sensors",
        address="AA:BB:CC:DD:EE:FF",
        payload=sample_payload(),
    )
    return messages, {topic: json.loads(payload) for topic, payload in messages.items()}


def test_home_assistant_cli_options_are_optional_and_configurable():
    args = parser().parse_args(["--mqtt-host", "127.0.0.1"])
    assert args.home_assistant_discovery is False
    assert args.home_assistant_discovery_prefix == "homeassistant"

    args = parser().parse_args([
        "--mqtt-host", "127.0.0.1",
        "--home-assistant-discovery",
        "--home-assistant-discovery-prefix", "ha",
    ])
    assert args.home_assistant_discovery is True
    assert args.home_assistant_discovery_prefix == "ha"


def test_discovery_creates_entities_with_common_device_and_availability():
    messages, decoded = decode_messages()
    assert messages
    assert all(topic.startswith("homeassistant/sensor/") and topic.endswith("/config") for topic in messages)
    temperature = next(item for item in decoded.values() if item["name"] == "Temperature")
    assert temperature["state_topic"] == "ble-sensors/aabbccddeeff/state"
    assert temperature["value_template"] == '{{ value_json["data"]["temperature"] }}'
    assert temperature["availability_topic"] == "ble-sensors/bridge/status"
    assert temperature["device_class"] == "temperature"
    assert temperature["unit_of_measurement"] == "°C"
    assert temperature["state_class"] == "measurement"
    assert temperature["device"]["name"] == "Sala Server"
    assert temperature["device"]["manufacturer"] == "SwitchBot"
    assert temperature["device"]["model"] == "Meter Plus"


def test_discovery_covers_generic_nested_scalars_and_diagnostics():
    _messages, decoded = decode_messages()
    configs = list(decoded.values())
    nested = next(item for item in configs if item["name"] == "Channel 1")
    assert nested["value_template"] == '{{ value_json["data"]["nested"]["channel_1"] }}'
    rssi = next(item for item in configs if item["name"] == "Rssi")
    assert rssi["device_class"] == "signal_strength"
    assert rssi["unit_of_measurement"] == "dBm"
    assert rssi["entity_category"] == "diagnostic"
    protocol = next(item for item in configs if item["name"] == "Protocol")
    assert protocol["value_template"] == '{{ value_json["protocol"] }}'
    assert protocol["entity_category"] == "diagnostic"


def test_unique_ids_do_not_depend_on_friendly_name():
    payload_a = sample_payload()
    payload_b = sample_payload()
    payload_b["name"] = "Nuovo Nome"
    a = discovery_messages(
        discovery_prefix="homeassistant", mqtt_prefix="ble-sensors",
        address="AA:BB:CC:DD:EE:FF", payload=payload_a,
    )
    b = discovery_messages(
        discovery_prefix="homeassistant", mqtt_prefix="ble-sensors",
        address="AA:BB:CC:DD:EE:FF", payload=payload_b,
    )
    assert set(a) == set(b)
    assert {json.loads(v)["unique_id"] for v in a.values()} == {
        json.loads(v)["unique_id"] for v in b.values()
    }


def test_stale_diagnostic_entity_is_exposed_when_feature_marks_payload():
    payload = sample_payload()
    payload["stale"] = True
    messages = discovery_messages(
        discovery_prefix="homeassistant",
        mqtt_prefix="ble-sensors",
        address="AA:BB:CC:DD:EE:FF",
        payload=payload,
    )
    decoded = [json.loads(item) for item in messages.values()]
    stale = next(item for item in decoded if item["name"] == "Stale")
    assert stale["entity_category"] == "diagnostic"
    assert 'value_json.get("stale", false)' in stale["value_template"]


def test_presence_motion_occupancy_are_binary_sensors():
    payload = sample_payload()
    payload["data"].update({
        "presence": True,
        "motion": False,
        "occupancy": 1,
        "moving": "false",
        "moveDetected": True,
    })
    messages = discovery_messages(
        discovery_prefix="homeassistant",
        mqtt_prefix="ble-sensors",
        address="AA:BB:CC:DD:EE:FF",
        payload=payload,
    )
    decoded = {topic: json.loads(value) for topic, value in messages.items()}
    expected = {
        "Presence": "presence",
        "Motion": "motion",
        "Occupancy": "occupancy",
        "Moving": "moving",
        "Movedetected": "motion",
    }
    for name, device_class in expected.items():
        topic, config = next((topic, config) for topic, config in decoded.items() if config["name"] == name)
        assert topic.startswith("homeassistant/binary_sensor/")
        assert config["device_class"] == device_class
        assert config["payload_on"] == "ON"
        assert config["payload_off"] == "OFF"
        assert "'ON'" in config["value_template"]
