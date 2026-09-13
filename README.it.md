# ble-sensors-mqtt

[English](README.md) · **Italiano**

<img src="assets/ble-sensors-mqtt-logo.png" alt="Logo applicativo ble-sensors-mqtt" width="180">

Gateway multi-sensore plugin-based per Raspberry Pi Zero W o superiore. Acquisisce sensori
Bluetooth LE e, opzionalmente, Tuya Cloud; normalizza i dati e li pubblica su MQTT,
Prometheus e SNMP. Repository previsto: `desalvo/ble-sensors-mqtt`.

**Versione:** 1.0.0 · **Build:** file `BUILD` · **Autore:** Alessandro De Salvo
<braket71@gmail.com> · **Licenza:** EUPL-1.2

## Funzioni

- scanner BLE unico con polling continuo (30 s per default) o singolo ciclo;
- plugin isolati e plugin esterni caricabili tramite entry point Python;
- SwitchBot nel profilo base; pacchetti opzionali per gli altri produttori;
- provider Tuya Cloud opzionale con credenziali lette esclusivamente da file protetti;
- alias per MAC e per identificatori cloud/multi-canale;
- MQTT con TLS verificato, QoS, retain e Last Will;
- Prometheus e SNMPv2c read-only opzionali, con IP e porte configurabili;
- `manufacturer`, `model` e `protocol` in ogni output, oltre a tutti i valori scalari
  disponibili nel decoder;
- Home Assistant MQTT Discovery opzionale con configurazione retained e raggruppamento per device;
- semantica di prima classe per presenza/movimento/occupazione in Home Assistant, Prometheus e SNMP;
- riuso opzionale dell’ultima lettura con flag `stale: true` quando un sensore manca;
- cache MQTT persistente SQLite e limitata (1 GiB per default) durante indisponibilità del broker;
- installer systemd irrobustito interattivo/non interattivo per funzionamento continuo;
- asset Docker/Compose e Kubernetes multiarch per amd64/arm64;
- pubblicazione CI delle immagini Docker Hub versionate sui tag e `latest` su `main`;
- test, lint, Bandit, audit dipendenze e gate automatici di release;
- logo applicativo PNG con sfondo trasparente, incluso nel manuale PDF.

## Sensori e modalità

| Plugin | Marche/protocolli | Lettura | Installazione |
| --- | --- | --- | --- |
| `switchbot` | SwitchBot Meter e altri modelli riconosciuti | advertisement BLE locale | base |
| `xiaomi` | Xiaomi/Mijia, HHCC e MiBeacon | BLE; bind key per frame cifrati | `.[sensors]` |
| `govee` | Govee | BLE locale | `.[sensors]` |
| `inkbird` | Inkbird | BLE; alcuni modelli richiedono connessione | `.[sensors]` |
| `thermopro` | ThermoPro | BLE locale | `.[sensors]` |
| `qingping` | Qingping/ClearGrass | BLE locale | `.[sensors]` |
| `bthome` | BTHome, Shelly BLU, firmware ATC/PVVX in modalità BTHome | BLE locale | `.[sensors]` |
| `ruuvi` | RuuviTag | BLE locale | `.[sensors]` |
| `sensorpush` | SensorPush | BLE locale per modelli compatibili | `.[sensors]` |
| `airthings` | Airthings | connessione BLE GATT attiva | `.[sensors]` |
| `mopeka` | Mopeka | BLE locale | `.[sensors]` |
| `tuya-cloud` | sensori associati a Smart Life/Tuya | API cloud | `.[cloud]`/`.[all]` |

Il supporto effettivo dipende da modello, firmware, cifratura e dati trasmessi. Un dispositivo
Tuya che usa BTHome può funzionare localmente; i formati Tuya proprietari richiedono chiavi
locali specifiche o il cloud. `--list-plugins` mostra cosa è realmente installato. L'app del
produttore non è necessaria per sensori BLE in chiaro e può coesistere con il gateway; può
servire per associare un dispositivo cloud o ottenere chiavi.

## Host supportati

Linux x86_64/arm64 è supportato sulle famiglie Debian e Red Hat, usando Bluetooth interno oppure un dongle Bluetooth USB gestito da BlueZ. Sono inoltre supportati Windows 11+ e macOS Tahoe 26+ tramite i backend nativi Bleak; le release taggate generano bundle nativi in CI. Vedere [`docs/HOSTS.it.md`](docs/HOSTS.it.md).

Su Linux con più controller usare `--bluetooth-adapter hci1`; su Windows/macOS il controller viene scelto dal sistema operativo.

## Installazione in venv

Requisiti: Raspberry Pi OS Bookworm, Python 3.11+, BlueZ e broker MQTT raggiungibile.

```bash
unzip ble-sensors-mqtt-v1.0.0-<BUILD>.zip
cd ble-sensors-mqtt
sudo apt update
sudo apt install -y bluetooth bluez python3 python3-venv
sudo systemctl enable --now bluetooth
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
```

Scegliere un profilo:

```bash
.venv/bin/pip install .             # solo SwitchBot, più leggero
.venv/bin/pip install '.[sensors]'  # tutti i decoder BLE
.venv/bin/pip install '.[cloud]'    # SwitchBot + Tuya Cloud
.venv/bin/pip install '.[web]'      # frontend browser autenticato
.venv/bin/pip install '.[all]'      # tutti i decoder BLE/cloud + frontend web
```

```bash
.venv/bin/ble-sensors-mqtt --version
.venv/bin/ble-sensors-mqtt --list-plugins
.venv/bin/ble-sensors-mqtt --help
```

Sul Pi Zero installare solo i plugin necessari e usare un intervallo di almeno 30 secondi.

## Scansione e nomi

La scansione non richiede MQTT:

```bash
.venv/bin/ble-sensors-mqtt --scan --scan-duration 15
.venv/bin/ble-sensors-mqtt --scan --plugin switchbot --plugin bthome
```

L'output JSON contiene i dispositivi riconosciuti. Ogni sensore ha sempre `address`, `name`,
`manufacturer`, `model`, `protocol`, `observed_at` e `data`; un'identità non determinabile è
`Unknown`.

```bash
# Alias BLE
.venv/bin/ble-sensors-mqtt --scan \
  --device-name 'AA:BB:CC:DD:EE:FF=Sala Server'

# Alias cloud o multi-canale
.venv/bin/ble-sensors-mqtt --scan --cloud-config ./cloud.toml \
  --sensor-name 'TUYA:bf123456=Cantina'
```

L'alias sostituisce `name` in tutti gli output; `bluetooth_name` conserva il nome radio.
`--device ID` filtra i sensori pubblicati ed è ripetibile; accetta sia MAC BLE sia identificatori cloud/plugin come `TUYA:bf123456`.

Per BTHome cifrato o Xiaomi/MiBeacon cifrato, esportare la bind key con gli strumenti previsti
dal produttore/firmware, salvarla come sola stringa esadecimale in un file `0600`/`0640` e
aggiungerla allo stesso TOML passato con `--cloud-config` (il nome dell'opzione è mantenuto per
compatibilità, ma il file contiene anche impostazioni BLE):

```toml
[ble_keys."AA:BB:CC:DD:EE:FF"]
plugin = "bthome" # oppure "xiaomi"
bindkey_file = "/etc/ble-sensors-mqtt/sensor-aa-bb-bindkey"
```

BTHome richiede 16 byte; Xiaomi accetta chiavi da 12 o 16 byte. La chiave non va mai inserita
nella CLI o nei log.

## MQTT

### Home Assistant MQTT Discovery

Abilitare l'autodiscovery di Home Assistant con `--home-assistant-discovery`. Il gateway pubblica topic di configurazione retained sotto `homeassistant/` per default, mantenendo gli stati dei sensori sui normali topic `ble-sensors/.../state`. Le misure scalari diventano entità Home Assistant `sensor`; i valori riconosciuti di presenza, motion, occupancy e moving diventano vere entità `binary_sensor` con la device class corrispondente. Le misure note ricevono device/state class e unità, mentre RSSI, protocollo e stale sono diagnostici. Tutte le entità dello stesso sensore fisico/cloud vengono raggruppate in un singolo device Home Assistant con manufacturer/model. L'availability usa il topic retained di stato del bridge.

La semantica presenza riconosce i campi comuni dei decoder/vendor, fra cui BTHome `presence`, `motion`, `occupancy` e `moving`, oltre ad alias come SwitchBot `Detected`, `moveDetected` e `detectionState`. Il campo originale del plugin resta invariato in MQTT e negli exporter generici.

```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 127.0.0.1 --home-assistant-discovery
```

Usare `--home-assistant-discovery-prefix PREFIX` se Home Assistant utilizza un prefisso discovery diverso dal default. I topic di configurazione discovery sono retained e quelli obsoleti vengono rimossi quando sensori/entità scompaiono o quando il discovery viene disabilitato, purché venga mantenuto il file di stato runtime.

### Letture stale e cache per indisponibilità MQTT

Con `--reuse-stale-data`, se un sensore non viene rilevato in un ciclo oppure restituisce `data` vuoto, viene riusata l’ultima lettura disponibile in memoria. Lo snapshot riusato conserva l’`observed_at` originale e aggiunge `"stale": true`; le letture fresche hanno `"stale": false`. Prometheus espone `ble_sensors_stale` e usa `ble_sensors_up=0` per i dati riusati.

La cache MQTT su disco è attiva per default. Se il broker non è disponibile all’avvio o cade successivamente, il polling continua e i messaggi MQTT vengono accodati transazionalmente in SQLite. Il limite logico predefinito è 1 GiB; quando viene raggiunto, i record più vecchi sono eliminati per lasciare spazio ai dati nuovi. Alla riconnessione i messaggi vengono inviati FIFO e cancellati soltanto dopo l’ACK di pubblicazione. Personalizzare con `--mqtt-cache-path`, `--mqtt-cache-max-size` o disabilitare con `--no-mqtt-cache`. Se è impostato `--state-file`, il path predefinito della cache è `mqtt-cache.sqlite3` nella stessa directory.


```bash
# Test, un solo ciclo
.venv/bin/ble-sensors-mqtt --mqtt-host 127.0.0.1 --once

# Servizio continuo, polling ogni 60 secondi
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --poll-interval 60 --allow-insecure-mqtt

# Produzione con TLS
.venv/bin/ble-sensors-mqtt --mqtt-host mqtt.example.it --mqtt-port 8883 \
  --mqtt-username sensor-publisher \
  --mqtt-password-file /etc/ble-sensors-mqtt/mqtt-password \
  --mqtt-tls --mqtt-ca-file /etc/ssl/certs/ca-certificates.crt
```

Per `AA:BB:CC:DD:EE:FF` il topic è `ble-sensors/aabbccddeeff/state`; lo stato processo è
`ble-sensors/bridge/status`. Esempio payload:

```json
{
  "address": "AA:BB:CC:DD:EE:FF",
  "name": "Sala Server",
  "bluetooth_name": "Meter Plus",
  "manufacturer": "SwitchBot",
  "model": "Meter Plus",
  "protocol": "SwitchBot BLE",
  "rssi": -58,
  "observed_at": "2026-09-11T20:00:00+00:00",
  "data": {"temperature": 23.4, "humidity": 51, "battery": 92}
}
```

`data` contiene tutti i dati resi dal decoder, inclusi booleani, versioni, unità ed eventi.
Il file password deve avere permessi `0640` o più restrittivi.

## Tuya Cloud

Mostrare le istruzioni integrate:

```bash
.venv/bin/ble-sensors-mqtt --cloud-help
```

Nel portale Tuya IoT creare un progetto Smart Home, collegare l'account Smart Life/Tuya,
autorizzare le API dispositivi e annotare regione, Access ID, Access Secret e un Device ID.

```bash
sudo install -d -m 0750 -o root -g ble-sensors-mqtt /etc/ble-sensors-mqtt
sudo sh -c 'umask 077; printf %s "ACCESS_ID" > /etc/ble-sensors-mqtt/tuya-api-key'
sudo sh -c 'umask 077; printf %s "ACCESS_SECRET" > /etc/ble-sensors-mqtt/tuya-api-secret'
sudo chown root:ble-sensors-mqtt /etc/ble-sensors-mqtt/tuya-api-*
sudo chmod 0640 /etc/ble-sensors-mqtt/tuya-api-*
sudo install -m 0640 -o root -g ble-sensors-mqtt config/cloud.example.toml \
  /etc/ble-sensors-mqtt/cloud.toml
sudo editor /etc/ble-sensors-mqtt/cloud.toml
```

```toml
[cloud.tuya]
enabled = true
region = "eu"
api_key_file = "/etc/ble-sensors-mqtt/tuya-api-key"
api_secret_file = "/etc/ble-sensors-mqtt/tuya-api-secret"
api_device_id = "DEVICE_ID_DI_RIFERIMENTO"
device_ids = ["DEVICE_ID_DA_ESPORTARE"] # opzionale; vuoto = tutti
```

```bash
.venv/bin/ble-sensors-mqtt --scan --cloud-config /etc/ble-sensors-mqtt/cloud.toml
```

Un errore cloud è isolato: il ciclo mantiene i dati BLE. Le chiamate escono su HTTPS;
verificare informativa privacy, localizzazione dati e condizioni del servizio.

## Prometheus

```bash
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --prometheus
curl http://127.0.0.1:9105/metrics
```

L'exporter espone queste famiglie di metriche:

| Metrica | Tipo | Label principali / significato |
| --- | --- | --- |
| `ble_sensors_up` | gauge | identità sensore; `1` fresco, `0` stale/riusato |
| `ble_sensors_stale` | gauge | identità sensore; indicatore di stale |
| `ble_sensors_temperature_celsius` | gauge | `temperature` trovato ricorsivamente |
| `ble_sensors_humidity_percent` | gauge | `humidity` trovato ricorsivamente |
| `ble_sensors_battery_percent` | gauge | `battery` o `battery_percent` |
| `ble_sensors_rssi_dbm` | gauge | RSSI top-level in dBm |
| `ble_sensors_sensor_value` | gauge | identità + `key,unit`; tutti gli scalari numerici/booleani di `data` |
| `ble_sensors_sensor_info` | gauge | identità + `key,unit,value`; tutte le stringhe di `data`, campione `1` |
| `ble_sensors_devices` | gauge | numero snapshot attualmente esportati |
| `ble_sensors_cycles_total` | counter | cicli di polling tentati |
| `ble_sensors_cycles_failed_total` | counter | cicli di polling falliti |

Le label di identità sono `address`, `name`, `manufacturer`, `model` e `protocol`. Le chiavi generiche sono
path puntati appiattiti da `data`; i booleani diventano `0`/`1`, `null` non viene esportato e sono esposti al
massimo 256 scalari per sensore. La mappa riservata `data.units` fornisce la label `unit` e non viene esportata
come dato. Vedere `docs/USAGE.it.md` per contratto completo ed esempi.

Default `127.0.0.1:9105`; usare `::` per IPv6. `/healthz` espone la liveness e `/readyz` la readiness.
Il bind non-loopback richiede `--allow-external-prometheus`; l'endpoint non ha TLS o autenticazione integrati.

## SNMP

```bash
sudo sh -c 'umask 077; printf %s "COMMUNITY_CASUALE" > /etc/ble-sensors-mqtt/snmp-community'
sudo chown root:ble-sensors-mqtt /etc/ble-sensors-mqtt/snmp-community
sudo chmod 0640 /etc/ble-sensors-mqtt/snmp-community
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --snmp \
  --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
snmpwalk -v2c -c COMMUNITY_CASUALE 127.0.0.1:1161 1.3.6.1.4.1.32473.1.1
```

Con il base OID predefinito, `.1.0` identifica l'applicazione, `.2.0` riporta il numero dispositivi esportati,
`.10.1` è la tabella dispositivi comuni (identità, RSSI, temperatura, umidità, batteria, timestamp e flag
stale) e `.20.1` è la tabella scalare generica (`key`, valore testuale, tipo, unità, indice dispositivo e
indice scalare). La tabella generica contiene fino a 256 scalari `data` per sensore. Gli indici dispositivo
sono transitori. Il contratto esatto OID/tipi è in `docs/BLE-SENSORS-MQTT-MIB.txt` e `docs/USAGE.it.md`.

Il listener predefinito è `127.0.0.1:1161/udp`; il bind non-loopback richiede `--allow-external-snmp`.
SNMPv2c è in chiaro. Il PEN 32473 è solo documentativo: in produzione usare un `--snmp-base-oid` assegnato.

## systemd

Installazione facile completa da clone GitHub, con prerequisiti host, verifica Bluetooth, venv e servizio:

```bash
git clone https://github.com/desalvo/ble-sensors-mqtt.git
cd ble-sensors-mqtt
sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net --prometheus
```

Sono inoltre supportate installazione systemd interattiva e non presidiata; i valori CLI restano i default delle domande.

```bash
sudo scripts/install-systemd.sh --mqtt-host mqtt.example.net
sudo scripts/install-systemd.sh --non-interactive --mqtt-host mqtt.example.net --mqtt-tls --prometheus
```

Vedere `docs/SYSTEMD.it.md`.

## Docker e Kubernetes

Sono inclusi Docker/Compose multiarch `linux/amd64,linux/arm64` e manifest Kubernetes. Prima di usare BLE in container/pod eseguire `sudo scripts/check-bluetooth-host.sh --strict`; Docker e Kubernetes usano BlueZ host via `/run/dbus`, senza richiedere `privileged`.

```bash
docker login
scripts/build-docker.sh
cd docker && cp .env.example .env && cp arguments.example arguments && docker compose up -d
kubectl apply -k kubernetes/
```

Vedere `docs/DOCKER.it.md` e `docs/KUBERNETES.it.md`. MQTT è uscente; Prometheus usa TCP/9105 e SNMP UDP/1161. L'esposizione esterna è opt-in.

## CLI completa

| Opzione | Default | Funzione |
| --- | ---: | --- |
| `--config FILE` | percorso nativo | Configurazione TOML persistente; le opzioni CLI esplicite hanno precedenza |
| `--scan` | no | Stampa sensori riconosciuti e termina |
| `--list-plugins` | no | Stato plugin e dipendenze |
| `--plugin NOME` | tutti installati | Limita plugin; ripetibile |
| `--cloud-help` | no | Istruzioni Tuya |
| `--cloud-config FILE` | - | Provider cloud in TOML protetto |
| `--scan-duration S` | 8 | Durata scansione BLE |
| `--bluetooth-adapter ADAPTER` | default OS | Controller BlueZ Linux (es. `hci1`) |
| `--poll-interval S` | 30 | Intervallo cicli (1–86400) |
| `--plugin-timeout S` | 15 | Timeout massimo decoder/cloud |
| `--device ID` | tutti | Filtro sensore ripetibile (MAC BLE o ID cloud/plugin) |
| `--device-name MAC=NOME` | radio | Alias BLE ripetibile |
| `--sensor-name ID=NOME` | originale | Alias cloud/multi-canale |
| `--mqtt-host HOST` | - | Broker MQTT |
| `--home-assistant-discovery` | no | Pubblica configurazione Home Assistant MQTT Discovery |
| `--home-assistant-discovery-prefix` | `homeassistant` | Prefisso discovery Home Assistant |
| `--mqtt-port PORT` | 1883/8883 | Porta broker |
| `--mqtt-topic-prefix` | `ble-sensors` | Radice topic |
| `--mqtt-username` | - | Utente broker |
| `--mqtt-password-file` | - | Password da file protetto |
| `--mqtt-tls` | no | TLS con verifica certificato |
| `--mqtt-connect-timeout S` | 15 | Timeout CONNACK/conferma publish |
| `--mqtt-cache` / `--no-mqtt-cache` | attiva | Persiste su disco i messaggi MQTT non inviati |
| `--mqtt-cache-path FILE` | accanto allo state file/directory stato utente | Path spool SQLite |
| `--mqtt-cache-max-size SIZE` | `1GiB` | Dimensione logica massima; accetta byte/KiB/MiB/GiB/TiB |
| `--reuse-stale-data` | no | Riusa l’ultima lettura con `stale: true` se il sensore manca o non ha dati |
| `--allow-insecure-mqtt` | no | Override esplicito rischio MQTT in chiaro |
| `--qos` | 1 | QoS 0, 1 o 2 |
| `--retain` / `--no-retain` | retain | Stato retained |
| `--stale-cycles N` | 3 | Cicli mancanti prima di rimuovere retained |
| `--state-file FILE` | - | Persiste lo stato di pulizia retained tra i riavvii |
| `--once` | no | Un ciclo |
| `--prometheus` | no | Abilita endpoint |
| `--prometheus-host` | `127.0.0.1` | IP ascolto |
| `--prometheus-port` | 9105 | Porta TCP |
| `--allow-external-prometheus` | no | Consente esplicitamente HTTP non autenticato non-loopback |
| `--snmp` | no | Agente SNMPv2c read-only |
| `--snmp-host` | `127.0.0.1` | IP ascolto |
| `--snmp-port` | 1161 | Porta UDP |
| `--snmp-community-file` | - | Community da file protetto |
| `--snmp-base-oid` | `.1.3.6.1.4.1.32473.1.1` | Subtree |
| `--allow-external-snmp` | no | Consente esplicitamente SNMPv2c in chiaro non-loopback |

## Estendere con un plugin

Un pacchetto esterno implementa `SensorPlugin` da `ble_sensors_mqtt.plugin_api` e registra una
factory senza argomenti:

```toml
[project.entry-points."ble_sensors_mqtt.sensor_plugins"]
acme = "acme_sensor.plugin:AcmePlugin"
```

`decode(device, advertisement)` restituisce zero o più `SensorReading`. Deve sempre indicare
marca, modello e protocollo e non deve inserire segreti nei dati. Gli errori sono isolati.

I provider cloud usano un entry point separato e ricevono la propria configurazione TOML più il
lettore di segreti da file protetti:

```toml
[project.entry-points."ble_sensors_mqtt.cloud_plugins"]
acme-cloud = "acme_sensor.cloud:AcmeCloudPlugin"
```

La classe/factory cloud viene costruita come `AcmeCloudPlugin(config, read_secret)` e implementa
`CloudPlugin.poll()`. Per default `acme-cloud` legge `[cloud.acme]`; la classe può esporre
`config_key` per scegliere una tabella diversa. Gli errori cloud sono isolati dal BLE e dagli
altri provider cloud.


## Frontend web autenticato opzionale

Installare `.[web]` (oppure `.[all]`) e abilitare `--frontend` per una console browser professionale e responsive. Mostra stato live/stale e valori normalizzati di ogni sensore esportato, supporta ruoli admin/reader, configurazione runtime persistente, utenti locali, LDAP, SSO OIDC generico, MFA TOTP portabile per utenti locali/LDAP e backup/restore completo cifrato di configurazione, utenti/MFA e cache MQTT. L'account bootstrap è `admin` / `password` e deve cambiare password al primo login. Le impostazioni persistenti del browser sono salvate in un override runtime scrivibile, lasciando protetti e read-only `/etc`/ConfigMap Kubernetes. Vedere `docs/FRONTEND.it.md`.

## Sicurezza, AGID e limiti

Il progetto applica least privilege, TLS verificato, segreti fuori da CLI/environment, limiti
agli input, output JSON sicuro, dipendenze opzionali, logging senza credenziali, hardening
systemd e controlli automatici. Dettagli in `docs/AGID-SECURITY.it.md` e `SECURITY.it.md`. È una
verifica tecnica rispetto alle buone pratiche AGID, non una certificazione AGID. Prima della
produzione eseguire threat modeling e test hardware, gestire vulnerabilità e rollback, e
configurare firewall e ACL MQTT. BLE advertisement e SNMPv2c non garantiscono autenticità o
confidenzialità end-to-end.

```bash
bluetoothctl show
.venv/bin/ble-sensors-mqtt --list-plugins
.venv/bin/ble-sensors-mqtt --scan --scan-duration 20 --log-level DEBUG
systemctl status ble-sensors-mqtt
journalctl -u ble-sensors-mqtt --since today
```

## Configurazione unificata e impostazioni grafiche

Tutte le piattaforme possono usare `config.toml` con precedenza **CLI > file di configurazione > default**. Le release Windows e macOS includono inoltre applicazioni grafiche native di configurazione e installer standard. Vedere `docs/CONFIGURATION.it.md` e `docs/NATIVE-INSTALLERS.it.md`.

## Build e licenza

`scripts/build-package.sh` aggiorna `BUILD` in UTC nel formato `YYYYMMDD-HHMM` e produce ZIP,
TAR.GZ e checksum SHA-256. Licenza EUPL-1.2: vedere `LICENSE`.

Documentazione: manuale italiano in [`docs/USAGE.it.md`](docs/USAGE.it.md) e `docs/ble-sensors-mqtt-manual-v1.0.0-it.pdf`; manuale inglese in [`docs/USAGE.en.md`](docs/USAGE.en.md) e `docs/ble-sensors-mqtt-manual-v1.0.0-en.pdf`.

## Politica release di produzione

La release 1.0.0 è progettata in modalità fail-closed rispetto alle esposizioni di rete non sicure. MQTT remoto o con credenziali in chiaro richiede l'override esplicito `--allow-insecure-mqtt`; in produzione va usato TLS verificato. Prometheus/health e SNMPv2c restano vincolati al loopback salvo uso esplicito dei flag di esposizione esterna. Chiamate cloud e decoder sono limitate da `--plugin-timeout`; i messaggi MQTT hanno dimensione limitata e le publish QoS vengono confermate prima di considerare riuscito il ciclo.

Il server HTTP Prometheus espone `/metrics`, `/healthz` e `/readyz`. La readiness è falsa prima del primo ciclo riuscito e quando l'ultimo successo è più vecchio di circa tre intervalli di polling. I topic MQTT retained dei sensori vengono rimossi dopo `--stale-cycles` assenze consecutive (default 3), non dopo una singola perdita transitoria BLE. Con systemd, `--state-file /var/lib/ble-sensors-mqtt/state.json` conserva questo stato anche tra i riavvii.

Una release di produzione deve superare `scripts/release-check.sh`: compilazione, Ruff, pytest con coverage, Bandit, `pip-audit`, generazione dei due manuali PDF, wheel/sdist standard, `twine check`, SBOM CycloneDX e verifica dei contenuti di release. La CI esegue la suite runtime su Python 3.11, 3.12 e 3.13 con tutte le dipendenze opzionali sensor/cloud. Vedere `docs/PRODUCTION.it.md`.

GitHub Actions automatizza anche la pubblicazione. Il push di un tag come `v1.0.0` avvia l'intera pipeline di test/build; solo dopo il superamento di tutti i gate il job `release` verifica che il tag corrisponda sia a `VERSION` sia a `pyproject.toml`, scarica gli artefatti costruiti dalla CI e crea o aggiorna la GitHub Release corrispondente. La release contiene wheel, sdist, SBOM, archivi deterministici del progetto, checksum SHA-256 e i manuali EN/IT separati. Non serve un token GitHub personale: il job usa il `GITHUB_TOKEN` del repository con `contents: write` soltanto nel job di release.

### Selezione componenti e release check

L'installer Linux interattivo chiede all'inizio quali gruppi opzionali installare: decoder BLE aggiuntivi (`sensors`), provider cloud (`cloud`) e frontend web autenticato (`web`). Per installazioni non presidiate usare i corrispondenti switch `--with-*`/`--without-*`. Gli installer grafici Windows/macOS mostrano invece i componenti di sistema (runtime, servizio/agent in background, Settings GUI); le integrazioni runtime vengono poi abilitate da Settings/configurazione.

`scripts/release-check.sh` installa/verifica per default `.[all,dev,release]`, così strumenti come Ruff e ReportLab sono disponibili anche in un release check manuale. Usare `BLE_SENSORS_RELEASE_SKIP_BOOTSTRAP=1` solo in ambienti già predisposti/offline.
