import asyncio
import sys
from types import SimpleNamespace

from ble_sensors_mqtt.cloud import TuyaCloudPlugin


def test_tuya_cloud_normalizes_all_status(monkeypatch, tmp_path):
    key = tmp_path / "key"
    secret = tmp_path / "secret"
    key.write_text("access-id", encoding="utf-8")
    secret.write_text("access-secret", encoding="utf-8")
    key.chmod(0o600)
    secret.chmod(0o600)

    class Cloud:
        def __init__(self, **kwargs):
            assert kwargs["apiKey"] == "access-id"

        def getdevices(self):
            return [{"id": "abc", "name": "Cantina", "product_name": "TH01"}]

        def getstatus(self, device_id):
            assert device_id == "abc"
            return {"result": [{"code": "temp_current", "value": 215}]}

    monkeypatch.setitem(sys.modules, "tinytuya", SimpleNamespace(Cloud=Cloud))

    def read(path, _description):
        return path.read_text(encoding="utf-8")

    readings = asyncio.run(TuyaCloudPlugin({
        "api_key_file": str(key), "api_secret_file": str(secret),
        "api_device_id": "abc", "region": "eu",
    }, read).poll())
    assert readings[0].manufacturer == "Tuya"
    assert readings[0].model == "TH01"
    assert readings[0].data["temp_current"] == 215


def test_cloud_registry_loads_enabled_tuya(monkeypatch):
    import ble_sensors_mqtt.cloud as cloud_module

    monkeypatch.setattr(cloud_module.importlib, "import_module", lambda name: object())
    loaded, unavailable = cloud_module.load_cloud_plugins(
        {"cloud": {"tuya": {"enabled": True}}}, None, lambda *_: "secret"
    )
    assert [item.name for item in loaded] == ["tuya-cloud"]
    assert "tuya-cloud" not in unavailable


def test_cloud_registry_skips_disabled_provider():
    from ble_sensors_mqtt.cloud import load_cloud_plugins

    loaded, unavailable = load_cloud_plugins({}, None, lambda *_: "secret")
    assert loaded == []
    assert "tuya-cloud" in unavailable
