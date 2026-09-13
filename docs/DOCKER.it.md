# Deployment Docker

L'immagine canonica è `desalvo/ble-sensors-mqtt:<VERSION>`. Il progetto costruisce un singolo manifest multi-platform per `linux/amd64` e `linux/arm64`.

MQTT è una connessione client in uscita verso il broker configurato; il container non contiene un broker MQTT. Prometheus ascolta su TCP/9105 e SNMP su UDP/1161 quando abilitati.

## Build e push su Docker Hub

Autenticarsi una volta:

```bash
docker login
```

Poi eseguire:

```bash
scripts/build-docker.sh
```

Lo script:

- legge la versione da `VERSION` e la verifica rispetto a `pyproject.toml`;
- crea o riusa un builder Docker Buildx;
- abilita gli helper binfmt amd64/arm64 salvo `--skip-binfmt`;
- costruisce `linux/amd64,linux/arm64`;
- applica il tag `desalvo/ble-sensors-mqtt:<VERSION>`;
- esegue di default il push dell'immagine multiarch su Docker Hub.

Opzioni utili:

```bash
# Pubblica anche desalvo/ble-sensors-mqtt:latest
scripts/build-docker.sh --latest

# Costruisce senza push; salva un archivio OCI multiarch in release/docker/
scripts/build-docker.sh --no-push

# Registry/immagine o piattaforme alternative
scripts/build-docker.sh --image registry.example/ble-sensors-mqtt \
  --platforms linux/amd64,linux/arm64
```

Il file `.dockerignore` nella root esclude dal contesto Git, virtualenv, output build/release e directory locali contenenti secret.

## Preparazione Bluetooth dell'host

Il container **non esegue BlueZ al proprio interno**: usa il demone BlueZ dell'host attraverso `/run/dbus/system_bus_socket`. Prima di avviare Docker:

```bash
sudo scripts/check-bluetooth-host.sh --strict
```

Se necessario:

```bash
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
bluetoothctl power on
bluetoothctl list
```

Compose monta `/run/dbus:/run/dbus:ro` e imposta `DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket`. Non sono richiesti `--privileged`, `--device /dev/...`, `CAP_NET_ADMIN` o `CAP_NET_RAW` quando viene usato BlueZ host via D-Bus.

Per provare lo scan BLE con la stessa immagine prima di avviare il demone:

```bash
docker run --rm \
  --entrypoint ble-sensors-mqtt \
  -e DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket \
  -v /run/dbus:/run/dbus:ro \
  desalvo/ble-sensors-mqtt:1.0.0 \
  --scan --scan-duration 10
```

Se lo scan host con `bluetoothctl` funziona ma quello nel container fallisce, verificare permessi/policy del system D-Bus e di BlueZ. Preferire la correzione della policy host alla modalità `privileged`.

## Esecuzione continua con Docker Compose

Preparare i file runtime:

```bash
cd docker
cp .env.example .env
cp arguments.example arguments
mkdir -p secrets
printf '%s\n' 'MQTT_PASSWORD' > secrets/mqtt-password
sudo chown 10001:10001 secrets/mqtt-password
chmod 400 secrets/mqtt-password
```

Modificare `.env`, quindi avviare:

```bash
docker compose up -d
docker compose ps
docker compose logs -f
```

Compose usa `restart: unless-stopped`: il demone viene riavviato dopo errori e ai reboot dell'host quando Docker riparte. Lo stato runtime viene persistito nel volume `ble-sensors-state`.

Per BLE il compose monta in sola lettura `/run/dbus` dell'host e usa esplicitamente il system D-Bus, permettendo a Bleak di comunicare con BlueZ dell'host. I deployment solo cloud possono rimuovere il mount. Se la policy BlueZ/D-Bus dell'host rifiuta il container non-root, correggere la policy host invece di rendere privilegiato il container, salvo assenza di alternative più sicure.

Prometheus è abilitato di default nel container ed esposto su TCP/9105. SNMP è disabilitato di default; per abilitarlo impostare `SNMP_ENABLED=true`, creare `secrets/snmp-community`, assegnarlo a UID/GID 10001 con modo `0400` e ricreare il container.

Gli argomenti applicativi aggiuntivi/ripetibili vanno in `docker/arguments`, uno per riga. Un valore con spazi resta un singolo argomento perché l'entrypoint legge la riga completa. Esempio:

```text
--device-name
AA:BB:CC:DD:EE:01=Soggiorno
--device-name
AA:BB:CC:DD:EE:02=Camera
```

## Esecuzione diretta con `docker run`

Esempio minimo persistente:

```bash
docker run -d --name ble-sensors-mqtt --restart unless-stopped \
  -e MQTT_HOST=mqtt.example.net \
  -e MQTT_TLS=true \
  -e PROMETHEUS_ENABLED=true \
  -p 9105:9105/tcp \
  -v /run/dbus:/run/dbus:ro \
  -v ble-sensors-state:/var/lib/ble-sensors-mqtt \
  desalvo/ble-sensors-mqtt:1.0.0
```

Se si abilita SNMP, pubblicare anche `-p 1161:1161/udp` e montare il file community protetto.

## Esposizione esterna e sicurezza

Pubblicare `9105:9105/tcp` o `1161:1161/udp` rende i listener raggiungibili secondo firewall host e regole di rete Docker. Prometheus non offre autenticazione/TLS applicativa e SNMPv2c è in chiaro. Non esporli direttamente a Internet non fidata: usare firewall, rete di management, VPN, reverse proxy/TLS dove appropriato oppure proxy SNMPv3.

Quando possibile, fornire le credenziali MQTT tramite file montati protetti anziché variabili d'ambiente letterali. L'immagine esegue l'applicazione con UID/GID 10001 e non richiede root.

## Pubblicazione CI su Docker Hub

Il workflow GitHub Actions contiene il job opzionale `docker-image`. Configurare nel repository:

- variabile `DOCKERHUB_PUSH_ENABLED=true`;
- variabile `DOCKERHUB_USERNAME=desalvo`;
- secret `DOCKERHUB_TOKEN` contenente un access token Docker Hub con permesso di push.

Dopo il successo dei normali job Python/security/build:

- un push su `main` pubblica `desalvo/ble-sensors-mqtt:latest` per amd64 e arm64;
- un tag release `vX.Y.Z` pubblica `desalvo/ble-sensors-mqtt:X.Y.Z`, dopo aver verificato la versione del tag rispetto a `VERSION`.

Se `DOCKERHUB_PUSH_ENABLED` non esiste o non vale `true`, il job di pubblicazione Docker viene saltato senza compromettere la normale CI/release.
