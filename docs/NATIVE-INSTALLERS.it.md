# Installer grafici Windows e macOS

## Windows 11 e successivi

Ad ogni tag vengono prodotti sia lo ZIP portabile sia un installer grafico standard Inno Setup:

`ble-sensors-mqtt-v<version>-windows-x86_64-setup.exe`

L'installer richiede approvazione Amministratore, installa il runtime in `Program Files\ble-sensors-mqtt`, registra un servizio Windows automatico chiamato `ble-sensors-mqtt`, conserva la configurazione tra upgrade/disinstallazioni in `%ProgramData%\ble-sensors-mqtt` e aggiunge **ble-sensors-mqtt Settings** al menu Start.

Il servizio viene registrato ma intenzionalmente non avviato finché la configurazione MQTT è vuota. Al termine di un'installazione interattiva viene aperta l'app Settings. Configurare broker ed exporter desiderati e poi scegliere **Save & restart service** oppure **Start service**. Le operazioni privilegiate richiedono automaticamente UAC: non serve un terminale amministrativo.

La GUI contiene le schede General, MQTT, Cache, Monitoring, Bluetooth & sensors e Advanced. Può salvare e riavviare il servizio, avviarlo/fermarlo, provare il Bluetooth e aprire la cartella di configurazione. Lo stesso file TOML resta modificabile manualmente per l'automazione.

## macOS Tahoe 26 e successivi

Ad ogni tag vengono prodotti installer standard `.pkg` separati per Apple Silicon e Intel, oltre agli ZIP portabili. Il package installa:

- `/Applications/ble-sensors-mqtt Settings.app`;
- il runtime frozen in `/Library/Application Support/ble-sensors-mqtt/runtime`;
- la documentazione in `/Library/Application Support/ble-sensors-mqtt/docs`.

L'app Settings salva la configurazione utente in `~/Library/Application Support/ble-sensors-mqtt/config.toml`. **Start service** crea e carica `~/Library/LaunchAgents/com.desalvo.ble-sensors-mqtt.plist`; **Stop service** lo scarica; **Save & restart service** applica subito le modifiche. L'uso di un LaunchAgent mantiene intenzionalmente il BLE nel contesto dell'utente loggato, più coerente con i controlli privacy Bluetooth di macOS rispetto a un LaunchDaemon root.

Dopo l'installazione usare una volta **Test Bluetooth**. macOS può chiedere l'autorizzazione Bluetooth per il runtime installato; l'autorizzazione può poi essere controllata in **Impostazioni di Sistema > Privacy e Sicurezza > Bluetooth**.

## Firma

La CI può costruire gli installer anche senza credenziali di firma, ma binari Windows/macOS non firmati possono mostrare avvisi SmartScreen/Gatekeeper. Per distribuzione di produzione è consigliata firma Authenticode su Windows e Developer ID + notarizzazione su macOS. La fase di build è separata dalla firma, così le credenziali possono essere aggiunte come secret del repository senza cambiare la configurazione runtime.

## Frontend web sui sistemi installati

I bundle nativi Windows/macOS includono le dipendenze web opzionali. Abilitare **Web frontend** nell'applicazione Settings nativa, scegliere indirizzo/porta, salvare e riavviare servizio/agent. Il frontend browser offre quindi stato sensori, gestione utenti/RBAC, LDAP/OIDC, MFA TOTP, impostazioni runtime e backup/restore cifrato. La utility Settings nativa resta disponibile come percorso di recupero fuori banda se l'autenticazione web viene configurata in modo errato.
