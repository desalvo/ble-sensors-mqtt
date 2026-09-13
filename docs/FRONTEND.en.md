# Optional authenticated web frontend

The web frontend is optional. Install the `web` profile (`pip install '.[web]'`) or `all`, then enable it with `--frontend` or `[frontend] enabled = true` in `config.toml`.

By default it listens only on `127.0.0.1:8080`. A non-loopback bind requires `allow_external = true` / `--allow-external-frontend`. Use the built-in TLS certificate/key options or place the frontend behind an authenticated TLS reverse proxy for remote access.

## First login and roles

The authentication database is created automatically. The initial account is:

- username: `admin`
- password: `password`
- role: `admin`

The initial password **must be changed at the first login**. Roles are intentionally small:

- `admin`: complete access to sensors, configuration, users, identity providers, MFA and backup/restore;
- `reader`: read-only dashboard and sensor status.

The local authentication database uses PBKDF2-SHA256 password hashes and does not store clear-text passwords.

## Dashboard and runtime configuration

The dashboard shows every normalized sensor currently exported by the gateway, including name, address, manufacturer/model, protocol, RSSI, observed time, stale/live state and all normalized data values. The responsive layout is designed for desktop, tablet and phone screens.

Administrators can edit persistent application settings from the browser. Poll interval, scan duration, plugin timeout and stale fallback are applied to the active process immediately. Connection/listener settings such as MQTT broker, Prometheus/SNMP/frontend endpoints, cache location, cloud providers and authentication providers are saved persistently and marked as requiring a service restart.

Browser changes are written to a writable `runtime-config.toml` under the frontend state directory instead of modifying the protected base configuration. On the next start, precedence is:

`CLI > runtime-config.toml > base config.toml > built-in defaults`.

This allows persistent browser changes even when `/etc` or a Kubernetes ConfigMap is read-only.

## LDAP

Enable `[frontend.ldap]` to authenticate against LDAP. Two modes are supported:

1. `user_dn_template`, e.g. `uid={username},ou=people,dc=example,dc=org`;
2. service/search bind with `bind_dn`, protected `bind_password_file`, `base_dn` and `user_filter`.

LDAP passwords are checked directly against LDAP and are never stored locally. On the first successful login the frontend creates a local shadow profile containing only application role, active state and optional MFA information. The default role is configurable and should normally remain `reader`.

Use LDAPS or StartTLS in production and protect the bind-password file.

## OpenID Connect SSO

Generic OIDC is supported through `[frontend.oidc]`: provider metadata URL, client ID, protected client-secret file, scopes, username claim and default role. This covers standards-compliant providers and services such as Google Workspace, Keycloak, Entra ID and other OIDC IdPs when correctly configured.

OIDC users receive a local shadow profile for the application role. MFA for SSO should normally be enforced by the Identity Provider.

## Local/LDAP MFA

Local and LDAP users can use RFC-compatible TOTP MFA. An administrator can create/enable a TOTP seed from **Users -> MFA**. The page exposes the Base32 seed and `otpauth://` URI so it can be enrolled in common authenticator apps.

The MFA seed is deliberately portable: an administrator may enroll the same seed on several ble-sensors-mqtt instances, or replicate it through an encrypted full backup. This allows a single TOTP token to be shared across equivalent application instances in the same infrastructure. Treat the exported seed as a credential.

## Encrypted import/export

**Backup / Restore** creates a `.bsmqbackup` file encrypted with AES-GCM using a key derived from the administrator-supplied passphrase with scrypt. The passphrase is mandatory.

The backup includes, when available:

- effective application configuration (base plus browser runtime overrides);
- local/LDAP/OIDC user shadow profiles, password hashes, roles and MFA seeds;
- MQTT disk-cache snapshot;
- runtime retained-topic state;
- cloud/BLE-key configuration file referenced by the running instance.

The MQTT SQLite spool is exported with SQLite's online backup mechanism and restored through the live cache object, so the queue does not need to be copied while its database file is open.

Import replaces/restores the corresponding settings and user profiles. Network/authentication changes require a service restart after import.

## State locations

Default frontend state is stored under:

- managed Linux/Docker/Kubernetes: `/var/lib/ble-sensors-mqtt/frontend` when the service state directory is available;
- ordinary Linux user: `$XDG_STATE_HOME/ble-sensors-mqtt/frontend` or `~/.local/state/ble-sensors-mqtt/frontend`;
- Windows: `%PROGRAMDATA%\ble-sensors-mqtt\frontend`;
- macOS: `~/Library/Application Support/ble-sensors-mqtt/frontend`.

It contains the authentication SQLite database, session secret, runtime configuration override and temporary/export data. Protect this directory as sensitive application state.

## Sensor history

When the web frontend is enabled, ble-sensors-mqtt stores each exported sensor snapshot in a persistent SQLite history database. The default retention is 30 days. Configure it from the web Configuration page under **History**, or with `--history-retention-days DAYS`. Use `--history-path PATH` to override the SQLite location.

The History page supports one or more sensors, date-range filtering, simultaneous chart series, and a tabular view. By default the table suppresses consecutive rows when both the complete sensor values and the `stale` flag are unchanged; enable **Show consecutive duplicates** to see every stored sample. Administrators can delete the full history of selected sensors or only the selected date interval. Readers have read-only access.

The history database is included in encrypted full backup/export and restored through the same web Backup / Restore workflow.
