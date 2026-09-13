# Installation and usage manual


> Host support: Linux x86_64/arm64 on Debian/Ubuntu/Raspberry Pi OS and RHEL/Rocky/AlmaLinux/CentOS/Fedora, plus Windows 11+ and macOS Tahoe 26+. Internal and USB Bluetooth are supported through the host OS stack. See `HOSTS.en.md`.
**English** · [Italiano](USAGE.it.md)

## 1. Purpose

`ble-sensors-mqtt` 1.0.0 is a multi-sensor gateway for Raspberry Pi. Plugins collect BLE or
Tuya Cloud data and emit one common model containing identifier, name, manufacturer, model,
protocol, signal strength, timestamp, and all available values. The same snapshot feeds MQTT,
Prometheus, and SNMP.

## 2. Installation

```bash
sudo apt update
sudo apt install -y bluetooth bluez python3 python3-venv
sudo systemctl enable --now bluetooth
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install '.[all]'
```

On a Pi Zero, use `pip install .` for SwitchBot only, `.[sensors]` for all BLE decoders, or
`.[cloud]` for SwitchBot and Tuya. Verify the result with
`ble-sensors-mqtt --list-plugins`.

## 3. Supported plugins

| Name | Family | Access |
| --- | --- | --- |
| switchbot | SwitchBot | local BLE |
| xiaomi | Xiaomi/Mijia/HHCC | BLE, optional bind key |
| govee | Govee | local BLE |
| inkbird | Inkbird | BLE/connection on compatible models |
| thermopro | ThermoPro | local BLE |
| qingping | Qingping/ClearGrass | local BLE |
| bthome | BTHome, Shelly BLU, ATC/PVVX-BTHome | local BLE |
| ruuvi | RuuviTag | local BLE |
| sensorpush | SensorPush | local BLE |
| airthings | Airthings | active BLE GATT |
| mopeka | Mopeka | local BLE |
| tuya-cloud | Tuya/Smart Life | HTTPS cloud |

Support varies by model and firmware. Clear-text BLE sensors do not need to be added to the
vendor app. The app may coexist with the gateway and can be required for cloud pairing or
for obtaining encryption keys.

## 4. Scan, selection, and aliases

```bash
.venv/bin/ble-sensors-mqtt --scan --scan-duration 15
.venv/bin/ble-sensors-mqtt --scan --plugin switchbot --plugin bthome
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 \
  --device AA:BB:CC:DD:EE:FF \
  --device-name 'AA:BB:CC:DD:EE:FF=Server Room'
```

Scanning needs no MQTT broker. `--device ID` accepts either a BLE MAC or a cloud/plugin identifier. Use `--sensor-name 'ID=NAME'` for Tuya or multi-channel readings. Aliases reach every output while `bluetooth_name` keeps the original radio name.

For encrypted Xiaomi/BTHome frames, store the hexadecimal bind key in a protected file and
add `[ble_keys."MAC"]`, `plugin="xiaomi"` or `"bthome"`, and
`bindkey_file="/path/file"` to the configuration TOML. Never pass keys on the command line.

## 5. Runtime and MQTT

### Home Assistant MQTT Discovery

Add `--home-assistant-discovery` to publish retained Home Assistant discovery configuration. The default discovery prefix is `homeassistant`; override it with `--home-assistant-discovery-prefix`. Each exported sensor becomes one Home Assistant device, with one sensor entity for each scalar payload value plus RSSI and protocol diagnostics. State remains on the regular gateway MQTT state topic and availability is tied to `<mqtt-prefix>/bridge/status`.

```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 127.0.0.1 --home-assistant-discovery
```

Discovery configuration is retained. Stale discovery topics are explicitly cleared using retained empty payloads so removed sensors/entities disappear from Home Assistant. Keep the runtime state file enabled in long-running/systemd deployments so cleanup also works across restarts.


```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 127.0.0.1 --once
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --poll-interval 60 --allow-insecure-mqtt
.venv/bin/ble-sensors-mqtt --mqtt-host mqtt.example.net --mqtt-port 8883 \
  --mqtt-username sensor-publisher \
  --mqtt-password-file /etc/ble-sensors-mqtt/mqtt-password --mqtt-tls
```

Polling defaults to 30 seconds. TLS certificates are always verified. Secret files must be
`0640` or more restrictive. Every payload contains `manufacturer`, `model`, `protocol`, and
all decoder information under `data`.

## 6. Tuya Cloud

Run `--cloud-help`, create a Smart Home project in Tuya IoT, and link the Smart Life/Tuya
account. Keep Access ID and Access Secret in separate protected files.

```toml
[cloud.tuya]
enabled = true
region = "eu"
api_key_file = "/etc/ble-sensors-mqtt/tuya-api-key"
api_secret_file = "/etc/ble-sensors-mqtt/tuya-api-secret"
api_device_id = "REFERENCE_DEVICE_ID"
device_ids = ["DEVICE_ID_1"]
```

The TOML file must be `0640` or more restrictive. Test it with:

```bash
.venv/bin/ble-sensors-mqtt --scan --cloud-config /etc/ble-sensors-mqtt/cloud.toml
```

A Tuya failure does not stop BLE collection. Review cloud privacy, data residency, and service
dependency. Tuya devices running BTHome firmware may work locally.

## 7. Prometheus

Enable the HTTP exporter with:

```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --prometheus
curl http://127.0.0.1:9105/metrics
```

The default listener is `127.0.0.1:9105`. A non-loopback bind requires the explicit
`--allow-external-prometheus` acknowledgement. The endpoint has no built-in authentication or
TLS, so external access should be protected by firewall rules, a VPN, or an authenticated
reverse proxy.

### Exported Prometheus metrics

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `ble_sensors_up` | gauge | `address,name,manufacturer,model,protocol` | `1` for a fresh snapshot, `0` when the exported snapshot is reused/stale |
| `ble_sensors_stale` | gauge | same sensor labels | `1` when the snapshot was reused from a previous cycle, otherwise `0` |
| `ble_sensors_temperature_celsius` | gauge | same sensor labels | recursively discovered numeric `temperature` value, in degrees Celsius |
| `ble_sensors_humidity_percent` | gauge | same sensor labels | recursively discovered numeric `humidity` value, in percent |
| `ble_sensors_battery_percent` | gauge | same sensor labels | recursively discovered numeric `battery` or `battery_percent` value |
| `ble_sensors_rssi_dbm` | gauge | same sensor labels | top-level Bluetooth RSSI in dBm, when available |
| `ble_sensors_sensor_value` | gauge | sensor labels + `key,unit` | every numeric scalar; booleans are exported as `0`/`1` |
| `ble_sensors_sensor_info` | gauge | sensor labels + `key,unit,value` | every non-null string scalar, represented by a constant sample value of `1` |
| `ble_sensors_devices` | gauge | none | number of snapshots currently exported, including reused stale snapshots |
| `ble_sensors_cycles_total` | counter | none | polling cycles attempted by the gateway |
| `ble_sensors_cycles_failed_total` | counter | none | polling cycles marked as failed |

The generic metrics are generated only from the normalized sensor `data` object. Nested dictionaries
are flattened with dotted paths such as `air.co2`; list/tuple entries use numeric path components such
as `channels.0`. The reserved `data.units` mapping is not exported as sensor data; when available, its
leaf-name mapping supplies the `unit` label. At most 256 scalar values per sensor are exported. `null`
values are omitted from Prometheus.

Dedicated temperature/humidity/battery metrics and the generic metric can intentionally expose the same
measurement. The dedicated names are convenient for stable dashboards, while the generic family preserves
all plugin-provided scalar values. Because `ble_sensors_sensor_info` puts string values in labels, highly
variable strings can increase Prometheus cardinality.

Example:

```text
ble_sensors_up{address="AA:BB:CC:DD:EE:FF",name="Room",manufacturer="SwitchBot",model="Meter Plus",protocol="SwitchBot BLE"} 1
ble_sensors_temperature_celsius{address="AA:BB:CC:DD:EE:FF",name="Room",manufacturer="SwitchBot",model="Meter Plus",protocol="SwitchBot BLE"} 21.5
ble_sensors_sensor_value{address="AA:BB:CC:DD:EE:FF",name="Room",manufacturer="SwitchBot",model="Meter Plus",protocol="SwitchBot BLE",key="temperature",unit="°C"} 21.5
```

The same HTTP server also exposes `/healthz` and `/readyz`. `/healthz` reports process liveness;
`/readyz` returns HTTP 503 until a polling cycle succeeds and again when the latest successful cycle
becomes too old.

```bash
--prometheus --prometheus-host 0.0.0.0 --prometheus-port 9200 --allow-external-prometheus
```

## 8. SNMP

Enable the read-only SNMPv2c agent with a protected community file:

```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --snmp \
  --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
```

The default listener is `127.0.0.1:1161/udp`. Non-loopback binding requires
`--allow-external-snmp`. SNMPv2c does not encrypt the community or payload, so restrict UDP access or
use a VPN/SNMPv3 proxy.

With the default `--snmp-base-oid 1.3.6.1.4.1.32473.1.1`, the exported tree is:

| OID suffix | MIB object | Type | Meaning |
| --- | --- | --- | --- |
| `.1.0` | `bleSensorsVersion` | DisplayString | application identification/version string |
| `.2.0` | `bleSensorsDeviceCount` | Gauge32 | number of snapshots currently exported |
| `.10.1.1.I` | `bleSensorsIndex` | Integer32 | transient device row index |
| `.10.1.2.I` | `bleSensorsAddress` | DisplayString | normalized sensor identifier/address |
| `.10.1.3.I` | `bleSensorsName` | DisplayString | effective sensor name/alias |
| `.10.1.4.I` | `bleSensorsRssi` | Integer32 | RSSI in dBm, omitted when unavailable |
| `.10.1.5.I` | `bleSensorsTemperatureMilliCelsius` | Integer32 | temperature multiplied by 1000 |
| `.10.1.6.I` | `bleSensorsHumidityMilliPercent` | Gauge32 | relative humidity multiplied by 1000 |
| `.10.1.7.I` | `bleSensorsBatteryPercent` | Gauge32 | battery percentage rounded to an integer |
| `.10.1.8.I` | `bleSensorsObservedAt` | DisplayString | original observation timestamp |
| `.10.1.9.I` | `bleSensorsManufacturer` | DisplayString | manufacturer, or `Unknown` |
| `.10.1.10.I` | `bleSensorsModel` | DisplayString | model, or `Unknown` |
| `.10.1.11.I` | `bleSensorsProtocol` | DisplayString | protocol, or `Unknown` |
| `.10.1.12.I` | `bleSensorsStale` | Gauge32 | `1` for reused/stale data, otherwise `0` |
| `.20.1.1.I.J` | `bleSensorsValueKey` | DisplayString | flattened scalar key/path |
| `.20.1.2.I.J` | `bleSensorsValue` | DisplayString | scalar rendered as text |
| `.20.1.3.I.J` | `bleSensorsValueType` | DisplayString | `null`, `boolean`, `number`, or `string` |
| `.20.1.4.I.J` | `bleSensorsValueUnit` | DisplayString | unit from `data.units`, when available |
| `.20.1.5.I.J` | `bleSensorsValueDeviceIndex` | Integer32 | device index `I` |
| `.20.1.6.I.J` | `bleSensorsValueIndex` | Integer32 | scalar row index `J` |

Rows in `.10` are ordered by the normalized sensor identifier, so index `I` is transient and may change
when the exported device set changes. Optional common-measurement columns are absent when their values are
not available. Table `.20` contains up to 256 scalar values from each sensor `data` object and uses the same
flattening rules as Prometheus. SNMP textual fields are capped by the agent at 512 encoded bytes.

The bundled textual MIB is `docs/BLE-SENSORS-MQTT-MIB.txt`. PEN `32473` is documentation-only. In
production, use an assigned enterprise OID with `--snmp-base-oid`. Changing the base OID relocates the same
suffix layout shown above; the bundled textual MIB itself still names the documented default root.

Example walks:

```bash
snmpwalk -v2c -c RANDOM_COMMUNITY 127.0.0.1:1161 1.3.6.1.4.1.32473.1.1
snmpwalk -v2c -c RANDOM_COMMUNITY 127.0.0.1:1161 1.3.6.1.4.1.32473.1.1.10
snmpwalk -v2c -c RANDOM_COMMUNITY 127.0.0.1:1161 1.3.6.1.4.1.32473.1.1.20
```

## 9. systemd

For a complete installation starting from a GitHub clone (host prerequisites, Bluetooth check, venv, and systemd):

```bash
git clone https://github.com/desalvo/ble-sensors-mqtt.git
cd ble-sensors-mqtt
sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net --prometheus
```

Use the systemd installer directly when the clone and prerequisites already exist:

```bash
# Interactive; CLI values are the defaults shown by the prompts
sudo scripts/install-systemd.sh --mqtt-host mqtt.example.net --prometheus

# Fully unattended provisioning
sudo scripts/install-systemd.sh --non-interactive \
  --mqtt-host mqtt.example.net --mqtt-tls \
  --mqtt-username ble-sensors-publisher --mqtt-password-file ./mqtt-password \
  --home-assistant-discovery --prometheus
```

The installer creates the service user, isolated venv, root-owned configuration and `/etc/ble-sensors-mqtt/config.toml`; repeatable options are stored as TOML arrays and values containing spaces are preserved without shell parsing. In interactive mode, CLI values remain the defaults shown by the wizard and already supplied repeatable options are retained. Use `--non-interactive` to install only from CLI/default values. See `docs/SYSTEMD.en.md`.

## Windows/macOS graphical installation and settings

Tagged Windows releases include a standard graphical `-setup.exe` installer; tagged macOS releases include standard `.pkg` installers for Apple Silicon and Intel. Both install a graphical **ble-sensors-mqtt Settings** application. Windows uses a system Windows Service and `%ProgramData%\ble-sensors-mqtt\config.toml`; macOS uses a per-user launchd LaunchAgent and `~/Library/Application Support/ble-sensors-mqtt/config.toml`. The GUI can save configuration, start/stop/restart the service, test Bluetooth, and open the configuration folder. CLI arguments override TOML without rewriting it. See `docs/NATIVE-INSTALLERS.en.md` and `docs/CONFIGURATION.en.md`.

## 10. Docker and Kubernetes

```bash
# Multiarch build + Docker Hub push of desalvo/ble-sensors-mqtt:<VERSION>
docker login
scripts/build-docker.sh

# Continuous Docker service
cd docker
cp .env.example .env
cp arguments.example arguments
docker compose up -d

# Continuous Kubernetes service
kubectl label node NODE_NAME ble-sensors-mqtt/bluetooth=true
kubectl apply -k kubernetes/
```

Before Docker/Kubernetes, validate the host with `sudo scripts/check-bluetooth-host.sh --strict`. Both mount `/run/dbus` read-only and use host BlueZ over system D-Bus; privileged mode is not required in the supported model. Kubernetes also includes `kubernetes/bluetooth-test-pod.yaml` to validate `--scan` on the selected node.

The image supports `linux/amd64` and `linux/arm64`. Docker/Kubernetes mount the host system D-Bus for BlueZ, persist runtime state, send MQTT outbound, expose Prometheus on TCP/9105 and SNMP on UDP/1161. Optional Kubernetes LoadBalancer manifests expose Prometheus and SNMP externally when explicitly applied. `scripts/build-docker.sh` pushes `desalvo/ble-sensors-mqtt:<VERSION>` by default; CI can publish the versioned image on `vX.Y.Z` tags and `latest` on `main`. See `docs/DOCKER.en.md` and `docs/KUBERNETES.en.md`; external monitoring endpoints must be restricted to trusted networks.

## 11. Extensions

A third-party local package implements `SensorPlugin.decode()`, returns `SensorReading` objects, and registers itself in the `ble_sensors_mqtt.sensor_plugins` entry-point group. A third-party cloud provider implements `CloudPlugin.poll()` and registers a factory/class in `ble_sensors_mqtt.cloud_plugins`; its constructor receives `(config, read_secret)` and its default TOML section is `[cloud.<entry-point-name-without--cloud>]`. Every reading must contain manufacturer, model, and protocol. Plugin exceptions are isolated.

## 12. Security and troubleshooting

- do not run as root;
- protect MQTT, Tuya, bind-key, and SNMP files;
- use minimal MQTT ACLs and TLS;
- do not expose Prometheus/SNMP without network controls;
- update and audit dependencies with `pip-audit`;
- test actual sensor models before production.

```bash
bluetoothctl show
.venv/bin/ble-sensors-mqtt --list-plugins
.venv/bin/ble-sensors-mqtt --scan --scan-duration 20 --log-level DEBUG
journalctl -u ble-sensors-mqtt --since today
```

The AgID review is a technical self-assessment, not a certification.

## 13. Build and rollback

`scripts/build-package.sh` generates a UTC build ID in `YYYYMMDD-HHMM` format, ZIP, TAR.GZ,
and SHA-256 checksums. Keep the previous package for rollback; do not modify `site-packages`
in place.

## 14. Production health and release gates

### Health and readiness

When Prometheus is enabled, the same HTTP server provides:

- `/metrics` for Prometheus;
- `/healthz` for process liveness;
- `/readyz` for readiness. It returns HTTP 503 until one polling cycle succeeds and again if successful polling becomes stale.

Non-loopback Prometheus/health exposure requires `--allow-external-prometheus`; non-loopback SNMPv2c requires `--allow-external-snmp`. Remote or credentialed plaintext MQTT requires `--allow-insecure-mqtt`. These overrides are deliberate risk acknowledgements, not recommended production defaults.

`--plugin-timeout` limits one decoder/cloud call (default 15 seconds). `--stale-cycles` controls when retained MQTT state for a missing sensor is cleared (default 3 consecutive cycles). `--state-file` persists this cleanup state across restarts; the supplied systemd unit uses `/var/lib/ble-sensors-mqtt/state.json`.

### Release verification

Install `.[all,dev,release]` and run:

```bash
scripts/release-check.sh
```

The gate requires lint, tests/coverage, Bandit, dependency audit, EN/IT PDF generation, wheel and sdist build, `twine check`, CycloneDX SBOM generation, and release package verification. CI repeats runtime tests on Python 3.11, 3.12 and 3.13.

For GitHub publication, push the source commit first and then push a matching `vX.Y.Z` tag. The tag workflow runs all gates, builds deterministic release assets, creates consolidated SHA-256 checksums, and publishes the GitHub Release automatically only after the test and build jobs succeed. The release job checks that the tag version matches `VERSION` and `pyproject.toml`.

## Stale fallback and persistent MQTT cache

Use `--reuse-stale-data` to preserve the last in-memory sensor snapshot when a cycle misses that sensor or produces no sensor data. Reused snapshots retain the original observation timestamp and set `stale: true`; fresh readings set `stale: false`. The MQTT SQLite spool is enabled by default, has a 1 GiB logical limit, continues collecting while the broker is offline, flushes FIFO after reconnection, and removes records only after MQTT acknowledgement. Configure it with `--mqtt-cache-path PATH`, `--mqtt-cache-max-size SIZE`, or `--no-mqtt-cache`.

## Optional web frontend

Enable the authenticated web console with `--frontend` after installing `.[web]` or `.[all]`. Default bind is `127.0.0.1:8080`; use `--allow-external-frontend` for a non-loopback address and protect remote access with HTTPS or a TLS reverse proxy. Initial credentials are `admin` / `password`, with mandatory password change at the first login. The console provides responsive desktop/mobile sensor status, admin/reader authorization, persistent runtime settings, local/LDAP/OIDC authentication, TOTP MFA for local/LDAP users, user administration and encrypted import/export of configuration plus available cache/state. Full details are in `docs/FRONTEND.en.md`.

