# Security assessment and AgID alignment

**English** · [Italiano](AGID-SECURITY.it.md)

## Scope

This is a technical self-assessment of release 1.0.0, not an AgID certification or an
independent audit. The measures follow the secure development lifecycle, secure coding,
secure configuration, and threat-modeling principles referenced by the AgID Guidelines for
Secure Software Development.

## Threat model

| Threat | Implemented measure | Residual risk |
| --- | --- | --- |
| MQTT credential theft | password only from a protected file; never logged | compromised host administrator |
| Broker MITM | TLS, CA, and hostname verification; no insecure switch | compromised CA or host |
| Unauthorized publishing | dedicated broker user and documented least-privilege ACL | incorrect broker ACL |
| Abusive CLI input | typed inputs, numeric limits, operator-controlled topic | trusted local operator |
| Malicious BLE payload | bounded depth/count, safe serialization, no `eval` | third-party decoder defects |
| Excess privileges | non-root service and hardened systemd unit | host BlueZ/D-Bus policy |
| Vulnerable dependencies | constrained versions, weekly `pip-audit`, explicit updates | newly undisclosed CVE |
| Supply chain | read-only CI and SHA-256 package checksums | unsigned checksums |
| Metrics disclosure | opt-in services, loopback default, read-only SNMP | locally visible sensor data |
| SNMP community capture | protected file and constant-time comparison | SNMPv2c traffic is clear text |
| External binding | explicit `0.0.0.0`/`::`, warning log, configurable ports | firewall controls exposure |
| Invalid alias | normalized MAC, length/printability checks, duplicates rejected | operator-chosen content |
| Tuya credential theft | IDs/secrets in protected files; HTTPS client | cloud/account/host compromise |
| Malicious plugin | explicit entry points, optional install, exception isolation | plugin has process privileges |
| Cloud outage | failure isolated while BLE collection continues | missing/stale Tuya values |
| Metric cardinality | at most 256 scalar values per sensor and operator guidance | variable string labels |

## Secure lifecycle controls

- public repository, EUPL-1.2 license, changelog, security policy, and traceable version/build;
- automated tests, Ruff validation, Bandit static analysis, and `pip-audit` SCA;
- least privilege and separation of code, configuration, and secrets;
- errors recorded without credentials, graceful shutdown, and controlled restart;
- encrypted production protocols recommended and certificate verification cannot be disabled;
- release review for vulnerabilities, licenses, and real-hardware behavior;
- separate dependency profiles (`sensors`, `cloud`, `all`) to reduce attack surface;
- manufacturer/model/protocol always present and bounded decoder output.

## Production checklist

1. Run tests, Bandit, and `pip-audit` against the resolved production dependencies.
2. Configure TLS 1.2/1.3 and a minimal broker ACL for the dedicated topic prefix.
3. Apply Raspberry Pi OS security updates and disable unnecessary services.
4. Protect SSH with keys, restrict the network, and centralize/rotate logs.
5. Test network loss, broker outage, disabled Bluetooth, SIGTERM, and host restart.
6. Record owner, maintainer, inventory, accepted risks, and the update plan.
7. Restrict TCP 9105 and UDP 1161; use HTTPS/VPN and an SNMPv3 proxy on untrusted networks.
8. Install plugins only from verified sources; review licenses/hashes and pin tested versions.
9. For Tuya, grant minimum cloud privileges, rotate keys, and review legal basis, privacy notice,
   retention, and data location.

## References

- AgID, Guidelines for Secure Software Development:
  https://www.agid.gov.it/it/sicurezza/cert-pa/linee-guida-sviluppo-del-software-sicuro
- CERT-AgID documents: https://cert-agid.gov.it/documenti-agid/
- AgID, software acquisition and reuse guidelines:
  https://docs.italia.it/italia/developers-italia/gl-acquisizione-e-riuso-software-per-pa-docs/
- European Commission, EUPL:
  https://commission.europa.eu/content/european-union-public-licence_en
