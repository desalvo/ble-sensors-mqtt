# Changelog

- L’acquisizione sensori ora ritenta i dispositivi BLE noti fino a 10 finestre nello stesso ciclo di polling e imposta `stale=true` solo dopo 10 cicli consecutivi mancanti; entrambe le soglie sono configurabili da CLI/configurazione e wizard di installazione.
- Aggiunto frontend web responsive autenticato opzionale con dashboard sensori, RBAC admin/reader, autenticazione locale/LDAP/OIDC, MFA TOTP portabile, configurazione runtime persistente e backup/restore completo cifrato.
- Aggiunti configurazione unificata `config.toml` (CLI > file > default), applicazioni grafiche Settings per Windows/macOS, servizio Windows e gestione LaunchAgent launchd su macOS. La CI sui tag costruisce ora installer standard Windows `.exe` e macOS `.pkg` oltre ai bundle portabili.
- Aggiunti preflight Bluetooth host, mount `/run/dbus` esplicito per Docker/Kubernetes, pod Kubernetes di test BLE e installer bootstrap da clone GitHub con prerequisiti, venv e systemd.

[English](CHANGELOG.en.md) · **Italiano**

- Aggiunto supporto di prima classe per presenza/motion/occupancy/moving: alias vendor comuni, binary sensor Home Assistant, gauge Prometheus dedicate e colonne nella tabella SNMP comune.

## 1.0.0 - 2026-09-12

- Esteso il supporto host a Linux x86_64/arm64 sulle famiglie Debian e Red Hat, Bluetooth interno/USB con selezione adattatore Linux, Windows 11+, macOS Tahoe 26+ e bundle nativi generati dalla CI ad ogni tag.

- Estesa la documentazione Prometheus/SNMP con i contratti completi metriche/OID e corretti gli indici della tabella SNMP generica per rispettare i tipi Integer32 della MIB inclusa.

- Aggiunti riuso opzionale delle letture stale e cache MQTT SQLite persistente e limitata con replay FIFO automatico alla riconnessione.

- Aggiunti installer systemd interattivo/non-interattivo, Docker/Compose multiarch, manifest Kubernetes e pubblicazione Docker Hub in CI.

- Aggiunto Home Assistant MQTT Discovery opzionale (`--home-assistant-discovery`) con raggruppamento per device, entità per valori scalari, device/state class e unità note, availability del bridge, configurazione retained e cleanup dei topic discovery obsoleti.
- GitHub Actions pubblica ora automaticamente le release taggate `v*` solo dopo il superamento di tutti i gate test/build, con validazione tag/versione, asset costruiti dalla CI, checksum SHA-256 consolidati e aggiornamento idempotente degli asset.
- Release irrobustita per produzione con regole fail-closed sull'esposizione di rete.
- MQTT attende CONNACK e conferma delle publish, usa backoff di riconnessione e rifiuta connessioni remote/non cifrate o con credenziali/non cifrate salvo consenso esplicito.
- I topic MQTT retained dei sensori vengono rimossi solo dopo un numero configurabile di cicli mancanti consecutivi (`--stale-cycles`), evitando di reagire a una singola scansione BLE persa.
- Dipendenza runtime diretta `bleak`; versione centralizzata e riutilizzata anche da SNMP.
- Timeout per plugin/cloud e polling concorrente dei provider cloud.
- Endpoint Prometheus `/healthz` e `/readyz` e metriche sui cicli/errori runtime.
- Binding esterni Prometheus non autenticati e SNMPv2c in chiaro richiedono flag di consenso espliciti.
- I file segreti devono essere file regolari con permessi `0640` o più restrittivi; dati plugin e dimensione payload MQTT sono limitati.
- Deploy systemd root-owned con sandbox aggiuntiva e script di installazione idempotente.
- CI su Python 3.11/3.12/3.13 con tutti i plugin opzionali, lint, test, coverage, Bandit, `pip-audit`, build wheel/sdist, `twine check` e SBOM CycloneDX.
- Configurazione Dependabot e script di verifica release.
- Wheel e sdist standard obbligatori oltre agli archivi di progetto e ai manuali EN/IT separati.

## 0.2.0 - 2026-09-11

- Registry cloud separato con entry point `ble_sensors_mqtt.cloud_plugins` e isolamento degli errori.
- Filtro generico `--device ID` per MAC BLE e identificatori cloud/plugin.
- Nomi espliciti `.en.md` / `.it.md` per README, sicurezza, changelog, uso e documenti AgID.
- Test di contratto estesi per identità/dati normalizzati su payload MQTT, Prometheus e SNMP.
- Documentazione completa in italiano e inglese, con manuali PDF separati e interfaccia
  applicativa interamente in inglese.
- Logo applicativo e copertina PDF aggiornata; titoli legati al primo contenuto successivo.
- Architettura plugin con registry interno ed entry point `ble_sensors_mqtt.sensor_plugins`.
- Supporto opzionale Xiaomi/Mijia, Govee, Inkbird, ThermoPro, Qingping/ClearGrass,
  BTHome/Shelly BLU/ATC-PVVX, RuuviTag, SensorPush, Airthings, Mopeka e Tuya Cloud.
- Identità normalizzata `manufacturer`, `model`, `protocol` in MQTT, Prometheus e SNMP.
- Esposizione di tutti i valori scalari tramite metriche Prometheus e tabella SNMP generica.
- Configurazione cloud TOML protetta e alias `--sensor-name` per identificatori non-MAC.
- Esportatori opzionali Prometheus e SNMPv2c read-only.
- MIB SNMP, binding locale predefinito e community letta da file protetto.
- Indirizzi IPv4/IPv6 e porte degli esportatori configurabili da CLI, inclusi binding esterni.
- Alias ripetibili `--device-name MAC=NOME`, propagati a MQTT, Prometheus, SNMP e scan.

## 0.1.0 - 2026-09-11

- Prima release: gateway multi-sensore plugin-based, polling continuo e pubblicazione MQTT.
- TLS, autenticazione tramite password file, filtri MAC e unità systemd irrobustita.
- Test, lint, analisi statica e audit dipendenze in CI.

- La dashboard ora risolve anche valori annidati e mette in evidenza le ultime letture comuni per dispositivo.
- Aggiunto storico persistente SQLite con retention predefinita di 30 giorni, grafici multi-sensore, tabelle deduplicate, cancellazione per intervallo/totale, configurazione da impostazioni/CLI e integrazione nel backup/ripristino cifrato.

- Corretto il polling BLE: più advertisement dello stesso dispositivo nella stessa finestra di scansione vengono decodificati in ordine e viene esportata l'ultima lettura valida, evitando che temperatura/altri valori sembrino bloccati tra i cicli.
