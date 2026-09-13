# Host e adattatori Bluetooth supportati

## Linux

Il target principale per il funzionamento continuo è Linux su **x86_64 o arm64**. Sono supportate almeno le famiglie Debian e derivate (Debian, Ubuntu, Raspberry Pi OS) e Red Hat e derivate (RHEL, Rocky Linux, AlmaLinux, CentOS Stream, Fedora). Servono Python 3.11+, BlueZ, D-Bus e un controller Bluetooth funzionante.

Sono supportati sia Bluetooth interno sia dongle Bluetooth USB, purché visibili a BlueZ. Verificare con:

```bash
sudo scripts/check-bluetooth-host.sh --strict
bluetoothctl list
```

Se sono presenti più controller, su Linux è possibile scegliere esplicitamente l'adattatore BlueZ:

```bash
ble-sensors-mqtt --scan --bluetooth-adapter hci1
ble-sensors-mqtt --mqtt-host 127.0.0.1 --bluetooth-adapter hci1
```

Senza opzione viene usato il controller scelto da Bleak/BlueZ. Un dongle USB non richiede accesso raw-HCI diretto dall'applicazione: l'installazione systemd comunica normalmente con BlueZ via D-Bus. Docker/Kubernetes continuano a usare BlueZ dell'host tramite `/run/dbus`.

Installazione systemd completa:

```bash
sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net
```

Il bootstrap riconosce `apt-get`, `dnf` e `yum`, installa anche `usbutils` e copre quindi le famiglie Debian e Red Hat sopra indicate.

## Windows 11 e successivi

L'applicazione Python e il bundle nativo prodotto dalla CI supportano Windows tramite il backend Bluetooth Windows di Bleak. È possibile usare un controller interno o USB supportato da Windows; verificarlo prima in Impostazioni/Gestione dispositivi. La scelta del controller è demandata al sistema operativo; `--bluetooth-adapter` è solo Linux.

Ogni release taggata produce uno ZIP x86_64 con `ble-sensors-mqtt.exe`. Estrarlo e avviarlo da PowerShell o Prompt:

```powershell
.\ble-sensors-mqtt.exe --scan
.\ble-sensors-mqtt.exe --mqtt-host 127.0.0.1 --prometheus
```

La cache MQTT persistente viene creata per default sotto `%LOCALAPPDATA%\ble-sensors-mqtt\mqtt-cache.sqlite3`. I controlli POSIX sui mode bit non vengono applicati in Windows: proteggere i secret tramite ACL Windows. La CI esegue smoke test del bundle, ma i runner GitHub non dispongono dell'hardware BLE fisico, quindi il controller va validato sull'host reale.

## macOS Tahoe (26) e successivi

Ogni release taggata produce ZIP separati per Apple Silicon e Intel usando runner GitHub macOS 26. Estrarre e avviare il binario corrispondente:

```bash
./ble-sensors-mqtt --scan
./ble-sensors-mqtt --mqtt-host 127.0.0.1 --prometheus
```

La cache MQTT di default è sotto `~/Library/Application Support/ble-sensors-mqtt/`. macOS gestisce il controller Bluetooth e `--bluetooth-adapter` resta solo Linux. Quando richiesto, autorizzare Bluetooth in **Impostazioni di Sistema > Privacy e Sicurezza > Bluetooth**.

Il bundle viene costruito su macOS 26 e quindi ha come target Tahoe e versioni successive. La CI esegue smoke test senza hardware BLE fisico.

## Contenuto dei bundle nativi

Il builder include sempre funzionalità core SwitchBot/Bleak/MQTT. In CI tenta poi di installare singolarmente tutte le dipendenze opzionali dei sensori/cloud; quelle non compatibili con la piattaforma vengono segnalate e omesse senza far fallire l'intero artifact. `--list-plugins` mostra cosa è realmente incluso. I plugin di terze parti basati su entry point non vengono congelati automaticamente: usare l'installazione Python normale o ricostruire il bundle con il plugin installato.


## Installer grafici e configurazione del servizio

Le release taggate producono un installer Windows `-setup.exe` e package macOS `.pkg`, oltre ai bundle portabili. Windows installa un servizio di sistema e l'app **ble-sensors-mqtt Settings** nel menu Start; macOS installa **ble-sensors-mqtt Settings.app** e usa un LaunchAgent per utente. Vedere `NATIVE-INSTALLERS.it.md` e `CONFIGURATION.it.md`.
