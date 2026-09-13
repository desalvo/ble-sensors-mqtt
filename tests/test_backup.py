import json
from pathlib import Path

from ble_sensors_mqtt.backup import create_backup, extract_backup
from ble_sensors_mqtt.mqtt_cache import MQTTCache


def test_encrypted_backup_roundtrip(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('[mqtt]\nhost = "example"\n', encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text('{}', encoding="utf-8")
    backup = tmp_path / "full.bsmqbackup"
    create_backup(backup, "very-secret-passphrase", config_path=config, users=[{"username": "admin"}], files={"state.json": state})
    out = tmp_path / "restore"
    extract_backup(backup, "very-secret-passphrase", out)
    assert (out / "config/config.toml").read_text() == config.read_text()
    assert json.loads((out / "users.json").read_text())[0]["username"] == "admin"
    assert (out / "files/state.json").is_file()


def test_mqtt_cache_live_snapshot_and_restore(tmp_path: Path):
    cache = MQTTCache(tmp_path / "cache.sqlite3", 1024 * 1024)
    cache.enqueue("a/topic", b"one", 1, True)
    snap = tmp_path / "snap.sqlite3"
    cache.snapshot_to(snap)
    cache.delete(cache.oldest()[0].id)
    assert cache.stats()[0] == 0
    cache.restore_from(snap)
    assert cache.oldest()[0].payload == b"one"
    cache.close()
