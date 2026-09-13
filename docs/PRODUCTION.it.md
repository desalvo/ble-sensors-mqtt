# Deploy e criteri di release per produzione

[English](PRODUCTION.en.md) · **Italiano**

La release 1.0.0 ha come target principale il funzionamento Linux non presidiato su x86_64/arm64, mentre le release taggate producono anche bundle nativi da riga di comando per Windows 11+ e macOS Tahoe 26+. Per production-grade si intende che l'applicazione opera in fail-closed rispetto alle esposizioni di rete non sicure, isola gli errori dei plugin, limita i dati non fidati restituiti dai plugin, espone liveness/readiness, gira con un account systemd non privilegiato e sandboxato e impone gate automatici di release. Questo non rende SNMPv2c cifrato e non aggiunge autenticazione a Prometheus: tali servizi restano su loopback per default e richiedono consenso esplicito per il binding esterno.

## Controlli di deploy obbligatori

- Usare MQTT TLS con verifica del certificato per ogni broker non-loopback. Non usare `--allow-insecure-mqtt` in produzione.
- Tenere Prometheus/health su loopback salvo protezione tramite firewall, VPN o reverse proxy TLS autenticato. Il binding esterno richiede `--allow-external-prometheus`.
- Tenere SNMPv2c su loopback. Se un SNMPv2c esterno legacy è inevitabile, il binding richiede `--allow-external-snmp`; usare VPN/firewall o proxy SNMPv3.
- Salvare password, community, bind key e credenziali cloud in file regolari con mode `0640` o più restrittivo. Non passare segreti nella riga di comando.
- Usare l'unità systemd fornita o isolamento equivalente a minimo privilegio. L'albero applicativo sotto `/opt` deve essere root-owned e non scrivibile dall'utente del servizio.
- Usare un enterprise OID assegnato con `--snmp-base-oid` per una MIB realmente produttiva.

## Affidabilità runtime

L'avvio MQTT viene considerato riuscito solo dopo il CONNACK del broker. Le publish QoS vengono confermate prima di marcare riuscito un ciclo. Le riconnessioni usano backoff limitato. Un topic retained di un sensore viene rimosso solo dopo `--stale-cycles` assenze consecutive, proteggendo da una singola scansione BLE persa. Il deploy systemd persiste atomicamente lo stato topic/assenze in `/var/lib/ble-sensors-mqtt/state.json`, quindi la pulizia sopravvive ai riavvii. Le chiamate decoder/cloud sono limitate da `--plugin-timeout`; i provider cloud vengono interrogati in parallelo e isolati fra loro.

Il server HTTP Prometheus fornisce `/healthz` e `/readyz`. La readiness è falsa prima del primo polling riuscito e quando l'ultimo successo è troppo vecchio. `ble_sensors_cycles_total` e `ble_sensors_cycles_failed_total` espongono contatori di affidabilità runtime.

## Gate di release

Una release candidate non è approvata finché `scripts/release-check.sh` non termina con successo in un ambiente con accesso Internet e set completo `.[all,dev,release]`. Il gate esegue compilazione, Ruff, pytest/coverage, Bandit, `pip-audit`, generazione manuali, build wheel/sdist, `twine check`, SBOM CycloneDX e validazione dei contenuti degli artefatti. La CI esegue la suite runtime su Python 3.11, 3.12 e 3.13.

La release deve includere wheel, sdist, SBOM, checksum, archivio sorgente del progetto e manuali italiano/inglese separati.

### GitHub Release automatica

Il workflow GitHub Actions può essere avviato anche manualmente tramite `workflow_dispatch`. Le pull request eseguono la validazione. Un push su `main` esegue la validazione, costruisce e carica come artifact del workflow i package nativi Windows/macOS e può inoltre pubblicare l'immagine Docker opzionale `latest` quando la pubblicazione Docker Hub è abilitata. Il push di un tag `v*` costruisce gli stessi package nativi e, soltanto se tutti i job prerequisiti terminano con successo, avvia un job di release con permesso `contents: write` limitato al repository. Il job verifica che `vX.Y.Z` corrisponda sia a `VERSION` sia a `[project].version` in `pyproject.toml`, scarica gli artefatti generati dal job di build, crea un `SHA256SUMS.txt` consolidato e crea o aggiorna la GitHub Release usando il comando `gh` e il `GITHUB_TOKEN` fornito da GitHub Actions.

Non sostituire artefatti CI falliti con file costruiti manualmente. Gli asset pubblicati devono provenire dal commit taggato che ha superato la CI. Il rerun di un workflow di tag parzialmente completato è sicuro: gli asset esistenti vengono sostituiti con `--clobber`.

## Docker Hub CI

Impostare la variabile repository `DOCKERHUB_PUSH_ENABLED=true`, la variabile `DOCKERHUB_USERNAME=desalvo` e il secret `DOCKERHUB_TOKEN`. Dopo test/build, i push su `main` pubblicano `desalvo/ble-sensors-mqtt:latest`; i tag `vX.Y.Z` pubblicano `desalvo/ble-sensors-mqtt:X.Y.Z` per amd64 e arm64.

## Persistenza durante indisponibilità MQTT

Lo spool MQTT SQLite predefinito fornisce consegna bounded at-least-once durante indisponibilità del broker e restart del processo. La capacità logica predefinita è 1 GiB. In produzione collocare la cache su storage persistente e monitorare lo spazio disco; al raggiungimento del limite configurato vengono eliminati prima i record più vecchi.

## Artifact nativi Windows/macOS

Ad ogni push su `main` e ad ogni tag `vX.Y.Z`, la CI crea bundle PyInstaller nativi su `windows-2025`, `macos-26` (Apple Silicon) e `macos-26-intel`. Le build di `main` restano artifact del workflow; quelle taggate vengono inoltre raccolte nella GitHub Release. Ogni bundle viene verificato con `--version` e `--list-plugins` prima dell'upload. Le dipendenze opzionali sensori/cloud vengono installate best-effort per piattaforma; quelle non supportate vengono omesse e risultano visibili tramite `--list-plugins`. I runner CI non dispongono di hardware Bluetooth fisico, quindi la validazione radio BLE resta un test di accettazione sull'host reale.

## Controlli di produzione del frontend

Il frontend opzionale è autenticato ma va comunque trattato come superficie amministrativa. Mantenerlo per default su loopback/rete interna, usare HTTPS per accessi remoti, cambiare subito la credenziale bootstrap `admin/password`, preferire ruoli reader, abilitare TOTP per amministratori locali/LDAP, proteggere la directory di stato frontend e trattare i `.bsmqbackup` cifrati come secret. LDAP dovrebbe usare LDAPS/StartTLS e i secret di client OIDC/bind LDAP devono restare in file protetti.
