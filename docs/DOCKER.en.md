# Docker deployment

The canonical image is `desalvo/ble-sensors-mqtt:<VERSION>`. The project builds one multi-platform manifest for `linux/amd64` and `linux/arm64`.

MQTT is an outbound client connection to the configured broker; the container does not run an MQTT broker. Prometheus listens on TCP/9105 and SNMP on UDP/1161 when enabled.

## Build and push to Docker Hub

Authenticate once:

```bash
docker login
```

Then run:

```bash
scripts/build-docker.sh
```

The script:

- reads the project version from `VERSION` and verifies it against `pyproject.toml`;
- creates/reuses a Docker Buildx builder;
- enables amd64/arm64 binfmt helpers unless `--skip-binfmt` is used;
- builds `linux/amd64,linux/arm64`;
- tags `desalvo/ble-sensors-mqtt:<VERSION>`;
- pushes the multiarch image to Docker Hub by default.

Useful options:

```bash
# Also publish desalvo/ble-sensors-mqtt:latest
scripts/build-docker.sh --latest

# Build without pushing; writes a multiarch OCI archive under release/docker/
scripts/build-docker.sh --no-push

# Alternate registry/image or platform set
scripts/build-docker.sh --image registry.example/ble-sensors-mqtt \
  --platforms linux/amd64,linux/arm64
```

The root `.dockerignore` excludes Git metadata, virtual environments, build/release output and local secret directories from the build context.

## Preparing host Bluetooth

The container **does not run BlueZ internally**. It uses the host BlueZ daemon through `/run/dbus/system_bus_socket`. Before starting Docker, run:

```bash
sudo scripts/check-bluetooth-host.sh --strict
```

If required:

```bash
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
bluetoothctl power on
bluetoothctl list
```

Compose mounts `/run/dbus:/run/dbus:ro` and sets `DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket`. `--privileged`, direct HCI device mapping, `CAP_NET_ADMIN`, and `CAP_NET_RAW` are not required when using host BlueZ through D-Bus.

Test BLE scanning with the same image before starting the daemon:

```bash
docker run --rm \
  --entrypoint ble-sensors-mqtt \
  -e DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket \
  -v /run/dbus:/run/dbus:ro \
  desalvo/ble-sensors-mqtt:1.0.0 \
  --scan --scan-duration 10
```

If `bluetoothctl` scanning works on the host but container scanning fails, inspect system D-Bus/BlueZ policy and permissions. Prefer fixing host policy over running the container as privileged.

## Run continuously with Docker Compose

Prepare the runtime files:

```bash
cd docker
cp .env.example .env
cp arguments.example arguments
mkdir -p secrets
printf '%s\n' 'MQTT_PASSWORD' > secrets/mqtt-password
sudo chown 10001:10001 secrets/mqtt-password
chmod 400 secrets/mqtt-password
```

Edit `.env`, then start:

```bash
docker compose up -d
docker compose ps
docker compose logs -f
```

Compose uses `restart: unless-stopped`, so the daemon is restarted after failures and across host reboots when Docker itself starts. Runtime state is persisted in the `ble-sensors-state` volume.

For BLE, Compose mounts host `/run/dbus` read-only and explicitly uses the system D-Bus so Bleak can communicate with host BlueZ. Cloud-only deployments can remove this mount. If host BlueZ/D-Bus policy rejects the unprivileged container, fix the host policy instead of granting a privileged container unless there is no safer alternative.

Prometheus is enabled by default in the container and published as TCP/9105. SNMP is disabled by default; to enable it, set `SNMP_ENABLED=true`, create `secrets/snmp-community`, set it to UID/GID 10001 and mode `0400`, then recreate the container.

Additional/repeatable application options are stored in `docker/arguments`, one CLI argument per line. A value containing spaces remains one argument because the entrypoint reads a whole line at a time. Example:

```text
--device-name
AA:BB:CC:DD:EE:01=Living room
--device-name
AA:BB:CC:DD:EE:02=Bedroom
```

## Direct `docker run`

A minimal long-running invocation is:

```bash
docker run -d --name ble-sensors-mqtt --restart unless-stopped \
  -e MQTT_HOST=mqtt.example.net \
  -e MQTT_TLS=true \
  -e PROMETHEUS_ENABLED=true \
  -e DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket \
  -p 9105:9105/tcp \
  -v /run/dbus:/run/dbus:ro \
  -v ble-sensors-state:/var/lib/ble-sensors-mqtt \
  desalvo/ble-sensors-mqtt:1.0.0
```

If SNMP is enabled, also publish `-p 1161:1161/udp` and mount the protected community file.

## External exposure and security

Publishing `9105:9105/tcp` or `1161:1161/udp` makes the listener reachable according to the host firewall and Docker networking rules. Prometheus has no application authentication/TLS and SNMPv2c is plaintext. Do not expose either directly to an untrusted Internet; use firewall rules, a trusted management network, VPN, reverse proxy/TLS where appropriate, or an SNMPv3 proxy.

MQTT credentials should be supplied through protected mounted files rather than literal environment variables when practical. The image runs as UID/GID 10001 and does not require root for the application.

## CI publication to Docker Hub

The GitHub Actions workflow contains an optional `docker-image` job. Configure these repository settings:

- variable `DOCKERHUB_PUSH_ENABLED=true`;
- variable `DOCKERHUB_USERNAME=desalvo`;
- secret `DOCKERHUB_TOKEN` containing a Docker Hub access token with push permission.

After the normal Python/security/build jobs pass:

- a push to `main` publishes `desalvo/ble-sensors-mqtt:latest` for amd64 and arm64;
- a pushed release tag `vX.Y.Z` publishes `desalvo/ble-sensors-mqtt:X.Y.Z`, after checking the tag version against `VERSION`.

If `DOCKERHUB_PUSH_ENABLED` is absent or not `true`, the Docker publication job is skipped without affecting ordinary CI/release validation.

## MQTT outage cache

The container stores the SQLite MQTT spool in `/var/lib/ble-sensors-mqtt/mqtt-cache.sqlite3`, therefore the existing state volume also persists queued messages. Configure `MQTT_CACHE_ENABLED`, `MQTT_CACHE_PATH`, `MQTT_CACHE_MAX_SIZE`, and `REUSE_STALE_DATA` in `.env`.

## Multiple Bluetooth controllers

On a Linux Docker host with more than one BlueZ controller (for example internal Bluetooth plus a USB dongle), set `BLUETOOTH_ADAPTER=hci1` in `docker/.env`. The entrypoint forwards it as `--bluetooth-adapter hci1`. Leave it empty to use the BlueZ/Bleak default controller.

## Authenticated frontend

The image includes the optional web dependencies. Set `FRONTEND_ENABLED=true` to start the frontend, which listens on `FRONTEND_HOST`/`FRONTEND_PORT` (defaults `0.0.0.0:8080` in the container) and stores users, MFA, session state and browser runtime overrides under `/var/lib/ble-sensors-mqtt/frontend`. The Compose example publishes TCP/8080. For remote use, terminate TLS either with `FRONTEND_TLS_CERT`/`FRONTEND_TLS_KEY` mounted as secrets or at a reverse proxy. See `FRONTEND.en.md`.
