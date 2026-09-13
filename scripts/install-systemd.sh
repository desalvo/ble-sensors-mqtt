#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install and configure ble-sensors-mqtt as a hardened systemd service.

Interactive mode is the default. Values supplied on the command line become
prompt defaults and are preserved if Enter is pressed. Repeatable options
already supplied on the CLI are kept and the interactive wizard can append
more values. Use --non-interactive to install exactly from CLI/default values.

Usage: sudo scripts/install-systemd.sh [options]
  --non-interactive
  --mqtt-host HOST                 required
  --mqtt-port PORT                 default 8883
  --mqtt-topic-prefix PREFIX       default ble-sensors
  --mqtt-username USER
  --mqtt-password-file FILE        copied securely into /etc
  --mqtt-tls | --no-mqtt-tls       default TLS enabled
  --mqtt-ca-file FILE              default system CA bundle
  --allow-insecure-mqtt
  --poll-interval SEC              default 30
  --scan-duration SEC              default 8
  --device ID                      repeatable
  --device-name MAC=NAME           repeatable
  --sensor-name ID=NAME            repeatable
  --home-assistant-discovery
  --home-assistant-discovery-prefix PREFIX   default homeassistant
  --prometheus
  --prometheus-host IP             default 127.0.0.1
  --prometheus-port PORT           default 9105
  --allow-external-prometheus
  --snmp
  --snmp-host IP                   default 127.0.0.1
  --snmp-port PORT                 default 1161
  --snmp-community-file FILE
  --allow-external-snmp
  --cloud-config FILE
  --extra-arg ARG                  repeatable raw application argument
  --enable | --no-enable           default enable
  --start | --no-start             default start/restart
  --install-root DIR               default /opt/ble-sensors-mqtt
  --config-root DIR                default /etc/ble-sensors-mqtt
EOF
}

bool_prompt() {
  local label=$1 current=$2 answer suffix
  if [[ $current == true ]]; then
    suffix='Y/n'
  else
    suffix='y/N'
  fi
  read -r -p "$label [$suffix]: " answer
  case "${answer,,}" in
    y|yes|s|si) printf '%s' true ;;
    n|no) printf '%s' false ;;
    *) printf '%s' "$current" ;;
  esac
}

value_prompt() {
  local label=$1 current=$2 answer
  read -r -p "$label [$current]: " answer
  printf '%s' "${answer:-$current}"
}

append_prompt() {
  local label=$1 array_name=$2 answer
  local -n target=$array_name
  if ((${#target[@]})); then
    printf '%s\n' "$label already supplied:"
    printf '  %s\n' "${target[@]}"
  fi
  while true; do
    read -r -p "$label (blank to finish): " answer
    [[ -z $answer ]] && break
    target+=("$answer")
  done
}

interactive=true
mqtt_host=''
mqtt_port=8883
mqtt_topic_prefix='ble-sensors'
mqtt_username=''
mqtt_password_source=''
mqtt_tls=true
mqtt_ca_file='/etc/ssl/certs/ca-certificates.crt'
allow_insecure_mqtt=false
poll_interval=30
scan_duration=8
home_assistant_discovery=false
home_assistant_discovery_prefix='homeassistant'
prometheus=false
prometheus_host='127.0.0.1'
prometheus_port=9105
allow_external_prometheus=false
snmp=false
snmp_host='127.0.0.1'
snmp_port=1161
snmp_community_source=''
allow_external_snmp=false
cloud_config_source=''
enable_service=true
start_service=true
install_root=${INSTALL_ROOT:-/opt/ble-sensors-mqtt}
config_root=${CONFIG_ROOT:-/etc/ble-sensors-mqtt}
device_args=()
device_name_args=()
sensor_name_args=()
extra_args=()

while (($#)); do
  case "$1" in
    --non-interactive) interactive=false; shift ;;
    --mqtt-host) mqtt_host=${2:?}; shift 2 ;;
    --mqtt-port) mqtt_port=${2:?}; shift 2 ;;
    --mqtt-topic-prefix) mqtt_topic_prefix=${2:?}; shift 2 ;;
    --mqtt-username) mqtt_username=${2:?}; shift 2 ;;
    --mqtt-password-file) mqtt_password_source=${2:?}; shift 2 ;;
    --mqtt-tls) mqtt_tls=true; shift ;;
    --no-mqtt-tls) mqtt_tls=false; shift ;;
    --mqtt-ca-file) mqtt_ca_file=${2:?}; shift 2 ;;
    --allow-insecure-mqtt) allow_insecure_mqtt=true; shift ;;
    --poll-interval) poll_interval=${2:?}; shift 2 ;;
    --scan-duration) scan_duration=${2:?}; shift 2 ;;
    --device) device_args+=("${2:?}"); shift 2 ;;
    --device-name) device_name_args+=("${2:?}"); shift 2 ;;
    --sensor-name) sensor_name_args+=("${2:?}"); shift 2 ;;
    --home-assistant-discovery) home_assistant_discovery=true; shift ;;
    --home-assistant-discovery-prefix) home_assistant_discovery_prefix=${2:?}; shift 2 ;;
    --prometheus) prometheus=true; shift ;;
    --prometheus-host) prometheus_host=${2:?}; shift 2 ;;
    --prometheus-port) prometheus_port=${2:?}; shift 2 ;;
    --allow-external-prometheus) allow_external_prometheus=true; shift ;;
    --snmp) snmp=true; shift ;;
    --snmp-host) snmp_host=${2:?}; shift 2 ;;
    --snmp-port) snmp_port=${2:?}; shift 2 ;;
    --snmp-community-file) snmp_community_source=${2:?}; shift 2 ;;
    --allow-external-snmp) allow_external_snmp=true; shift ;;
    --cloud-config) cloud_config_source=${2:?}; shift 2 ;;
    --extra-arg) extra_args+=("${2:?}"); shift 2 ;;
    --enable) enable_service=true; shift ;;
    --no-enable) enable_service=false; shift ;;
    --start) start_service=true; shift ;;
    --no-start) start_service=false; shift ;;
    --install-root) install_root=${2:?}; shift 2 ;;
    --config-root) config_root=${2:?}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ $(id -u) -ne 0 ]]; then
  echo 'run as root (for example with sudo)' >&2
  exit 1
fi

if [[ $interactive == true ]]; then
  echo 'ble-sensors-mqtt systemd configuration; Enter keeps the shown default.'
  mqtt_host=$(value_prompt 'MQTT host' "$mqtt_host")
  mqtt_tls=$(bool_prompt 'Use verified MQTT TLS?' "$mqtt_tls")
  if [[ $mqtt_tls == true && $mqtt_port == 1883 ]]; then
    mqtt_port=8883
  elif [[ $mqtt_tls == false && $mqtt_port == 8883 ]]; then
    mqtt_port=1883
  fi
  mqtt_port=$(value_prompt 'MQTT port' "$mqtt_port")
  mqtt_topic_prefix=$(value_prompt 'MQTT topic prefix' "$mqtt_topic_prefix")
  if [[ $mqtt_tls == false ]]; then
    allow_insecure_mqtt=$(bool_prompt \
      'Allow remote/plaintext MQTT explicitly?' "$allow_insecure_mqtt")
  fi
  mqtt_username=$(value_prompt 'MQTT username (blank for none)' "$mqtt_username")
  mqtt_password_source=$(value_prompt \
    'MQTT password file to copy (blank for none)' "$mqtt_password_source")
  poll_interval=$(value_prompt 'Polling interval seconds' "$poll_interval")
  scan_duration=$(value_prompt 'BLE scan duration seconds' "$scan_duration")

  append_prompt 'Allowed sensor ID' device_args
  append_prompt 'BLE alias MAC=NAME' device_name_args
  append_prompt 'Generic/cloud alias ID=NAME' sensor_name_args

  cloud_config_source=$(value_prompt \
    'Cloud provider TOML file to copy (blank for none)' "$cloud_config_source")
  home_assistant_discovery=$(bool_prompt \
    'Enable Home Assistant MQTT Discovery?' "$home_assistant_discovery")
  if [[ $home_assistant_discovery == true ]]; then
    home_assistant_discovery_prefix=$(value_prompt \
      'Home Assistant discovery prefix' "$home_assistant_discovery_prefix")
  fi

  prometheus=$(bool_prompt 'Enable Prometheus/health endpoint?' "$prometheus")
  if [[ $prometheus == true ]]; then
    prometheus_host=$(value_prompt 'Prometheus bind IP' "$prometheus_host")
    prometheus_port=$(value_prompt 'Prometheus TCP port' "$prometheus_port")
    if [[ $prometheus_host != 127.0.0.1 && $prometheus_host != ::1 ]]; then
      allow_external_prometheus=$(bool_prompt \
        'Allow external unauthenticated Prometheus?' "$allow_external_prometheus")
    fi
  fi

  snmp=$(bool_prompt 'Enable SNMPv2c?' "$snmp")
  if [[ $snmp == true ]]; then
    snmp_host=$(value_prompt 'SNMP bind IP' "$snmp_host")
    snmp_port=$(value_prompt 'SNMP UDP port' "$snmp_port")
    snmp_community_source=$(value_prompt \
      'SNMP community file to copy' "$snmp_community_source")
    if [[ $snmp_host != 127.0.0.1 && $snmp_host != ::1 ]]; then
      allow_external_snmp=$(bool_prompt \
        'Allow external plaintext SNMPv2c?' "$allow_external_snmp")
    fi
  fi

  append_prompt 'Additional raw ble-sensors-mqtt argument' extra_args
  enable_service=$(bool_prompt 'Enable service at boot?' "$enable_service")
  start_service=$(bool_prompt 'Start/restart service now?' "$start_service")
fi

[[ -n $mqtt_host ]] || { echo '--mqtt-host is required' >&2; exit 2; }
[[ -z $mqtt_password_source || -n $mqtt_username ]] || {
  echo '--mqtt-password-file requires --mqtt-username' >&2
  exit 2
}
[[ $snmp != true || -n $snmp_community_source ]] || {
  echo 'SNMP requires --snmp-community-file' >&2
  exit 2
}

for source in "$mqtt_password_source" "$snmp_community_source" "$cloud_config_source"; do
  [[ -z $source || -f $source ]] || { echo "file not found: $source" >&2; exit 2; }
done

src_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

getent group ble-sensors-mqtt >/dev/null 2>&1 || groupadd --system ble-sensors-mqtt
id ble-sensors-mqtt >/dev/null 2>&1 || useradd \
  --system --gid ble-sensors-mqtt --home-dir "$install_root" \
  --shell /usr/sbin/nologin ble-sensors-mqtt
getent group bluetooth >/dev/null 2>&1 && \
  usermod -a -G bluetooth ble-sensors-mqtt || true

install -d -m 0755 -o root -g root "$install_root"
install -d -m 0750 -o root -g ble-sensors-mqtt "$config_root"

for item in src assets config docs systemd scripts docker kubernetes; do
  if [[ -e $src_dir/$item ]]; then
    rm -rf "$install_root/$item"
    cp -a "$src_dir/$item" "$install_root/$item"
  fi
done
for item in \
  pyproject.toml MANIFEST.in VERSION BUILD LICENSE README.md README.en.md README.it.md \
  SECURITY.en.md SECURITY.it.md CHANGELOG.en.md CHANGELOG.it.md; do
  [[ -e $src_dir/$item ]] && install -m 0644 "$src_dir/$item" "$install_root/$item"
done

find "$install_root" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$install_root" -type f -name '*.pyc' -delete
chown -R root:root "$install_root"

if [[ ! -x $install_root/.venv/bin/python ]]; then
  python3 -m venv "$install_root/.venv"
fi
"$install_root/.venv/bin/python" -m pip install --upgrade pip 'setuptools>=83' wheel
"$install_root/.venv/bin/pip" install --upgrade "$install_root[all]"
chown -R root:root "$install_root/.venv"

copy_secret() {
  install -m 0640 -o root -g ble-sensors-mqtt "$1" "$2"
}

mqtt_password_dest=''
if [[ -n $mqtt_password_source ]]; then
  mqtt_password_dest="$config_root/mqtt-password"
  copy_secret "$mqtt_password_source" "$mqtt_password_dest"
fi

snmp_community_dest=''
if [[ -n $snmp_community_source ]]; then
  snmp_community_dest="$config_root/snmp-community"
  copy_secret "$snmp_community_source" "$snmp_community_dest"
fi

cloud_config_dest=''
if [[ -n $cloud_config_source ]]; then
  cloud_config_dest="$config_root/cloud.toml"
  copy_secret "$cloud_config_source" "$cloud_config_dest"
fi

args=(
  --mqtt-host "$mqtt_host"
  --mqtt-port "$mqtt_port"
  --mqtt-topic-prefix "$mqtt_topic_prefix"
  --poll-interval "$poll_interval"
  --scan-duration "$scan_duration"
  --state-file /var/lib/ble-sensors-mqtt/state.json
)
[[ -z $mqtt_username ]] || args+=(--mqtt-username "$mqtt_username")
[[ -z $mqtt_password_dest ]] || args+=(--mqtt-password-file "$mqtt_password_dest")
if [[ $mqtt_tls == true ]]; then
  args+=(--mqtt-tls --mqtt-ca-file "$mqtt_ca_file")
elif [[ $allow_insecure_mqtt == true ]]; then
  args+=(--allow-insecure-mqtt)
fi
if [[ $home_assistant_discovery == true ]]; then
  args+=(--home-assistant-discovery \
    --home-assistant-discovery-prefix "$home_assistant_discovery_prefix")
fi
if [[ $prometheus == true ]]; then
  args+=(--prometheus --prometheus-host "$prometheus_host" --prometheus-port "$prometheus_port")
  [[ $allow_external_prometheus == false ]] || args+=(--allow-external-prometheus)
fi
if [[ $snmp == true ]]; then
  args+=(--snmp --snmp-host "$snmp_host" --snmp-port "$snmp_port" \
    --snmp-community-file "$snmp_community_dest")
  [[ $allow_external_snmp == false ]] || args+=(--allow-external-snmp)
fi
[[ -z $cloud_config_dest ]] || args+=(--cloud-config "$cloud_config_dest")
for value in "${device_args[@]}"; do args+=(--device "$value"); done
for value in "${device_name_args[@]}"; do args+=(--device-name "$value"); done
for value in "${sensor_name_args[@]}"; do args+=(--sensor-name "$value"); done
args+=("${extra_args[@]}")

python3 - "$config_root/service-args.json" "${args[@]}" <<'PY'
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
fd, temporary = tempfile.mkstemp(prefix=".service-args.", dir=path.parent)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(sys.argv[2:], handle, ensure_ascii=False, indent=2)
    handle.write("\n")
os.chmod(temporary, 0o640)
os.replace(temporary, path)
PY
chown root:ble-sensors-mqtt "$config_root/service-args.json"

# Parse the final vector with the installed application before touching systemd.
"$install_root/.venv/bin/python" - "$config_root/service-args.json" <<'PY'
import json
import sys
from pathlib import Path

from ble_sensors_mqtt.cli import parser

args = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
parser().parse_args(args)
PY

python3 - \
  "$src_dir/systemd/ble-sensors-mqtt.service" \
  /etc/systemd/system/ble-sensors-mqtt.service \
  "$install_root" "$config_root" <<'PY'
import sys
from pathlib import Path

source, destination, install_root, config_root = sys.argv[1:]
text = Path(source).read_text(encoding="utf-8")
text = text.replace("/opt/ble-sensors-mqtt", install_root)
text = text.replace("/etc/ble-sensors-mqtt", config_root)
Path(destination).write_text(text, encoding="utf-8")
PY
chmod 0644 /etc/systemd/system/ble-sensors-mqtt.service

systemctl daemon-reload
if [[ $enable_service == true ]]; then
  systemctl enable ble-sensors-mqtt
else
  systemctl disable ble-sensors-mqtt >/dev/null 2>&1 || true
fi
if [[ $start_service == true ]]; then
  systemctl restart ble-sensors-mqtt
fi

echo "Installed. Arguments: $config_root/service-args.json"
echo 'Logs: journalctl -u ble-sensors-mqtt -f'
