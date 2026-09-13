from ble_sensors_mqtt.metrics import SensorStore
from ble_sensors_mqtt.prometheus import render
from ble_sensors_mqtt.snmp import _integer, _oid, _tlv, mib, parse_oid, respond


def populated_store():
    store = SensorStore()
    store.replace({
        "AA:BB:CC:DD:EE:FF": {
            "name": "Meter",
            "manufacturer": "SwitchBot",
            "model": "Meter Plus",
            "protocol": "SwitchBot BLE",
            "rssi": -55,
            "observed_at": "2026-09-11T13:00:00+00:00",
            "data": {"temperature": 21.5, "humidity": 48, "battery": 91},
        }
    })
    return store


def test_prometheus_rendering():
    body = render(populated_store()).decode()
    assert 'manufacturer="SwitchBot",model="Meter Plus",protocol="SwitchBot BLE"' in body
    assert 'key="temperature",unit=""} 21.5' in body
    assert "ble_sensors_devices 1" in body


def test_snmp_get_returns_response():
    base = parse_oid("1.3.6.1.4.1.32473.1.1")
    varbind = _tlv(0x30, _oid(base + (2, 0)) + _tlv(0x05, b""))
    pdu = _integer(7) + _integer(0) + _integer(0) + _tlv(0x30, varbind)
    packet = _tlv(0x30, _integer(1) + _tlv(0x04, b"secret") + _tlv(0xA0, pdu))
    answer = respond(packet, b"secret", populated_store(), base)
    assert answer is not None
    assert b"secret" in answer


def test_snmp_rejects_wrong_community():
    base = parse_oid("1.3.6.1.4.1.32473.1.1")
    varbind = _tlv(0x30, _oid(base + (2, 0)) + _tlv(0x05, b""))
    pdu = _integer(7) + _integer(0) + _integer(0) + _tlv(0x30, varbind)
    packet = _tlv(0x30, _integer(1) + _tlv(0x04, b"wrong") + _tlv(0xA0, pdu))
    assert respond(packet, b"secret", populated_store(), base) is None


def test_normalized_identity_and_all_scalar_data_survive_export_contract():
    body = render(populated_store()).decode()
    for field in ("temperature", "humidity", "battery"):
        assert f'key="{field}"' in body
    for identity in ("SwitchBot", "Meter Plus", "SwitchBot BLE"):
        assert identity in body

    snapshot = populated_store().snapshot()["AA:BB:CC:DD:EE:FF"]
    assert snapshot["manufacturer"] == "SwitchBot"
    assert snapshot["model"] == "Meter Plus"
    assert snapshot["protocol"] == "SwitchBot BLE"
    assert snapshot["data"] == {"temperature": 21.5, "humidity": 48, "battery": 91}


def test_snmp_mib_contains_identity_and_every_scalar():
    base = parse_oid("1.3.6.1.4.1.32473.1.1")
    table = mib(populated_store(), base)
    blob = b"".join(table.values())
    for text in (b"SwitchBot", b"Meter Plus", b"SwitchBot BLE", b"temperature", b"humidity", b"battery"):
        assert text in blob


def test_prometheus_marks_reused_sensor_as_stale():
    from ble_sensors_mqtt.metrics import SensorStore
    from ble_sensors_mqtt.prometheus import render

    store = SensorStore()
    store.replace({
        "AA:BB:CC:DD:EE:FF": {
            "name": "Room", "manufacturer": "Vendor", "model": "M", "protocol": "BLE",
            "stale": True, "data": {"temperature": 21.0},
        }
    })
    text = render(store).decode()
    assert "ble_sensors_up{" in text and "} 0" in text
    assert "ble_sensors_stale{" in text and "} 1" in text


def test_snmp_generic_index_columns_are_integer32():
    base = parse_oid("1.3.6.1.4.1.32473.1.1")
    table = mib(populated_store(), base)
    # BER tag 0x02 = INTEGER. The MIB declares columns 5 and 6 as Integer32.
    assert table[base + (20, 1, 5, 1, 1)][0] == 0x02
    assert table[base + (20, 1, 6, 1, 1)][0] == 0x02


def presence_store():
    store = SensorStore()
    store.replace({
        "11:22:33:44:55:66": {
            "name": "Presence Sensor",
            "manufacturer": "SwitchBot",
            "model": "Presence Sensor",
            "protocol": "SwitchBot BLE",
            "rssi": -50,
            "data": {
                "Detected": True,
                "moveDetected": False,
                "occupancy": 1,
                "moving": "off",
            },
        }
    })
    return store


def test_prometheus_exposes_presence_family_metrics():
    body = render(presence_store()).decode()
    assert "ble_sensors_presence{" in body and "} 1" in body
    assert "ble_sensors_motion{" in body and "} 0" in body
    assert "ble_sensors_occupancy{" in body and "} 1" in body
    assert "ble_sensors_moving{" in body and "} 0" in body
    # Original vendor fields remain available through the generic scalar exporter.
    assert 'key="Detected"' in body
    assert 'key="moveDetected"' in body


def test_snmp_exposes_presence_family_common_columns():
    base = parse_oid("1.3.6.1.4.1.32473.1.1")
    table = mib(presence_store(), base)
    for column in (13, 14, 15, 16):
        assert base + (10, 1, column, 1) in table
        assert table[base + (10, 1, column, 1)][0] == 0x42
