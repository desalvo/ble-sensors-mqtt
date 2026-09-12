# ble-sensors-mqtt

[English](README.en.md) · **Italiano**

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
- unità systemd irrobustita, test, lint, Bandit e audit dipendenze.
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
.venv/bin/pip install '.[all]'      # tutti i decoder + Tuya Cloud
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

Sono esposte `ble_sensors_up`, `ble_sensors_temperature_celsius`,
`ble_sensors_humidity_percent`, `ble_sensors_battery_percent`, `ble_sensors_rssi_dbm` e
`ble_sensors_devices`. Ogni valore numerico/booleano è anche
`ble_sensors_sensor_value{key="...",unit="..."}`; ogni stringa è
`ble_sensors_sensor_info{key="...",value="..."}`. Tutte hanno label `address`, `name`,
`manufacturer`, `model` e `protocol`.

```bash
# Tutte le interfacce IPv4 e porta personalizzata
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --prometheus \
  --prometheus-host 0.0.0.0 --prometheus-port 9200 --allow-external-prometheus
```

Default `127.0.0.1:9105`; usare `::` per IPv6. `/healthz` indica la liveness del processo e `/readyz` restituisce HTTP 200 solo dopo un ciclo di polling recente completato con successo. L'endpoint non ha TLS/autenticazione: il binding non-loopback viene quindi rifiutato senza `--allow-external-prometheus`. Per accesso esterno usare firewall, VPN o reverse proxy autenticato. Le stringhe possono aumentare la
cardinalità Prometheus; disabilitare plugin non necessari.

## SNMP

```bash
sudo sh -c 'umask 077; printf %s "COMMUNITY_CASUALE" > /etc/ble-sensors-mqtt/snmp-community'
sudo chown root:ble-sensors-mqtt /etc/ble-sensors-mqtt/snmp-community
sudo chmod 0640 /etc/ble-sensors-mqtt/snmp-community
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --snmp \
  --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
snmpwalk -v2c -c COMMUNITY_CASUALE 127.0.0.1:1161 1.3.6.1.4.1.32473.1.1
```

La tabella dispositivo contiene nome, indirizzo, RSSI, misure comuni, timestamp, marca,
modello e protocollo. La subtree `.20` contiene ogni scalare come chiave, valore, tipo e unità.
Vedere `docs/BLE-SENSORS-MQTT-MIB.txt`.

```bash
# Tutte le interfacce IPv4 e porta personalizzata
.venv/bin/ble-sensors-mqtt --mqtt-host 192.0.2.10 --snmp \
  --snmp-host 0.0.0.0 --snmp-port 2161 --allow-external-snmp \
  --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
```

Default `127.0.0.1:1161`; `::` espone IPv6. Il binding non-loopback viene rifiutato senza `--allow-external-snmp`. SNMPv2c non cifra: non pubblicarlo direttamente su Internet; usare firewall, VPN o proxy SNMPv3. Il PEN 32473 è per documentazione; in
produzione impostare il PEN assegnato con `--snmp-base-oid`.

## systemd

```bash
sudo scripts/install-systemd.sh
sudo install -m 0640 -o root -g ble-sensors-mqtt /dev/null \
  /etc/ble-sensors-mqtt/mqtt-password
sudo editor /etc/ble-sensors-mqtt/mqtt-password
sudo editor /etc/ble-sensors-mqtt/environment
sudo systemctl enable --now ble-sensors-mqtt
journalctl -u ble-sensors-mqtt -f
```

Esempio environment:

```ini
MQTT_HOST=mqtt.example.it
MQTT_PORT=8883
MQTT_USERNAME=sensor-publisher
POLL_INTERVAL=30
EXTRA_ARGS=--cloud-config /etc/ble-sensors-mqtt/cloud.toml --prometheus --snmp --snmp-community-file /etc/ble-sensors-mqtt/snmp-community
```

Lo script crea l'utente non privilegiato, mantiene il codice applicativo root-owned, installa il runtime completo in una venv isolata e installa l'unità irrobustita. L'unità fornita richiede MQTT TLS verificato. In produzione non rimuovere TLS; la CLI rifiuta inoltre MQTT remoto o con credenziali in chiaro salvo override di rischio esplicito.

## CLI completa

| Opzione | Default | Funzione |
| --- | ---: | --- |
| `--scan` | no | Stampa sensori riconosciuti e termina |
| `--list-plugins` | no | Stato plugin e dipendenze |
| `--plugin NOME` | tutti installati | Limita plugin; ripetibile |
| `--cloud-help` | no | Istruzioni Tuya |
| `--cloud-config FILE` | - | Provider cloud in TOML protetto |
| `--scan-duration S` | 8 | Durata scansione BLE |
| `--poll-interval S` | 30 | Intervallo cicli (1–86400) |
| `--plugin-timeout S` | 15 | Timeout massimo decoder/cloud |
| `--device ID` | tutti | Filtro sensore ripetibile (MAC BLE o ID cloud/plugin) |
| `--device-name MAC=NOME` | radio | Alias BLE ripetibile |
| `--sensor-name ID=NOME` | originale | Alias cloud/multi-canale |
| `--mqtt-host HOST` | - | Broker MQTT |
| `--mqtt-port PORT` | 1883/8883 | Porta broker |
| `--mqtt-topic-prefix` | `ble-sensors` | Radice topic |
| `--mqtt-username` | - | Utente broker |
| `--mqtt-password-file` | - | Password da file protetto |
| `--mqtt-tls` | no | TLS con verifica certificato |
| `--mqtt-connect-timeout S` | 15 | Timeout CONNACK/conferma publish |
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

## Build e licenza

`scripts/build-package.sh` aggiorna `BUILD` in UTC nel formato `YYYYMMDD-HHMM` e produce ZIP,
TAR.GZ e checksum SHA-256. Licenza EUPL-1.2: vedere `LICENSE`.

Documentazione: manuale italiano in [`docs/USAGE.it.md`](docs/USAGE.it.md) e `docs/ble-sensors-mqtt-manual-v1.0.0-it.pdf`; manuale inglese in [`docs/USAGE.en.md`](docs/USAGE.en.md) e `docs/ble-sensors-mqtt-manual-v1.0.0-en.pdf`.

## Politica release di produzione

La release 1.0.0 è progettata in modalità fail-closed rispetto alle esposizioni di rete non sicure. MQTT remoto o con credenziali in chiaro richiede l'override esplicito `--allow-insecure-mqtt`; in produzione va usato TLS verificato. Prometheus/health e SNMPv2c restano vincolati al loopback salvo uso esplicito dei flag di esposizione esterna. Chiamate cloud e decoder sono limitate da `--plugin-timeout`; i messaggi MQTT hanno dimensione limitata e le publish QoS vengono confermate prima di considerare riuscito il ciclo.

Il server HTTP Prometheus espone `/metrics`, `/healthz` e `/readyz`. La readiness è falsa prima del primo ciclo riuscito e quando l'ultimo successo è più vecchio di circa tre intervalli di polling. I topic MQTT retained dei sensori vengono rimossi dopo `--stale-cycles` assenze consecutive (default 3), non dopo una singola perdita transitoria BLE. Con systemd, `--state-file /var/lib/ble-sensors-mqtt/state.json` conserva questo stato anche tra i riavvii.

Una release di produzione deve superare `scripts/release-check.sh`: compilazione, Ruff, pytest con coverage, Bandit, `pip-audit`, generazione dei due manuali PDF, wheel/sdist standard, `twine check`, SBOM CycloneDX e verifica dei contenuti di release. La CI esegue la suite runtime su Python 3.11, 3.12 e 3.13 con tutte le dipendenze opzionali sensor/cloud. Vedere `docs/PRODUCTION.it.md`.
