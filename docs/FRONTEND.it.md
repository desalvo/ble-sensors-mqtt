# Frontend web autenticato opzionale

Il frontend web è opzionale. Installare il profilo `web` (`pip install '.[web]'`) oppure `all`, quindi abilitarlo con `--frontend` o con `[frontend] enabled = true` in `config.toml`.

Per default ascolta solo su `127.0.0.1:8080`. Un bind non-loopback richiede `allow_external = true` / `--allow-external-frontend`. Per accessi remoti usare le opzioni TLS certificate/key integrate oppure un reverse proxy TLS autenticato.

## Primo accesso e ruoli

Il database di autenticazione viene creato automaticamente. L'account iniziale è:

- username: `admin`
- password: `password`
- ruolo: `admin`

Al primo accesso **è obbligatorio cambiare la password iniziale**. I ruoli sono volutamente semplici:

- `admin`: accesso completo a sensori, configurazione, utenti, provider di identità, MFA e backup/restore;
- `reader`: dashboard e stato sensori in sola lettura.

Le password locali sono memorizzate come hash PBKDF2-SHA256 e mai in chiaro.

## Dashboard e configurazione runtime

La dashboard mostra ogni sensore normalizzato esportato dal gateway: nome, indirizzo, marca/modello, protocollo, RSSI, data di osservazione, stato live/stale e tutti i valori normalizzati. Il layout responsive è progettato per desktop, tablet e telefoni.

Gli amministratori possono modificare dal browser la configurazione persistente. Intervallo di polling, durata scansione, timeout plugin e stale fallback vengono applicati immediatamente al processo attivo. Impostazioni di connessione/listener come broker MQTT, endpoint Prometheus/SNMP/frontend, posizione cache, provider cloud e autenticazione vengono salvate e marcate come richiedenti riavvio del servizio.

Le modifiche web vengono scritte in un `runtime-config.toml` scrivibile nella directory dati del frontend, senza modificare il `config.toml` base protetto. Al riavvio la precedenza è:

`CLI > runtime-config.toml > config.toml base > default integrati`.

Questo consente modifiche persistenti dalla GUI anche quando `/etc` o una ConfigMap Kubernetes sono read-only.

## LDAP

Abilitare `[frontend.ldap]` per autenticare contro LDAP. Sono disponibili due modalità:

1. `user_dn_template`, ad esempio `uid={username},ou=people,dc=example,dc=org`;
2. bind/search di servizio con `bind_dn`, `bind_password_file` protetto, `base_dn` e `user_filter`.

Le password LDAP vengono verificate direttamente sul server LDAP e non sono memorizzate localmente. Al primo login riuscito viene creato un profilo shadow locale che contiene solo ruolo applicativo, stato attivo ed eventuale MFA. Il ruolo di default è configurabile e dovrebbe normalmente restare `reader`.

In produzione usare LDAPS o StartTLS e proteggere il file della password di bind.

## SSO OpenID Connect

È supportato OIDC generico tramite `[frontend.oidc]`: URL metadata del provider, client ID, file protetto con client secret, scopes, claim per username e ruolo di default. Questo consente l'uso di provider standard come Google Workspace, Keycloak, Entra ID e altri IdP OIDC correttamente configurati.

Gli utenti OIDC ricevono un profilo shadow locale per il ruolo applicativo. Per SSO l'MFA dovrebbe normalmente essere applicato dall'Identity Provider.

## MFA per utenti locali/LDAP

Gli utenti locali e LDAP possono usare MFA TOTP standard. Un amministratore può creare/abilitare il seed TOTP da **Utenti -> MFA**. La pagina mostra seed Base32 e URI `otpauth://`, utilizzabili con le comuni app Authenticator.

Il seed MFA è intenzionalmente portabile: l'amministratore può registrare lo stesso seed su più istanze ble-sensors-mqtt oppure replicarlo tramite backup completo cifrato. In questo modo lo stesso token TOTP può essere condiviso tra istanze equivalenti della stessa infrastruttura. Il seed esportato deve essere trattato come una credenziale.

## Import/export cifrato

**Backup / Restore** produce un file `.bsmqbackup` cifrato AES-GCM con chiave derivata tramite scrypt dalla passphrase scelta dall'amministratore. La passphrase è obbligatoria.

Il backup include, quando presenti:

- configurazione applicativa effettiva (base più override runtime della GUI);
- profili shadow locali/LDAP/OIDC, hash password, ruoli e seed MFA;
- snapshot della cache MQTT su disco;
- stato runtime dei topic retained;
- file di configurazione cloud/chiavi BLE referenziato dall'istanza.

La spool SQLite MQTT viene esportata tramite backup online SQLite e ripristinata attraverso l'oggetto cache attivo, evitando di copiare brutalmente un database aperto.

L'import ripristina configurazione e profili utenti. Le modifiche relative a rete/autenticazione richiedono un riavvio del servizio.

## Directory dati

Per default lo stato frontend risiede in:

- Linux gestito/Docker/Kubernetes: `/var/lib/ble-sensors-mqtt/frontend` quando è disponibile lo StateDirectory del servizio;
- utente Linux ordinario: `$XDG_STATE_HOME/ble-sensors-mqtt/frontend` oppure `~/.local/state/ble-sensors-mqtt/frontend`;
- Windows: `%PROGRAMDATA%\ble-sensors-mqtt\frontend`;
- macOS: `~/Library/Application Support/ble-sensors-mqtt/frontend`.

Contiene database SQLite di autenticazione, secret di sessione, override della configurazione e dati temporanei/export. Va protetta come stato applicativo sensibile.
