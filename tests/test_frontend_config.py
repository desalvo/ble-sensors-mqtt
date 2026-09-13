from ble_sensors_mqtt.config import default_config, dump_config


def test_frontend_config_has_auth_sections():
    cfg = default_config()
    assert cfg["frontend"]["enabled"] is False
    assert cfg["frontend"]["ldap"]["default_role"] == "reader"
    assert cfg["frontend"]["oidc"]["default_role"] == "reader"
    text = dump_config(cfg)
    assert "[frontend.ldap]" in text
    assert "[frontend.oidc]" in text


def test_runtime_override_is_nested_toml(tmp_path):
    from ble_sensors_mqtt.config import atomic_write_config, load_config
    path = tmp_path / "runtime-config.toml"
    cfg = default_config()
    cfg["frontend"]["ldap"]["enabled"] = True
    atomic_write_config(path, cfg)
    loaded = load_config(path, required=True)
    assert loaded["frontend"]["ldap"]["enabled"] is True
