from pathlib import Path

from ble_sensors_mqtt.cli import _configured_parser
from ble_sensors_mqtt.config import atomic_write_config, default_config, dump_config, load_config


def test_config_toml_roundtrip(tmp_path: Path):
    path = tmp_path / "config.toml"
    config = default_config()
    config["mqtt"]["host"] = "broker.example"
    config["mqtt"]["home_assistant_discovery"] = True
    config["bluetooth"]["device_names"] = ["AA:BB:CC:DD:EE:FF=Office"]
    atomic_write_config(path, config)
    loaded = load_config(path, required=True)
    assert loaded["mqtt"]["host"] == "broker.example"
    assert loaded["mqtt"]["home_assistant_discovery"] is True
    assert loaded["bluetooth"]["device_names"] == ["AA:BB:CC:DD:EE:FF=Office"]
    assert "[prometheus]" in dump_config(config)


def test_cli_overrides_config_file(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[bluetooth]
poll_interval = 31.0
device_names = ["AA:BB:CC:DD:EE:FF=Office"]

[mqtt]
host = "from-config.example"
port = 1884
home_assistant_discovery = true

[mqtt_cache]
enabled = true
max_size = "2MiB"

[prometheus]
enabled = true
host = "127.0.0.1"
port = 9106
""".strip() + "\n",
        encoding="utf-8",
    )
    path.chmod(0o640)
    configured, argv = _configured_parser(
        ["--config", str(path), "--mqtt-host", "from-cli.example", "--poll-interval", "42"]
    )
    args = configured.parse_args(argv)
    assert args.config == path
    assert args.mqtt_host == "from-cli.example"
    assert args.mqtt_port == 1884
    assert args.poll_interval == 42.0
    assert args.home_assistant_discovery is True
    assert args.mqtt_cache_max_size == 2 * 1024 * 1024
    assert args.device_name == [("AA:BB:CC:DD:EE:FF", "Office")]
    assert args.prometheus is True
    assert args.prometheus_port == 9106
