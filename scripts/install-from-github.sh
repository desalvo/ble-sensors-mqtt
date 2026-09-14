#!/usr/bin/env bash
set -euo pipefail

repo_url='https://github.com/desalvo/ble-sensors-mqtt.git'
ref='main'
clone_dir='/usr/local/src/ble-sensors-mqtt'
clone_dir_explicit=false
install_system_deps=true
run_bluetooth_check=true
installer_args=()

usage() {
  cat <<'HELP'
Easy bootstrap installer for ble-sensors-mqtt on systemd Linux hosts.

Supported package-manager families include Debian/Ubuntu/Raspberry Pi OS and
RHEL/Rocky/AlmaLinux/CentOS/Fedora. Both x86_64 and ARM64 hosts are supported.

It installs common host prerequisites, uses the current Git clone when run
inside one (otherwise clones/updates GitHub), checks host Bluetooth/BlueZ
readiness, then delegates to install-systemd.sh,
which creates the Python virtualenv and hardened systemd service.

Usage:
  sudo scripts/install-from-github.sh [bootstrap options] [install-systemd options]

Bootstrap options:
  --repo-url URL          default https://github.com/desalvo/ble-sensors-mqtt.git
  --ref REF               branch/tag/commit to install; default main
  --clone-dir DIR         clone/update this directory instead of using the current clone
  --skip-system-deps      do not install git/python/venv/BlueZ/rfkill packages
  --skip-bluetooth-check  skip host Bluetooth preflight
  --help

All unrecognised options and all arguments after -- are passed unchanged to
scripts/install-systemd.sh. Therefore interactive mode is the default and starts
by asking which optional components to install: BLE sensor decoder packs, cloud
providers and the authenticated web frontend. CLI values remain the wizard
defaults. Pass --non-interactive together with --with/--without-sensors,
--with/--without-cloud and --with/--without-web for unattended provisioning.
Sensor retry/stale options are forwarded too: --sensor-retry-attempts N and
--sensor-stale-cycles N. History options are forwarded too: --history-retention-days DAYS and
--history-path FILE.

Examples:
  sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net --prometheus
  sudo scripts/install-from-github.sh --ref v1.0.0 --non-interactive \
    --with-sensors --without-cloud --with-web \
    --mqtt-host mqtt.example.net --mqtt-tls --home-assistant-discovery \
    --history-retention-days 30
HELP
}

while (($#)); do
  case "$1" in
    --repo-url) repo_url=${2:?}; shift 2 ;;
    --ref) ref=${2:?}; shift 2 ;;
    --clone-dir) clone_dir=${2:?}; clone_dir_explicit=true; shift 2 ;;
    --skip-system-deps) install_system_deps=false; shift ;;
    --skip-bluetooth-check) run_bluetooth_check=false; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; installer_args+=("$@"); break ;;
    *) installer_args+=("$@"); break ;;
  esac
done

if [[ $(id -u) -ne 0 ]]; then
  echo 'run as root (for example with sudo)' >&2
  exit 1
fi

install_deps() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y git python3 python3-venv python3-pip bluez rfkill dbus usbutils
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y git python3 python3-pip bluez rfkill dbus usbutils
  elif command -v yum >/dev/null 2>&1; then
    yum install -y git python3 python3-pip bluez rfkill dbus usbutils
  else
    echo 'Unsupported package manager. Install git, Python >=3.11 with venv, BlueZ, rfkill, D-Bus and (optionally) usbutils, then rerun with --skip-system-deps.' >&2
    exit 2
  fi
}

if [[ $install_system_deps == true ]]; then
  install_deps
fi

command -v git >/dev/null 2>&1 || { echo 'git is required' >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo 'python3 is required' >&2; exit 2; }

python3 - <<'PYVER'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")
PYVER

script_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd || true)
source_dir=''
if [[ $clone_dir_explicit == false && -n $script_root && -d $script_root/.git ]]; then
  source_dir=$script_root
  echo "Using current Git clone: $source_dir"
else
  source_dir=$clone_dir
  mkdir -p "$(dirname "$source_dir")"
  if [[ -d $source_dir/.git ]]; then
    if [[ -n $(git -C "$source_dir" status --porcelain) ]]; then
      echo "refusing to update dirty clone: $source_dir" >&2
      exit 2
    fi
    current_origin=$(git -C "$source_dir" remote get-url origin 2>/dev/null || true)
    if [[ -n $current_origin && $current_origin != "$repo_url" ]]; then
      echo "existing clone origin differs: $current_origin" >&2
      exit 2
    fi
    git -C "$source_dir" fetch --tags --prune origin
  else
    rm -rf "$source_dir"
    git clone "$repo_url" "$source_dir"
    git -C "$source_dir" fetch --tags --prune origin
  fi
fi

# Only change revisions when --ref was explicitly useful for a managed clone or
# when the requested ref differs from the current checkout.
if [[ $source_dir != "$script_root" || $ref != main ]]; then
  git -C "$source_dir" fetch --tags --prune origin >/dev/null 2>&1 || true
  target=$ref
  if git -C "$source_dir" show-ref --verify --quiet "refs/remotes/origin/$ref"; then
    target="origin/$ref"
  elif git -C "$source_dir" show-ref --verify --quiet "refs/tags/$ref"; then
    target="refs/tags/$ref"
  fi
  git -C "$source_dir" rev-parse --verify "$target^{commit}" >/dev/null 2>&1 || {
    echo "cannot resolve ref: $ref" >&2
    exit 2
  }
  if [[ -n $(git -C "$source_dir" status --porcelain) ]]; then
    echo "refusing to change ref in dirty clone: $source_dir" >&2
    exit 2
  fi
  git -C "$source_dir" checkout --detach "$target"
fi

if [[ $run_bluetooth_check == true ]]; then
  "$source_dir/scripts/check-bluetooth-host.sh" || true
fi

exec "$source_dir/scripts/install-systemd.sh" "${installer_args[@]}"
