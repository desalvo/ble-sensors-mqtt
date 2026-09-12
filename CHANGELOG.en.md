# Changelog

**English** · [Italiano](CHANGELOG.it.md)

## 1.0.0 - 2026-09-12

- GitHub Actions now publishes tagged `v*` releases automatically after all test/build gates pass, with version/tag validation, CI-built assets, consolidated SHA-256 checksums, and idempotent asset updates.
- Production hardening release with fail-closed network exposure rules.
- MQTT waits for CONNACK and publish acknowledgements, uses reconnect backoff, and rejects remote/plaintext or credentialed/plaintext connections unless explicitly allowed.
- Retained MQTT sensor topics are cleared only after a configurable number of consecutive missing cycles (`--stale-cycles`), reducing stale state without reacting to one missed BLE scan.
- Direct `bleak` runtime dependency declared; version output is centralized and reused by SNMP.
- Plugin/cloud polling timeout and concurrent cloud provider polling.
- Prometheus `/healthz` and `/readyz`, plus runtime cycle/failure metrics.
- External unauthenticated Prometheus and plaintext SNMPv2c bindings require explicit opt-in flags.
- Secret files must be regular files with `0640` or stricter permissions; plugin data and MQTT payload size are bounded.
- systemd deployment is root-owned and further sandboxed; idempotent installation helper included.
- CI covers Python 3.11/3.12/3.13 with all optional plugins, lint, tests, coverage, Bandit, `pip-audit`, wheel/sdist build, `twine check`, and CycloneDX SBOM generation.
- Dependabot configuration and release verification script added.
- Standard wheel and sdist are mandatory release artifacts in addition to project archives and separate EN/IT manuals.

## 0.2.0 - 2026-09-11

- Separate cloud plugin registry with `ble_sensors_mqtt.cloud_plugins` entry points and failure isolation.
- Generic `--device ID` allow-list supporting BLE MAC addresses and cloud/plugin identifiers.
- Explicit `.en.md` / `.it.md` naming for README, security, changelog, usage, and AgID documents.
- Expanded contract tests for normalized identity/data across MQTT payloads, Prometheus, and SNMP.
- Complete English and Italian documentation sets with separate PDF manuals; English-only CLI,
  runtime messages, logs, and configuration examples.
- Application logo and updated PDF cover; headings kept with their first following content.
- Plugin architecture with built-in registry and `ble_sensors_mqtt.sensor_plugins` entry point.
- Optional support for Xiaomi/Mijia, Govee, Inkbird, ThermoPro, Qingping/ClearGrass,
  BTHome/Shelly BLU/ATC-PVVX, RuuviTag, SensorPush, Airthings, Mopeka, and Tuya Cloud.
- Normalized `manufacturer`, `model`, and `protocol` identity across MQTT, Prometheus, and SNMP.
- Every scalar exposed through generic Prometheus metrics and an SNMP table.
- Protected cloud TOML configuration and `--sensor-name` aliases for non-MAC identifiers.
- Optional Prometheus and read-only SNMPv2c exporters.
- SNMP MIB, loopback binding by default, and community read from a protected file.
- Configurable IPv4/IPv6 addresses and exporter ports, including explicit external binding.
- Repeatable `--device-name MAC=NAME` aliases propagated to every output and scan result.

## 0.1.0 - 2026-09-11

- Initial multi-sensor plugin gateway with continuous polling and MQTT publishing.
- TLS, file-based password authentication, MAC allow-list, and hardened systemd unit.
- Tests, linting, static analysis, and dependency auditing in CI.
