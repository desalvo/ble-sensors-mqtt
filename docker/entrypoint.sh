#!/bin/sh
set -eu
is_true(){ case "${1:-}" in 1|true|TRUE|yes|YES|on|ON)return 0;;*)return 1;;esac; }
: "${MQTT_HOST:?MQTT_HOST must be set}"
set -- --mqtt-host "$MQTT_HOST" --poll-interval "${POLL_INTERVAL:-30}" --scan-duration "${SCAN_DURATION:-8}" --state-file "${STATE_FILE:-/var/lib/ble-sensors-mqtt/state.json}"
if is_true "${MQTT_CACHE_ENABLED:-true}";then set -- "$@" --mqtt-cache --mqtt-cache-path "${MQTT_CACHE_PATH:-/var/lib/ble-sensors-mqtt/mqtt-cache.sqlite3}" --mqtt-cache-max-size "${MQTT_CACHE_MAX_SIZE:-1GiB}";else set -- "$@" --no-mqtt-cache;fi
is_true "${REUSE_STALE_DATA:-false}"&&set -- "$@" --reuse-stale-data
[ -z "${BLUETOOTH_ADAPTER:-}" ]||set -- "$@" --bluetooth-adapter "$BLUETOOTH_ADAPTER"
[ -z "${MQTT_PORT:-}" ]||set -- "$@" --mqtt-port "$MQTT_PORT";[ -z "${MQTT_USERNAME:-}" ]||set -- "$@" --mqtt-username "$MQTT_USERNAME"
pw=${MQTT_PASSWORD_FILE:-/run/secrets/mqtt-password};[ ! -f "$pw" ]||set -- "$@" --mqtt-password-file "$pw"
if is_true "${MQTT_TLS:-true}";then set -- "$@" --mqtt-tls --mqtt-ca-file "${MQTT_CA_FILE:-/etc/ssl/certs/ca-certificates.crt}";elif is_true "${ALLOW_INSECURE_MQTT:-false}";then set -- "$@" --allow-insecure-mqtt;fi
[ -z "${MQTT_TOPIC_PREFIX:-}" ]||set -- "$@" --mqtt-topic-prefix "$MQTT_TOPIC_PREFIX"
if is_true "${HOME_ASSISTANT_DISCOVERY:-false}";then set -- "$@" --home-assistant-discovery;[ -z "${HOME_ASSISTANT_DISCOVERY_PREFIX:-}" ]||set -- "$@" --home-assistant-discovery-prefix "$HOME_ASSISTANT_DISCOVERY_PREFIX";fi
if is_true "${PROMETHEUS_ENABLED:-true}";then set -- "$@" --prometheus --prometheus-host "${PROMETHEUS_HOST:-0.0.0.0}" --prometheus-port "${PROMETHEUS_PORT:-9105}";is_true "${ALLOW_EXTERNAL_PROMETHEUS:-true}"&&set -- "$@" --allow-external-prometheus;fi
if is_true "${SNMP_ENABLED:-false}";then comm=${SNMP_COMMUNITY_FILE:-/run/secrets/snmp-community};[ -f "$comm" ]||{ echo "missing SNMP community file: $comm" >&2;exit 2; };set -- "$@" --snmp --snmp-host "${SNMP_HOST:-0.0.0.0}" --snmp-port "${SNMP_PORT:-1161}" --snmp-community-file "$comm";is_true "${ALLOW_EXTERNAL_SNMP:-true}"&&set -- "$@" --allow-external-snmp;fi
if is_true "${FRONTEND_ENABLED:-false}";then set -- "$@" --frontend --frontend-host "${FRONTEND_HOST:-0.0.0.0}" --frontend-port "${FRONTEND_PORT:-8080}" --frontend-data-dir "${FRONTEND_DATA_DIR:-/var/lib/ble-sensors-mqtt/frontend}";is_true "${ALLOW_EXTERNAL_FRONTEND:-true}"&&set -- "$@" --allow-external-frontend;[ -z "${FRONTEND_TLS_CERT:-}" ]||set -- "$@" --frontend-tls-cert "$FRONTEND_TLS_CERT";[ -z "${FRONTEND_TLS_KEY:-}" ]||set -- "$@" --frontend-tls-key "$FRONTEND_TLS_KEY";fi
[ -z "${CLOUD_CONFIG:-}" ]||set -- "$@" --cloud-config "$CLOUD_CONFIG"
extra=${EXTRA_ARGS_FILE:-/etc/ble-sensors-mqtt/arguments};if [ -f "$extra" ];then while IFS= read -r arg||[ -n "$arg" ];do [ -z "$arg" ]&&continue;case "$arg" in \#*)continue;;esac;set -- "$@" "$arg";done < "$extra";fi
exec ble-sensors-mqtt "$@"
