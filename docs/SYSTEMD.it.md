# Deployment systemd

`ble-sensors-mqtt` è pensato per funzionare in continua come demone Linux non privilegiato su x86_64 o arm64. L'installer fornito crea un account dedicato, una virtualenv Python isolata, configurazione root-owned, stato runtime persistente e una unità systemd irrobustita.

### Bluetooth interno e USB

BlueZ può esporre un controller interno, un dongle USB oppure entrambi. `bluetoothctl list` mostra i controller disponibili. Se ce n'è più di uno, passare `--bluetooth-adapter hciN` tra gli argomenti dell'applicazione/installer systemd per scegliere l'adattatore BlueZ desiderato. Il bootstrap installa `usbutils` dove disponibile per facilitare la diagnosi con `lsusb`.

## Prerequisiti

Installare Python 3.11 o successivo, `python3-venv`, BlueZ e systemd. L'adattatore Bluetooth dell'host deve già funzionare con BlueZ. L'installer va eseguito come root, normalmente tramite `sudo`.


## Installazione facile direttamente da GitHub

Per una macchina Linux nuova è disponibile `scripts/install-from-github.sh`. Lo script installa i prerequisiti comuni, usa il clone corrente oppure clona/aggiorna `https://github.com/desalvo/ble-sensors-mqtt.git`, verifica BlueZ/Bluetooth, poi richiama `install-systemd.sh`. Quest'ultimo crea la virtualenv e il servizio systemd.

Installazione interattiva dal clone:

```bash
git clone https://github.com/desalvo/ble-sensors-mqtt.git
cd ble-sensors-mqtt
sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net --prometheus
```

Installazione non interattiva:

```bash
sudo scripts/install-from-github.sh --ref main --non-interactive \
  --mqtt-host mqtt.example.net --mqtt-tls \
  --home-assistant-discovery --prometheus
```

Per installare una release precisa usare, per esempio, `--ref v1.0.0`. Se eseguito dentro un clone Git, lo script usa direttamente quel checkout. Fuori da un clone usa `/usr/local/src/ble-sensors-mqtt` come checkout gestito; l'installazione runtime resta in `/opt/ble-sensors-mqtt`. Usare `--skip-system-deps` se i pacchetti host sono già gestiti esternamente e `--skip-bluetooth-check` solo per deployment esclusivamente cloud o quando il controllo viene eseguito separatamente.

Lo script riconosce `apt`, `dnf` e `yum`, coprendo Debian/Ubuntu/Raspberry Pi OS e RHEL/Rocky/AlmaLinux/CentOS/Fedora; in caso di package manager differente richiede di installare manualmente Git, Python >=3.11 con supporto venv, BlueZ, D-Bus e `rfkill`.

## Verifica Bluetooth host

Prima di installare o diagnosticare il servizio eseguire:

```bash
sudo scripts/check-bluetooth-host.sh --strict
```

Il controllo verifica `/run/dbus/system_bus_socket`, `bluetooth.service`, presenza di almeno un controller BlueZ, stato `Powered`, `rfkill` e presenza di `org.bluez` sul system D-Bus. Azioni tipiche:

```bash
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
bluetoothctl list
bluetoothctl show
bluetoothctl power on
```

Il servizio usa BlueZ dell'host tramite system D-Bus; non richiede accesso privilegiato diretto all'adattatore HCI. L'utente `ble-sensors-mqtt` viene aggiunto al gruppo `bluetooth` se tale gruppo esiste.

## Installazione interattiva

La modalità interattiva è il default:

```bash
sudo scripts/install-systemd.sh --mqtt-host mqtt.example.net
```

Ogni valore passato via CLI viene mostrato come default dal wizard. Premendo Invio viene mantenuto. Le opzioni ripetibili già fornite, come `--device`, `--device-name`, `--sensor-name` e `--extra-arg`, vengono conservate e il wizard permette di aggiungerne altre.

Esempio con alcuni default già valorizzati:

```bash
sudo scripts/install-systemd.sh \
  --mqtt-host mqtt.example.net \
  --mqtt-username ble-sensors-publisher \
  --device-name 'AA:BB:CC:DD:EE:01=Soggiorno' \
  --home-assistant-discovery \
  --prometheus
```

## Installazione non interattiva

Usare `--non-interactive` per installare esclusivamente con i valori CLI/default senza porre domande:

```bash
sudo scripts/install-systemd.sh --non-interactive \
  --mqtt-host mqtt.example.net \
  --mqtt-port 8883 \
  --mqtt-tls \
  --mqtt-username ble-sensors-publisher \
  --mqtt-password-file ./mqtt-password \
  --device-name 'AA:BB:CC:DD:EE:01=Soggiorno' \
  --device-name 'AA:BB:CC:DD:EE:02=Camera' \
  --home-assistant-discovery \
  --prometheus
```

Eseguire `scripts/install-systemd.sh --help` per tutte le opzioni di provisioning supportate.

## Cosa crea l'installer

Layout predefinito:

- applicazione e virtualenv: `/opt/ble-sensors-mqtt`;
- configurazione protetta: `/etc/ble-sensors-mqtt`;
- configurazione unificata: `/etc/ble-sensors-mqtt/config.toml`;
- stato persistente: `/var/lib/ble-sensors-mqtt/state.json`;
- unità: `/etc/systemd/system/ble-sensors-mqtt.service`;
- utente/gruppo di servizio: `ble-sensors-mqtt`.

Il servizio usa lo stesso schema TOML di Windows e macOS. Le opzioni ripetibili sono array TOML, i secret restano in file protetti separati e la configurazione generata viene validata dall'applicazione installata prima di modificare systemd. Gli argomenti CLI continuano ad avere precedenza sul TOML per esecuzioni manuali.

## Installazione manuale

L'installer è raccomandato, ma la procedura equivalente è:

```bash
sudo useradd --system --home-dir /opt/ble-sensors-mqtt \
  --shell /usr/sbin/nologin ble-sensors-mqtt
sudo install -d -m 0755 /opt/ble-sensors-mqtt
sudo install -d -m 0750 -o root -g ble-sensors-mqtt /etc/ble-sensors-mqtt
sudo cp -a . /opt/ble-sensors-mqtt/
sudo python3 -m venv /opt/ble-sensors-mqtt/.venv
sudo /opt/ble-sensors-mqtt/.venv/bin/pip install --upgrade \
  pip 'setuptools>=83' wheel '/opt/ble-sensors-mqtt[all]'
```

Creare `/etc/ble-sensors-mqtt/config.toml`, per esempio:

```toml
[mqtt]
host = "mqtt.example.it"
port = 8883
tls = true

[runtime]
state_file = "/var/lib/ble-sensors-mqtt/state.json"

[prometheus]
enabled = true
```

Proteggerlo con ownership `root:ble-sensors-mqtt` e mode `0640`. Vedere `CONFIGURATION.it.md` per lo schema completo.

Installare quindi l'unità fornita:

```bash
sudo cp systemd/ble-sensors-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ble-sensors-mqtt
```

Se l'applicazione è installata in un percorso diverso da `/opt/ble-sensors-mqtt` o la configurazione non è in `/etc/ble-sensors-mqtt`, adattare `ExecStart`. Per l'accesso BLE aggiungere l'utente di servizio al gruppo host `bluetooth`, se presente.

## Gestione

```bash
sudo systemctl status ble-sensors-mqtt
sudo systemctl restart ble-sensors-mqtt
journalctl -u ble-sensors-mqtt -f
```

Per cambiare configurazione modificare l'array JSON oppure rieseguire l'installer con le opzioni desiderate e poi riavviare il servizio. Mantenere l'account non privilegiato e gli alberi applicazione/configurazione non scrivibili dal demone.

## Fallback stale e cache MQTT

L’installer chiede se abilitare il riuso stale e come configurare la cache MQTT persistente. I default sono cache attiva, `/var/lib/ble-sensors-mqtt/mqtt-cache.sqlite3`, 1 GiB e riuso stale disattivato. Gli stessi valori possono essere passati senza interazione con `--reuse-stale-data`, `--mqtt-cache-path`, `--mqtt-cache-max-size` o `--no-mqtt-cache`.
