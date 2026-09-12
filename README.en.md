# ble-sensors-mqtt

**English** · [Italiano](README.it.md)

<img src="assets/ble-sensors-mqtt-logo.png" alt="ble-sensors-mqtt application logo" width="180">

A plugin-based multi-sensor gateway for Raspberry Pi Zero W and newer boards. It collects
Bluetooth LE data and, optionally, Tuya Cloud data, then publishes one normalized snapshot to
MQTT, Prometheus, and SNMP. Intended repository: `desalvo/ble-sensors-mqtt`.

**Version:** 1.0.0 · **Build:** see `BUILD` · **Author:** Alessandro De Salvo
<braket71@gmail.com> · **License:** EUPL-1.2

## Features

- one BLE scanner with continuous polling (30 seconds by default) or a single cycle;
- isolated built-in adapters and third-party plugins loaded through Python entry points;
- SwitchBot in the base install and optional packages for other vendors;
- optional Tuya Cloud provider with credentials read only from protected files;
- aliases for MAC addresses and cloud/multi-channel identifiers;
- MQTT with verified TLS, QoS, retained state, and Last Will;
- optional read-only Prometheus and SNMPv2c exporters with configurable IP addresses and ports;
- `manufacturer`, `model`, and `protocol` in every output, plus all scalar values returned by
  the decoder;
- hardened systemd unit, tests, linting, Bandit, and dependency auditing;
- transparent PNG application logo, also embedded in the separate English and Italian PDF manuals.

## Sensors and access modes

| Plugin | Brands/protocols | Access | Install profile |
| --- | --- | --- | --- |
| `switchbot` | SwitchBot Meter and recognized models | local BLE advertisements | base |
| `xiaomi` | Xiaomi/Mijia, HHCC, MiBeacon | BLE; bind key for encrypted frames | `.[sensors]` |
| `govee` | Govee | local BLE | `.[sensors]` |
| `inkbird` | Inkbird | BLE; some models need a connection | `.[sensors]` |
| `thermopro` | ThermoPro | local BLE | `.[sensors]` |
| `qingping` | Qingping/ClearGrass | local BLE | `.[sensors]` |
| `bthome` | BTHome, Shelly BLU, ATC/PVVX in BTHome mode | local BLE | `.[sensors]` |
| `ruuvi` | RuuviTag | local BLE | `.[sensors]` |
| `sensorpush` | compatible SensorPush models | local BLE | `.[sensors]` |
| `airthings` | Airthings | active BLE GATT | `.[sensors]` |
| `mopeka` | Mopeka | local BLE | `.[sensors]` |
| `tuya-cloud` | sensors paired with Smart Life/Tuya | cloud API | `.[cloud]`/`.[all]` |

Actual support depends on the model, firmware, encryption, and advertised values. A Tuya
device using BTHome may work locally; proprietary Tuya formats require device-specific local
keys or the cloud. `--list-plugins` reports the adapters available in the current environment.
The vendor app is unnecessary for clear-text BLE advertisements and may coexist with this
gateway. It may be required to pair cloud devices or obtain encryption keys.

## Install in a Python virtual environment

Requirements: Raspberry Pi OS Bookworm, Python 3.11+, BlueZ, and a reachable MQTT broker.

```bash
unzip ble-sensors-mqtt-v1.0.0-<BUILD>.zip
cd ble-sensors-mqtt
sudo apt update
sudo apt install -y bluetooth bluez python3 python3-venv
sudo systemctl enable --now bluetooth
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
```

Choose one profile:

```bash
.venv/bin/pip install .             # SwitchBot only; lightest option
.venv/bin/pip install '.[sensors]'  # all BLE decoders
.venv/bin/pip install '.[cloud]'    # SwitchBot and Tuya Cloud
.venv/bin/pip install '.[all]'      # all BLE decoders and Tuya Cloud
```

```bash
.venv/bin/ble-sensors-mqtt --version
.venv/bin/ble-sensors-mqtt --list-plugins
.venv/bin/ble-sensors-mqtt --help
```

On a Pi Zero, install only the required plugins and keep the polling interval at 30 seconds
or more.

## Scan and name sensors

Scanning does not require MQTT:

```bash
.venv/bin/ble-sensors-mqtt --scan --scan-duration 15
.venv/bin/ble-sensors-mqtt --scan --plugin switchbot --plugin bthome
```

The JSON output contains recognized devices. Every reading includes `address`, `name`,
`manufacturer`, `model`, `protocol`, `observed_at`, and `data`; unknown identity fields use
`Unknown`.

```bash
# BLE alias
.venv/bin/ble-sensors-mqtt --scan \
  --device-name 'AA:BB:CC:DD:EE:FF=Server Room'

# Cloud or multi-channel alias
.venv/bin/ble-sensors-mqtt --scan --cloud-config ./cloud.toml \
  --sensor-name 'TUYA:bf123456=Basement'
```

The alias replaces `name` in every output; `bluetooth_name` preserves the radio name.
`--device ID` is a repeatable allow-list for published sensors and accepts BLE MAC addresses or cloud/plugin identifiers such as `TUYA:bf123456`.

For encrypted BTHome or Xiaomi/MiBeacon advertisements, export the bind key using the vendor
or firmware tools. Store only its hexadecimal value in a `0600`/`0640` file and reference it
from the TOML file supplied with `--cloud-config`:

```toml
[ble_keys."AA:BB:CC:DD:EE:FF"]
plugin = "bthome" # or "xiaomi"
bindkey_file = "/etc/ble-sensors-mqtt/sensor-aa-bb-bindkey"
```

BTHome requires 16 bytes; Xiaomi accepts 12 or 16 bytes. Never put the key on the command
line or in logs.

## MQTT

```bash
# One-cycle test
.venv/bin/ble-sensors-mqtt --mqtt-host 127.0.0.1 --once

# Continuous service, every 60 seconds
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --poll-interval 60 --allow-insecure-mqtt

# Production with TLS
.venv/bin/ble-sensors-mqtt --mqtt-host mqtt.example.net --mqtt-port 8883 \
  --mqtt-username sensor-publisher \
  --mqtt-password-file /etc/ble-sensors-mqtt/mqtt-password \
  --mqtt-tls --mqtt-ca-file /etc/ssl/certs/ca-certificates.crt
```

For `AA:BB:CC:DD:EE:FF`, the topic is `ble-sensors/aabbccddeeff/state`; bridge status is
`ble-sensors/bridge/status`. Example payload:

```json
{
  "address": "AA:BB:CC:DD:EE:FF",
  "name": "Server Room",
  "bluetooth_name": "Meter Plus",
  "manufacturer": "SwitchBot",
  "model": "Meter Plus",
  "protocol": "SwitchBot BLE",
  "rssi": -58,
  "observed_at": "2026-09-11T20:00:00+00:00",
  "data": {"temperature": 23.4, "humidity": 51, "battery": 92}
}
```

`data` contains every value returned by the decoder, including booleans, versions, units,
and events. Secret files must have permissions `0640` or more restrictive.

## Tuya Cloud

Run `.venv/bin/ble-sensors-mqtt --cloud-help`. In the Tuya IoT portal, create a Smart Home
project, link the Smart Life/Tuya account, authorize device APIs, and record the region,
Access ID, Access Secret, and one Device ID. Store the two secrets in separate `0640` files.

```toml
[cloud.tuya]
enabled = true
region = "eu"
api_key_file = "/etc/ble-sensors-mqtt/tuya-api-key"
api_secret_file = "/etc/ble-sensors-mqtt/tuya-api-secret"
api_device_id = "REFERENCE_DEVICE_ID"
device_ids = ["DEVICE_ID_TO_EXPORT"] # optional; empty means all
```

```bash
sudo install -m 0640 -o root -g ble-sensors-mqtt config/cloud.example.toml \
  /etc/ble-sensors-mqtt/cloud.toml
.venv/bin/ble-sensors-mqtt --scan --cloud-config /etc/ble-sensors-mqtt/cloud.toml
```

A cloud failure is isolated and does not discard BLE readings from the cycle. Calls use
HTTPS; review the service privacy notice, data location, and terms.

## Prometheus

```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --prometheus
curl http://127.0.0.1:9105/metrics
```

The exporter provides `ble_sensors_up`, `ble_sensors_temperature_celsius`,
`ble_sensors_humidity_percent`, `ble_sensors_battery_percent`, `ble_sensors_rssi_dbm`, and
`ble_sensors_devices`. Generic numbers/booleans use `ble_sensors_sensor_value`; strings use
`ble_sensors_sensor_info`. Sensor series include `address`, `name`, `manufacturer`, `model`,
and `protocol` labels.

```bash
# All IPv4 interfaces, custom port
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --prometheus \
  --prometheus-host 0.0.0.0 --prometheus-port 9200 --allow-external-prometheus
```

The default is `127.0.0.1:9105`; use `::` for IPv6. `/healthz` reports process liveness and `/readyz` returns HTTP 200 only after a recent successful polling cycle. The endpoint has no authentication or TLS, therefore a non-loopback bind is rejected unless `--allow-external-prometheus` is explicitly supplied. Protect external access with a firewall, VPN, or authenticated reverse proxy.

## SNMP

```bash
sudo sh -c 'umask 077; printf %s "RANDOM_COMMUNITY" > /etc/ble-sensors-mqtt/snmp-community'
sudo chown root:ble-sensors-mqtt /etc/ble-sensors-mqtt/snmp-community
sudo chmod 0640 /etc/ble-sensors-mqtt/snmp-community
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --snmp \
  --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
snmpwalk -v2c -c RANDOM_COMMUNITY 127.0.0.1:1161 1.3.6.1.4.1.32473.1.1
```

The device table includes name, address, RSSI, common measurements, timestamp, manufacturer,
model, and protocol. Subtree `.20` exposes each scalar as key, value, type, and unit. See
`docs/BLE-SENSORS-MQTT-MIB.txt`.

```bash
# All IPv4 interfaces, custom port
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --snmp \
  --snmp-host 0.0.0.0 --snmp-port 2161 --allow-external-snmp \
  --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
```

The default is `127.0.0.1:1161`; `::` exposes IPv6. A non-loopback bind is rejected unless `--allow-external-snmp` is explicitly supplied. SNMPv2c does not encrypt traffic: never publish it directly to the Internet. Use firewall rules, a VPN, or an SNMPv3 proxy. PEN 32473
is documentation-only; set an assigned enterprise OID with `--snmp-base-oid` in production.

## systemd

```bash
sudo scripts/install-systemd.sh
sudo install -m 0640 -o root -g ble-sensors-mqtt /dev/null \
  /etc/ble-sensors-mqtt/mqtt-password
sudo editor /etc/ble-sensors-mqtt/mqtt-password
sudo editor /etc/ble-sensors-mqtt/environment
sudo systemctl enable --now ble-sensors-mqtt
journalctl -u ble-sensors-mqtt -f
```

The installer creates the unprivileged service account, keeps application code root-owned, installs the complete runtime into an isolated venv, and installs the hardened unit. The supplied unit requires verified MQTT TLS. Do not remove TLS in a production deployment; the CLI also rejects remote or credentialed plaintext MQTT unless the explicit risk override is supplied.

## CLI reference

| Option | Default | Purpose |
| --- | ---: | --- |
| `--scan` | off | Print recognized sensors and exit |
| `--list-plugins` | off | Show plugin and dependency status |
| `--plugin NAME` | all installed | Restrict plugins; repeatable |
| `--cloud-help` | off | Show Tuya setup instructions |
| `--cloud-config FILE` | none | Protected TOML configuration |
| `--scan-duration S` | 8 | BLE scan duration |
| `--poll-interval S` | 30 | Poll interval, 1–86400 seconds |
| `--plugin-timeout S` | 15 | Maximum decoder/cloud call duration |
| `--device ID` | all | Repeatable sensor allow-list (BLE MAC or cloud/plugin ID) |
| `--device-name MAC=NAME` | radio name | Repeatable BLE alias |
| `--sensor-name ID=NAME` | original | Cloud/multi-channel alias |
| `--mqtt-host HOST` | none | MQTT broker |
| `--mqtt-port PORT` | 1883/8883 | Broker port |
| `--mqtt-topic-prefix` | `ble-sensors` | Topic root |
| `--mqtt-username` | none | Broker username |
| `--mqtt-password-file` | none | Password in a protected file |
| `--mqtt-tls` | off | TLS with certificate verification |
| `--mqtt-connect-timeout S` | 15 | CONNACK/publish acknowledgement timeout |
| `--allow-insecure-mqtt` | off | Explicit plaintext MQTT risk override |
| `--qos` | 1 | QoS 0, 1, or 2 |
| `--retain` / `--no-retain` | retain | Retained sensor state |
| `--stale-cycles N` | 3 | Missing cycles before clearing retained state |
| `--state-file FILE` | none | Persist retained-topic cleanup state across restarts |
| `--once` | off | Run one cycle |
| `--prometheus` | off | Enable HTTP metrics |
| `--prometheus-host` | `127.0.0.1` | Listen IP |
| `--prometheus-port` | 9105 | TCP port |
| `--allow-external-prometheus` | off | Explicitly allow non-loopback unauthenticated HTTP |
| `--snmp` | off | Enable read-only SNMPv2c |
| `--snmp-host` | `127.0.0.1` | Listen IP |
| `--snmp-port` | 1161 | UDP port |
| `--snmp-community-file` | none | Community in a protected file |
| `--snmp-base-oid` | `.1.3.6.1.4.1.32473.1.1` | Export subtree |
| `--allow-external-snmp` | off | Explicitly allow non-loopback plaintext SNMPv2c |

## Third-party plugins

Implement `SensorPlugin` from `ble_sensors_mqtt.plugin_api` and register a no-argument
factory:

```toml
[project.entry-points."ble_sensors_mqtt.sensor_plugins"]
acme = "acme_sensor.plugin:AcmePlugin"
```

`decode(device, advertisement)` returns zero or more `SensorReading` objects. Always provide
manufacturer, model, and protocol, and never put secrets in sensor data. Plugin errors are
isolated.

Cloud providers use a separate entry-point group and receive their own TOML configuration plus
the protected-file secret reader:

```toml
[project.entry-points."ble_sensors_mqtt.cloud_plugins"]
acme-cloud = "acme_sensor.cloud:AcmeCloudPlugin"
```

The cloud class/factory is constructed as `AcmeCloudPlugin(config, read_secret)` and implements
`CloudPlugin.poll()`. By default `acme-cloud` reads `[cloud.acme]`; a class may expose
`config_key` to select a different table. Cloud failures are isolated from BLE and from other
cloud providers.

## Security, AgID alignment, and limitations

The project applies least privilege, verified TLS, secrets outside command lines and
environment variables, bounded inputs, safe JSON conversion, optional dependencies,
credential-free logging, hardened systemd settings, and automated checks. See
[`docs/AGID-SECURITY.en.md`](docs/AGID-SECURITY.en.md) and [`SECURITY.en.md`](SECURITY.en.md). This is a
technical self-assessment against AgID secure-software good practices, not an AgID
certification. Before production, perform threat modeling and hardware testing, prepare
vulnerability handling and rollback, and configure firewall and MQTT ACLs. BLE advertisements
and SNMPv2c do not provide end-to-end authenticity or confidentiality.

## Documentation, build, and license

- English manual: [`docs/USAGE.en.md`](docs/USAGE.en.md) and `docs/ble-sensors-mqtt-manual-v1.0.0-en.pdf`
- Manuale italiano: [`docs/USAGE.it.md`](docs/USAGE.it.md) and `docs/ble-sensors-mqtt-manual-v1.0.0-it.pdf`

`scripts/build-package.sh` updates `BUILD` in UTC as `YYYYMMDD-HHMM`, then creates ZIP,
TAR.GZ, and SHA-256 checksums. Licensed under EUPL-1.2; see `LICENSE`.

## Production release policy

Release 1.0.0 is designed to fail closed on unsafe network exposure. Remote or credentialed plaintext MQTT requires the explicit `--allow-insecure-mqtt` override; production deployments should use verified TLS. Prometheus/health and SNMPv2c stay loopback-only unless their explicit external-access flags are supplied. Cloud and decoder calls are bounded by `--plugin-timeout`; MQTT messages are bounded and QoS publications are acknowledged before a cycle is considered successful.

The Prometheus HTTP server exposes `/metrics`, `/healthz`, and `/readyz`. Readiness becomes false before the first successful cycle and when the latest success is older than approximately three polling intervals. MQTT retained sensor topics are removed after `--stale-cycles` consecutive misses (default 3), not after one transient BLE miss. With systemd, `--state-file /var/lib/ble-sensors-mqtt/state.json` preserves this cleanup state across process restarts.

A production release must pass `scripts/release-check.sh`. The gate runs compilation, Ruff, pytest with coverage, Bandit, `pip-audit`, both PDF manual builds, standard wheel/sdist creation, `twine check`, CycloneDX SBOM generation, and release-content verification. CI executes the runtime suite on Python 3.11, 3.12, and 3.13 with all optional sensor/cloud dependencies. See `docs/PRODUCTION.en.md`.

GitHub Actions also automates publication. A pushed tag such as `v1.0.0` triggers the complete test/build pipeline; only after every gate succeeds does the `release` job verify that the tag matches both `VERSION` and `pyproject.toml`, download the CI-built artifacts, and create or update the corresponding GitHub Release. The release contains wheel, sdist, SBOM, deterministic project archives, SHA-256 checksums, and the separate EN/IT manuals. No personal GitHub token is required: the job uses the repository-scoped `GITHUB_TOKEN` with `contents: write` only for the release job.
