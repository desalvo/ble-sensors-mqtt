# Unified configuration

`ble-sensors-mqtt` supports a persistent TOML configuration file on every operating system. Precedence is always:

1. explicit CLI arguments;
2. values in `config.toml`;
3. built-in application defaults.

Use an alternate file with `--config PATH`. If `--config` is not supplied, the native default is:

- Linux: `/etc/ble-sensors-mqtt/config.toml`;
- Windows: `%ProgramData%\ble-sensors-mqtt\config.toml`;
- macOS: `~/Library/Application Support/ble-sensors-mqtt/config.toml`.

The complete template is `config/app.example.toml`. Important sections are `[bluetooth]`, `[runtime]`, `[mqtt]`, `[mqtt_cache]`, `[prometheus]`, `[snmp]`, and `[cloud]`. Repeatable sensor/plugin options use TOML arrays.

Example:

```toml
[bluetooth]
poll_interval = 30.0
device_names = ["AA:BB:CC:DD:EE:FF=Server room"]

[runtime]
reuse_stale_data = true

[mqtt]
host = "mqtt.example.net"
port = 8883
tls = true
home_assistant_discovery = true

[mqtt_cache]
enabled = true
max_size = "1GiB"

[prometheus]
enabled = true
host = "127.0.0.1"
port = 9105
```

Secrets remain in separate protected files. Store paths such as `mqtt.password_file` and `snmp.community_file` in `config.toml`; do not put the actual secret into TOML.

A one-off CLI override does not rewrite the configuration. For example:

```bash
ble-sensors-mqtt --config /etc/ble-sensors-mqtt/config.toml --poll-interval 10
```

uses the stored configuration but changes the polling interval only for that process.

## History

`[history]` controls persistent dashboard history. `retention_days` defaults to `30` and is applied live from the web Configuration page. `path` selects the SQLite file and requires a service restart when changed. Equivalent CLI options are `--history-retention-days` and `--history-path`.
