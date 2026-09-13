# systemd deployment

`ble-sensors-mqtt` is designed to run continuously as an unprivileged Linux daemon. The supplied installer creates a dedicated account, an isolated Python virtual environment, root-owned configuration, persistent runtime state and a hardened systemd unit.

## Prerequisites

Install Python 3.11 or newer, `python3-venv`, BlueZ and systemd. The host Bluetooth adapter must already work with BlueZ. The installer must be run as root, normally through `sudo`.


## Easy installation directly from GitHub

For a new Linux host, `scripts/install-from-github.sh` installs common prerequisites, uses the current clone or clones/updates `https://github.com/desalvo/ble-sensors-mqtt.git`, checks host BlueZ/Bluetooth readiness, then delegates to `install-systemd.sh`. The latter creates the virtualenv and hardened systemd service.

Interactive installation from a clone:

```bash
git clone https://github.com/desalvo/ble-sensors-mqtt.git
cd ble-sensors-mqtt
sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net --prometheus
```

Unattended installation:

```bash
sudo scripts/install-from-github.sh --ref main --non-interactive \
  --mqtt-host mqtt.example.net --mqtt-tls \
  --home-assistant-discovery --prometheus
```

Use a release tag such as `--ref v1.0.0` for a pinned installation. When run inside a Git clone, the script uses that checkout directly. Outside a clone it manages `/usr/local/src/ble-sensors-mqtt`; the runtime installation remains under `/opt/ble-sensors-mqtt`. Use `--skip-system-deps` when host packages are managed separately and `--skip-bluetooth-check` only for cloud-only deployments or when Bluetooth validation is performed separately.

The bootstrap script supports `apt`, `dnf`, and `yum`; other distributions must provide Git, Python >=3.11 with venv support, BlueZ, D-Bus, and `rfkill` before using `--skip-system-deps`.

## Host Bluetooth validation

Before installation or while troubleshooting, run:

```bash
sudo scripts/check-bluetooth-host.sh --strict
```

The check verifies `/run/dbus/system_bus_socket`, `bluetooth.service`, at least one BlueZ controller, its `Powered` state, `rfkill`, and the `org.bluez` name on the system D-Bus. Common corrective actions are:

```bash
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
bluetoothctl list
bluetoothctl show
bluetoothctl power on
```

The daemon uses the host BlueZ service through system D-Bus and therefore does not need privileged direct HCI access. The installer adds the `ble-sensors-mqtt` service user to the host `bluetooth` group when that group exists.

## Interactive installation

Interactive mode is the default:

```bash
sudo scripts/install-systemd.sh --mqtt-host mqtt.example.net
```

Every CLI value is used as the default shown by the wizard. Press Enter to keep it. Values already supplied with repeatable options such as `--device`, `--device-name`, `--sensor-name` and `--extra-arg` are retained; the wizard can append more values.

Example with useful defaults pre-filled:

```bash
sudo scripts/install-systemd.sh \
  --mqtt-host mqtt.example.net \
  --mqtt-username ble-sensors-publisher \
  --device-name 'AA:BB:CC:DD:EE:01=Living room' \
  --home-assistant-discovery \
  --prometheus
```

## Non-interactive installation

Use `--non-interactive` to install only from command-line/default values and ask no questions:

```bash
sudo scripts/install-systemd.sh --non-interactive \
  --mqtt-host mqtt.example.net \
  --mqtt-port 8883 \
  --mqtt-tls \
  --mqtt-username ble-sensors-publisher \
  --mqtt-password-file ./mqtt-password \
  --device-name 'AA:BB:CC:DD:EE:01=Living room' \
  --device-name 'AA:BB:CC:DD:EE:02=Bedroom' \
  --home-assistant-discovery \
  --prometheus
```

Run `scripts/install-systemd.sh --help` for every supported provisioning option.

## What the installer creates

The default layout is:

- application and virtual environment: `/opt/ble-sensors-mqtt`;
- protected configuration: `/etc/ble-sensors-mqtt`;
- service argument vector: `/etc/ble-sensors-mqtt/service-args.json`;
- persistent state: `/var/lib/ble-sensors-mqtt/state.json`;
- unit: `/etc/systemd/system/ble-sensors-mqtt.service`;
- service account/group: `ble-sensors-mqtt`.

The argument file is a JSON array, not shell text. This preserves repeated options and values containing spaces without `eval`, shell expansion or quoting ambiguity. Secret files supplied to the installer are copied root-owned and readable by the service group only. The completed vector is parsed by the installed application before systemd is changed.

## Manual installation

The installer is preferred, but the equivalent manual setup is:

```bash
sudo useradd --system --home-dir /opt/ble-sensors-mqtt \
  --shell /usr/sbin/nologin ble-sensors-mqtt
sudo install -d -m 0755 /opt/ble-sensors-mqtt
sudo install -d -m 0750 -o root -g ble-sensors-mqtt /etc/ble-sensors-mqtt
sudo cp -a . /opt/ble-sensors-mqtt/
sudo python3 -m venv /opt/ble-sensors-mqtt/.venv
sudo /opt/ble-sensors-mqtt/.venv/bin/pip install --upgrade \
  pip 'setuptools>=83' wheel '/opt/ble-sensors-mqtt[all]'
```

Create `/etc/ble-sensors-mqtt/service-args.json`, for example:

```json
[
  "--mqtt-host", "mqtt.example.net",
  "--mqtt-port", "8883",
  "--mqtt-tls",
  "--prometheus",
  "--state-file", "/var/lib/ble-sensors-mqtt/state.json"
]
```

Then install the supplied unit:

```bash
sudo cp systemd/ble-sensors-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ble-sensors-mqtt
```

If the application is installed somewhere other than `/opt/ble-sensors-mqtt` or configuration somewhere other than `/etc/ble-sensors-mqtt`, adjust `ExecStart` in the unit. For BLE access, add the service user to the host `bluetooth` group when that group exists.

## Operation

```bash
sudo systemctl status ble-sensors-mqtt
sudo systemctl restart ble-sensors-mqtt
journalctl -u ble-sensors-mqtt -f
```

To change settings, edit the JSON argument array or rerun the installer with the desired options, then restart the service. Keep the service account unprivileged and the application/configuration trees non-writable by it.
