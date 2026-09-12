#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

src_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
install_root=${INSTALL_ROOT:-/opt/ble-sensors-mqtt}
config_root=${CONFIG_ROOT:-/etc/ble-sensors-mqtt}

if ! getent group ble-sensors-mqtt >/dev/null 2>&1; then
  groupadd --system ble-sensors-mqtt
fi
if ! id ble-sensors-mqtt >/dev/null 2>&1; then
  useradd --system --gid ble-sensors-mqtt --home-dir "$install_root" --shell /usr/sbin/nologin ble-sensors-mqtt
fi
if getent group bluetooth >/dev/null 2>&1; then
  usermod -a -G bluetooth ble-sensors-mqtt
fi

install -d -m 0755 -o root -g root "$install_root"
install -d -m 0750 -o root -g ble-sensors-mqtt "$config_root"

# Replace application sources while preserving the isolated virtual environment.
for item in src assets config docs systemd scripts; do
  rm -rf "$install_root/$item"
  cp -a "$src_dir/$item" "$install_root/$item"
done
for item in pyproject.toml MANIFEST.in VERSION BUILD LICENSE README.en.md README.it.md \
            SECURITY.en.md SECURITY.it.md CHANGELOG.en.md CHANGELOG.it.md; do
  install -m 0644 "$src_dir/$item" "$install_root/$item"
done
find "$install_root" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$install_root" -type f -name '*.pyc' -delete
chown -R root:root "$install_root"

if [ ! -x "$install_root/.venv/bin/python" ]; then
  python3 -m venv "$install_root/.venv"
fi
"$install_root/.venv/bin/python" -m pip install --upgrade pip
"$install_root/.venv/bin/pip" install --upgrade "$install_root[all]"
chown -R root:root "$install_root/.venv"

if [ ! -e "$config_root/environment" ]; then
  install -m 0640 -o root -g ble-sensors-mqtt "$src_dir/config/environment.example" "$config_root/environment"
fi
install -m 0644 "$src_dir/systemd/ble-sensors-mqtt.service" /etc/systemd/system/ble-sensors-mqtt.service
systemctl daemon-reload

echo "Installed. Create $config_root/mqtt-password (0640 root:ble-sensors-mqtt), edit $config_root/environment, then run:"
echo "  systemctl enable --now ble-sensors-mqtt"
