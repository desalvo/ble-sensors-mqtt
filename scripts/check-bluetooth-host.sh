#!/usr/bin/env bash
set -uo pipefail

strict=false
quiet=false
while (($#)); do
  case "$1" in
    --strict) strict=true; shift ;;
    --quiet) quiet=true; shift ;;
    -h|--help)
      cat <<'HELP'
Check whether a Linux host is ready to expose its Bluetooth adapter through
host BlueZ/system D-Bus to ble-sensors-mqtt, systemd, Docker, or Kubernetes.

Usage: scripts/check-bluetooth-host.sh [--strict] [--quiet]
  --strict  return non-zero when a required item is missing, blocked or off
  --quiet   print only warnings/errors and the final result
HELP
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

failures=0
warnings=0
ok() { [[ $quiet == true ]] || printf '[OK] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; warnings=$((warnings + 1)); }
fail() { printf '[FAIL] %s\n' "$*" >&2; failures=$((failures + 1)); }

if [[ -S /run/dbus/system_bus_socket ]]; then
  ok 'system D-Bus socket exists at /run/dbus/system_bus_socket'
else
  fail 'missing /run/dbus/system_bus_socket; start/install the system D-Bus service'
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-active --quiet bluetooth.service 2>/dev/null; then
    ok 'bluetooth.service is active'
  else
    fail 'bluetooth.service is not active; run: sudo systemctl enable --now bluetooth'
  fi
fi

if command -v bluetoothctl >/dev/null 2>&1; then
  adapters=$(bluetoothctl list 2>/dev/null || true)
  if [[ -n $adapters ]]; then
    ok 'BlueZ sees at least one Bluetooth controller'
    [[ $quiet == true ]] || printf '%s\n' "$adapters" | sed 's/^/     /'
  else
    fail 'BlueZ does not see a Bluetooth controller; check USB/UART hardware and rfkill'
  fi

  powered=$(bluetoothctl show 2>/dev/null | awk -F': ' '/^[[:space:]]*Powered:/{print $2; exit}')
  case "$powered" in
    yes) ok 'default Bluetooth controller is powered' ;;
    no) fail 'default Bluetooth controller is powered off; run: bluetoothctl power on' ;;
    *) warn 'could not determine whether the default controller is powered' ;;
  esac
else
  fail 'bluetoothctl is missing; install the BlueZ package (usually: bluez)'
fi

if command -v rfkill >/dev/null 2>&1; then
  rfkill_output=$(rfkill list bluetooth 2>/dev/null || true)
  if grep -qi 'Soft blocked: yes' <<<"$rfkill_output"; then
    fail 'Bluetooth is soft-blocked; run: sudo rfkill unblock bluetooth'
  elif grep -qi 'Hard blocked: yes' <<<"$rfkill_output"; then
    fail 'Bluetooth is hard-blocked; enable it in hardware/firmware/BIOS'
  elif [[ -n $rfkill_output ]]; then
    ok 'Bluetooth is not blocked by rfkill'
  else
    warn 'rfkill reports no Bluetooth entry'
  fi
else
  warn 'rfkill is not installed; blocking state was not checked'
fi

if command -v busctl >/dev/null 2>&1; then
  if busctl --system --no-pager list 2>/dev/null | grep -q 'org.bluez'; then
    ok 'org.bluez is present on the system D-Bus'
  else
    fail 'org.bluez is not present on the system D-Bus; check bluetooth.service/BlueZ'
  fi
else
  warn 'busctl is not installed; org.bluez D-Bus ownership was not checked'
fi

if ((failures)); then
  printf 'Bluetooth host check: %d failure(s), %d warning(s).\n' "$failures" "$warnings" >&2
  [[ $strict == true ]] && exit 1
else
  printf 'Bluetooth host check: ready (%d warning(s)).\n' "$warnings"
fi
