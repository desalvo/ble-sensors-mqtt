from ble_sensors_mqtt.binary import binary_device_class, coerce_binary, find_binary


def test_binary_aliases_cover_presence_sensor_families():
    assert binary_device_class("presence") == "presence"
    assert binary_device_class("Detected") == "presence"
    assert binary_device_class("moveDetected") == "motion"
    assert binary_device_class("detectionState") == "motion"
    assert binary_device_class("occupancy") == "occupancy"
    assert binary_device_class("moving") == "moving"


def test_binary_values_are_coerced_conservatively():
    assert coerce_binary(True) is True
    assert coerce_binary(0) is False
    assert coerce_binary("DETECTED") is True
    assert coerce_binary("NOT_DETECTED") is False
    assert coerce_binary("present") is True
    assert coerce_binary("unoccupied") is False
    assert coerce_binary(2) is None
    assert coerce_binary("maybe") is None


def test_find_binary_is_recursive_and_preserves_semantics():
    payload = {"data": {"channel": {"moveDetected": True, "occupancy": "off"}}}
    assert find_binary(payload, "motion") is True
    assert find_binary(payload, "occupancy") is False
    assert find_binary(payload, "presence") is None
