import asyncio
import sys
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace

import pytest

from ble_sensors_mqtt.plugins import (
    DECODERS,
    AirthingsPlugin,
    RuuviPlugin,
    SensorStatePlugin,
    SwitchBotPlugin,
)


@dataclass(frozen=True)
class Key:
    device_id: str | None
    key: str


class FakeServiceInfo:
    def __init__(self, name, address, rssi, *_args):
        self.name = name
        self.address = address
        self.rssi = rssi


@pytest.mark.parametrize("plugin_name,module_name,class_name,vendor", [
    (name, module, class_name, vendor)
    for name, (module, class_name, vendor) in DECODERS.items()
])
def test_sensor_state_adapters_preserve_identity_and_available_data(
    monkeypatch, plugin_name, module_name, class_name, vendor
):
    decoder_module = ModuleType(module_name)

    class Decoder:
        def __init__(self, bindkey=None):
            self.bindkey = bindkey
            self.unhandled = {"raw_flag": 7}

        def update(self, _service_info):
            key_temp = Key(None, "temperature")
            key_batt = Key(None, "battery")
            return SimpleNamespace(
                devices={None: SimpleNamespace(
                    model=f"{plugin_name}-model", manufacturer=vendor,
                    name=f"{plugin_name}-sensor", sw_version="1.2.3", hw_version="A1",
                )},
                entity_values={
                    key_temp: SimpleNamespace(native_value=21.5),
                    key_batt: SimpleNamespace(native_value=88),
                },
                binary_entity_values={},
                events={},
                entity_descriptions={
                    key_temp: SimpleNamespace(native_unit_of_measurement="°C"),
                    key_batt: SimpleNamespace(native_unit_of_measurement="%"),
                },
                title=f"{plugin_name} title",
            )

    setattr(decoder_module, class_name, Decoder)
    monkeypatch.setitem(sys.modules, module_name, decoder_module)
    monkeypatch.setitem(
        sys.modules,
        "habluetooth",
        SimpleNamespace(BluetoothServiceInfoBleak=FakeServiceInfo),
    )
    plugin = SensorStatePlugin(plugin_name, module_name, class_name, vendor)
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="radio-name")
    advertisement = SimpleNamespace(
        local_name="radio-name", rssi=-61, manufacturer_data={}, service_data={},
        service_uuids=[], tx_power=None,
    )

    readings = plugin.decode(device, advertisement)
    assert len(readings) == 1
    reading = readings[0]
    assert reading.manufacturer == vendor
    assert reading.model == f"{plugin_name}-model"
    assert reading.protocol == "Bluetooth LE"
    assert reading.data["temperature"] == 21.5
    assert reading.data["battery"] == 88
    assert reading.data["units"] == {"temperature": "°C", "battery": "%"}
    assert reading.data["software_version"] == "1.2.3"
    assert reading.data["hardware_version"] == "A1"
    assert reading.data["unhandled"] == {"raw_flag": 7}


def test_switchbot_adapter_preserves_all_parsed_data(monkeypatch):
    package = ModuleType("switchbot")
    adv_parser = ModuleType("switchbot.adv_parser")

    def parse_advertisement_data(_device, _advertisement):
        return SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF",
            device=SimpleNamespace(name="Meter Plus"),
            rssi=-55,
            data={"modelName": "Meter Plus", "temperature": 22.1, "humidity": 50, "battery": 93},
        )

    adv_parser.parse_advertisement_data = parse_advertisement_data
    monkeypatch.setitem(sys.modules, "switchbot", package)
    monkeypatch.setitem(sys.modules, "switchbot.adv_parser", adv_parser)

    reading = SwitchBotPlugin().decode(SimpleNamespace(), SimpleNamespace())[0]
    assert (reading.manufacturer, reading.model, reading.protocol) == (
        "SwitchBot", "Meter Plus", "SwitchBot BLE"
    )
    assert reading.data == {
        "modelName": "Meter Plus", "temperature": 22.1, "humidity": 50, "battery": 93
    }


def test_ruuvi_adapter_preserves_decoder_fields(monkeypatch):
    package = ModuleType("ruuvitag_sensor")
    decoder_module = ModuleType("ruuvitag_sensor.decoder")

    class Decoder:
        def decode_data(self, _data):
            return {"temperature": 20.3, "humidity": 47.2, "pressure": 101325}

    decoder_module.get_decoder = lambda _format: Decoder()
    monkeypatch.setitem(sys.modules, "ruuvitag_sensor", package)
    monkeypatch.setitem(sys.modules, "ruuvitag_sensor.decoder", decoder_module)
    advertisement = SimpleNamespace(
        manufacturer_data={0x0499: bytes([5, 1, 2, 3])}, local_name="RuuviTag", rssi=-63
    )
    reading = RuuviPlugin().decode(
        SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="RuuviTag"), advertisement
    )[0]
    assert reading.manufacturer == "Ruuvi"
    assert reading.model == "RuuviTag format 5"
    assert reading.data["pressure"] == 101325


def test_airthings_adapter_preserves_active_ble_values(monkeypatch):
    module = ModuleType("airthings_ble")

    class Data:
        def __init__(self, *_args, **_kwargs):
            pass

        async def update_device(self, _device):
            return SimpleNamespace(
                model=SimpleNamespace(product_name="Wave Plus"),
                manufacturer="Airthings",
                friendly_name=lambda: "Office Wave Plus",
                sensors={"radon_1day_avg": 42, "temperature": 21.0, "humidity": 45},
            )

    module.AirthingsBluetoothDeviceData = Data
    monkeypatch.setitem(sys.modules, "airthings_ble", module)
    reading = asyncio.run(AirthingsPlugin().decode_async(
        SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="Airthings Wave"),
        SimpleNamespace(local_name="Airthings Wave", rssi=-70),
    ))[0]
    assert reading.manufacturer == "Airthings"
    assert reading.model == "Wave Plus"
    assert reading.protocol == "Airthings BLE GATT"
    assert reading.data["radon_1day_avg"] == 42
