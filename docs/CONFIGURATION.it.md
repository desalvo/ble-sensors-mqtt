# Configurazione unificata

`ble-sensors-mqtt` supporta un file TOML persistente su tutti i sistemi operativi. La precedenza è sempre:

1. argomenti CLI espliciti;
2. valori presenti in `config.toml`;
3. default interni dell'applicazione.

Per usare un file diverso: `--config PERCORSO`. Senza `--config`, i percorsi nativi sono:

- Linux: `/etc/ble-sensors-mqtt/config.toml`;
- Windows: `%ProgramData%\ble-sensors-mqtt\config.toml`;
- macOS: `~/Library/Application Support/ble-sensors-mqtt/config.toml`.

Il template completo è `config/app.example.toml`. Le sezioni principali sono `[bluetooth]`, `[runtime]`, `[mqtt]`, `[mqtt_cache]`, `[prometheus]`, `[snmp]` e `[cloud]`. Le opzioni ripetibili per sensori/plugin sono array TOML.

Esempio:

```toml
[bluetooth]
poll_interval = 30.0
device_names = ["AA:BB:CC:DD:EE:FF=Sala server"]

[runtime]
reuse_stale_data = true

[mqtt]
host = "mqtt.example.it"
port = 8883
tls = true
home_assistant_discovery = true

[mqtt_cache]
enabled = true
max_size = "1GiB"

[prometheus]
enabled = true
host = "127.0.0.1"
port = 9105
```

I segreti rimangono in file protetti separati. In `config.toml` inserire solo percorsi come `mqtt.password_file` e `snmp.community_file`, non il segreto stesso.

Un override CLI occasionale non modifica il file persistente. Ad esempio:

```bash
ble-sensors-mqtt --config /etc/ble-sensors-mqtt/config.toml --poll-interval 10
```

usa tutta la configurazione memorizzata ma cambia l'intervallo soltanto per quel processo.
