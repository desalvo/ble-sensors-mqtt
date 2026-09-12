# Production deployment and release criteria

**English** · [Italiano](PRODUCTION.it.md)

Release 1.0.0 is intended for unattended Linux operation. Production-grade here means the application fails closed for unsafe network exposure, isolates plugin failures, bounds untrusted plugin data, exposes liveness/readiness, runs under a sandboxed unprivileged systemd account, and has mandatory automated release gates. It does not make SNMPv2c encrypted or add authentication to the Prometheus endpoint; those services remain loopback by default and require explicit opt-in for external binding.

## Required deployment controls

- Use MQTT TLS with certificate verification for every non-loopback broker. Do not use `--allow-insecure-mqtt` in production.
- Keep Prometheus/health on loopback unless it is behind a firewall, VPN, or authenticated TLS reverse proxy. External binding requires `--allow-external-prometheus`.
- Keep SNMPv2c on loopback. If legacy external SNMPv2c is unavoidable, external binding requires `--allow-external-snmp`; use a VPN/firewall or an SNMPv3 proxy.
- Store every password, community, bind key, and cloud credential in a regular file with mode `0640` or stricter. Never pass secrets on the command line.
- Run with the supplied systemd unit or equivalent least-privilege isolation. The application tree under `/opt` should be root-owned and not writable by the service account.
- Use an assigned enterprise OID with `--snmp-base-oid` for a real production MIB namespace.

## Runtime reliability

MQTT connection startup is successful only after broker CONNACK. QoS publishes are acknowledged before a polling cycle is marked successful. Reconnects use bounded backoff. A sensor retained topic is cleared only after `--stale-cycles` consecutive misses, protecting against one lost BLE scan. The systemd deployment persists the topic/miss state atomically in `/var/lib/ble-sensors-mqtt/state.json`, so stale cleanup survives restarts. Decoder and cloud calls are bounded by `--plugin-timeout`, and cloud providers are polled concurrently and isolated from one another.

The Prometheus HTTP server provides `/healthz` and `/readyz`. Readiness is false before the first successful polling cycle and when the last success is stale. `ble_sensors_cycles_total` and `ble_sensors_cycles_failed_total` expose runtime reliability counters.

## Release gate

A release candidate is not approved until `scripts/release-check.sh` succeeds in an environment with Internet access and the complete `.[all,dev,release]` dependency set. The gate runs compile checks, Ruff, pytest/coverage, Bandit, `pip-audit`, manual generation, wheel/sdist build, `twine check`, CycloneDX SBOM generation, and artifact-content validation. CI executes the runtime suite on Python 3.11, 3.12, and 3.13.

The release should include the wheel, sdist, SBOM, checksums, source project archive, and separate English and Italian manuals.
