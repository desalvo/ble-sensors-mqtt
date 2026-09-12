# Valutazione di sicurezza e allineamento AGID

[English](AGID-SECURITY.en.md) · **Italiano**

## Ambito

Questa è un'autovalutazione tecnica della release 1.0.0, non una certificazione AGID né un
audit indipendente. Le misure seguono i principi di ciclo di sviluppo sicuro, codice sicuro,
configurazione sicura e threat modeling richiamati dalle Linee guida AgID per lo sviluppo del
software sicuro.

## Minacce considerate

| Minaccia | Misura implementata | Rischio residuo |
| --- | --- | --- |
| Furto credenziali MQTT | password solo da file, permessi stretti, nessun log del segreto | amministratore host compromesso |
| MITM verso broker | TLS, CA e hostname verificati; nessun flag insecure | CA/host compromessi |
| Pubblicazione non autorizzata | utente broker dedicato e ACL documentata | ACL configurata male |
| Input CLI abusivo | tipi, limiti numerici, topic controllato dall'operatore | operatore locale fidato |
| Payload BLE malevolo | serializzazione limitata in profondità e quantità, niente eval | decoder di terze parti |
| Privilegi e persistenza | utente non root, hardening systemd, filesystem protetto | policy BlueZ/D-Bus host |
| Dipendenze vulnerabili | versioni vincolate, `pip-audit` settimanale, aggiornamenti espliciti | nuova CVE non ancora nota |
| Supply chain | CI read-only, checksum SHA-256 del pacchetto | checksum non firmato |
| Esposizione metriche | servizi opt-in, localhost predefinito, SNMP read-only | dati visibili localmente |
| Community SNMP | file protetto e confronto constant-time | SNMPv2c non cifra il traffico |
| Binding esterno | scelta esplicita di `0.0.0.0`/`::`, warning nei log, porte configurabili | esposizione determinata dal firewall |
| Alias non valido | MAC normalizzato, lunghezza 1-64, caratteri di controllo rifiutati, duplicati bloccati | alias scelto dall'operatore |
| Credenziali Tuya | ID e secret solo da file protetti; TOML senza segreti; HTTPS della libreria | account/cloud/host compromesso |
| Plugin malevolo | entry point espliciti, eccezioni isolate, installazione opzionale | un plugin Python ha i privilegi del processo |
| Indisponibilità cloud | errore isolato e prosecuzione della raccolta BLE | dati Tuya temporaneamente obsoleti/assenti |
| Cardinalità metriche | massimo 256 scalari per sensore e documentazione operativa | etichette stringa variabili |

## Controlli SDLC

- repository pubblico, licenza EUPL-1.2, changelog, security policy e tracciabilità versione/build;
- test automatici e validazione statica con Ruff e Bandit;
- Software Composition Analysis con `pip-audit` a ogni modifica e settimanalmente;
- privilegi minimi e separazione tra codice, configurazione e segreti;
- errori registrati senza credenziali, arresto ordinato e ripartenza controllata;
- protocolli cifrati raccomandati in produzione e verifica certificati non eludibile;
- revisione richiesta prima della release per vulnerabilità, licenze e comportamento su hardware.
- profili di dipendenze separati (`sensors`, `cloud`, `all`) per ridurre superficie di attacco;
- metadati marca/modello/protocollo sempre presenti e limiti su profondità/numero dei valori.

## Verifiche operative prima della produzione

1. Eseguire test, Bandit e `pip-audit` su dipendenze effettivamente risolte.
2. Configurare TLS 1.2/1.3 sul broker e ACL minima sul prefisso dedicato.
3. Applicare aggiornamenti di sicurezza a Raspberry Pi OS e disabilitare servizi non necessari.
4. Proteggere SSH con chiavi, limitare la rete e centralizzare/ruotare i log.
5. Provare perdita rete, broker indisponibile, Bluetooth spento, SIGTERM e riavvio host.
6. Documentare titolare, manutentore, inventario, rischio accettato e piano di aggiornamento.
7. Limitare TCP 9105 e UDP 1161; su reti non fidate usare HTTPS/VPN e un proxy SNMPv3.
8. Installare plugin solo da fonti verificate, controllarne licenza/hash e bloccare le versioni
   effettivamente collaudate in un constraints file di esercizio.
9. Per Tuya, applicare minimo privilegio al progetto cloud, ruotare le chiavi e verificare
   base giuridica, informativa, conservazione e localizzazione dei dati.

## Riferimenti

- AgID, Linee guida per lo sviluppo del software sicuro:
  https://www.agid.gov.it/it/sicurezza/cert-pa/linee-guida-sviluppo-del-software-sicuro
- CERT-AgID, documenti AgID: https://cert-agid.gov.it/documenti-agid/
- AgID, Linee guida sull'acquisizione e il riuso del software per le PA:
  https://docs.italia.it/italia/developers-italia/gl-acquisizione-e-riuso-software-per-pa-docs/
- European Commission, EUPL: https://commission.europa.eu/content/european-union-public-licence_en
