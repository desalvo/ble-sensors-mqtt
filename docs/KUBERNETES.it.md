# Deployment Kubernetes

La directory `kubernetes/` esegue `desalvo/ble-sensors-mqtt:<VERSION>` in continua come Deployment a singola replica con stato persistente. Il funzionamento BLE richiede un nodo Linux con Bluetooth/BlueZ e accesso al system D-Bus host. MQTT resta una connessione in uscita verso il broker configurato.

## File disponibili

I manifest forniti sono:

- `configmap.yaml`: ambiente runtime non segreto;
- `secret.example.yaml`: esempio delle chiavi segrete MQTT/SNMP;
- `arguments-configmap.example.yaml`: argomenti applicativi opzionali/ripetibili;
- `pvc.yaml`: volume persistente dello stato;
- `deployment.yaml`: demone persistente;
- `bluetooth-test-pod.yaml`: pod temporaneo per verificare lo scan BLE via BlueZ host;
- `service.yaml`: ClusterIP interno per Prometheus TCP/9105 e SNMP UDP/1161;
- `service-prometheus-external.yaml`: LoadBalancer Prometheus esterno opzionale;
- `service-snmp-external.yaml`: LoadBalancer SNMP esterno opzionale;
- `kustomization.yaml`: deployment sicuro di default, senza LoadBalancer esterni.

## Preparazione di un nodo Bluetooth

Sul nodo che dovrà ospitare il pod installare/abilitare BlueZ e verificare localmente il controller:

```bash
sudo scripts/check-bluetooth-host.sh --strict
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
bluetoothctl power on
bluetoothctl list
```

Etichettare quindi uno o più nodi pronti per Bluetooth:

```bash
kubectl label node NOME_NODO ble-sensors-mqtt/bluetooth=true
```

Il Deployment usa questa label come `nodeSelector`. `/run/dbus` dell'host viene montato read-only e `DBUS_SYSTEM_BUS_ADDRESS` punta al socket system bus, quindi Bleak usa il BlueZ host. Non sono richiesti pod privilegiati o capability HCI quando questo modello D-Bus funziona. Per un deployment solo cloud si possono rimuovere node selector e mount hostPath D-Bus.

Prima del Deployment si può verificare lo scan dal pod di test fornito:

```bash
kubectl apply -f kubernetes/bluetooth-test-pod.yaml
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/ble-sensors-mqtt-bluetooth-test --timeout=60s || true
kubectl logs ble-sensors-mqtt-bluetooth-test
kubectl delete -f kubernetes/bluetooth-test-pod.yaml
```

Il pod di test usa la stessa immagine, lo stesso `nodeSelector`, utente non-root e mount D-Bus del Deployment, ma esegue soltanto `--scan`. Se BlueZ funziona sul nodo ma il test pod non vede i sensori, controllare policy/permessi D-Bus e `org.bluez` sul nodo prima di considerare `privileged`.

## Configurazione MQTT ed exporter

Modificare `kubernetes/configmap.yaml`, in particolare:

```yaml
MQTT_HOST: "mqtt.example.net"
MQTT_PORT: "8883"
MQTT_TLS: "true"
HOME_ASSISTANT_DISCOVERY: "true"
PROMETHEUS_ENABLED: "true"
SNMP_ENABLED: "false"
```

Creare i secret senza inserirli in Git:

```bash
kubectl create secret generic ble-sensors-mqtt-secrets \
  --from-literal=MQTT_USERNAME='ble-sensors-publisher' \
  --from-file=mqtt-password=./mqtt-password
```

Se si abilita SNMP:

```bash
kubectl create secret generic ble-sensors-mqtt-secrets \
  --from-literal=MQTT_USERNAME='ble-sensors-publisher' \
  --from-file=mqtt-password=./mqtt-password \
  --from-file=snmp-community=./snmp-community \
  --dry-run=client -o yaml | kubectl apply -f -
```

Il pod imposta `fsGroup: 10001` e il volume Secret usa modo `0440`, rispettando i controlli applicativi sui permessi dei secret senza eseguire il container come root.

Per opzioni ripetibili, ad esempio più `--device-name`, copiare `arguments-configmap.example.yaml` in `arguments-configmap.yaml`, modificarlo e aggiungerlo alla Kustomization oppure crearlo manualmente:

```bash
kubectl apply -f kubernetes/arguments-configmap.example.yaml
```

Il contenuto viene montato come `/etc/ble-sensors-mqtt/arguments` e usa un argomento applicativo per riga.

## Deploy e funzionamento continuo

```bash
kubectl apply -k kubernetes/
kubectl rollout status deployment/ble-sensors-mqtt
kubectl get pods -l app.kubernetes.io/name=ble-sensors-mqtt
kubectl logs -f deployment/ble-sensors-mqtt
```

Il Deployment usa una replica e strategia `Recreate`, evitando che due scanner competano per lo stesso adattatore Bluetooth locale. Lo stato dei topic retained è persistito sul PVC. Kubernetes riavvia il pod dopo un errore del processo/container.

Le probe di liveness/readiness usano gli endpoint Prometheus `/healthz` e `/readyz`. I manifest predefiniti mantengono quindi Prometheus abilitato. Se viene disabilitato intenzionalmente, rimuovere o sostituire le probe HTTP.

## Accesso interno

Il `Service` predefinito è solo `ClusterIP`:

```bash
kubectl get service ble-sensors-mqtt
```

All'interno del cluster:

- Prometheus: `http://ble-sensors-mqtt:9105/metrics`;
- health: `http://ble-sensors-mqtt:9105/healthz`;
- readiness: `http://ble-sensors-mqtt:9105/readyz`;
- SNMP: UDP `ble-sensors-mqtt:1161` quando abilitato.

## Prometheus e SNMP esterni opzionali

L'esposizione esterna è volutamente esclusa dalla Kustomization predefinita. Applicare solo ciò che serve:

```bash
kubectl apply -f kubernetes/service-prometheus-external.yaml
kubectl apply -f kubernetes/service-snmp-external.yaml
kubectl get service ble-sensors-mqtt-prometheus-external
kubectl get service ble-sensors-mqtt-snmp-external
```

Entrambi usano `type: LoadBalancer`. Su Kubernetes bare-metal può essere necessario un componente come MetalLB. Il supporto LoadBalancer UDP dipende dal provider.

Prometheus non offre autenticazione/TLS integrati e SNMPv2c è in chiaro. Limitare i Service esterni con firewall/security group cloud, NetworkPolicy quando supportata, LoadBalancer privato, VPN o altra rete di management. Non esporli intenzionalmente a Internet pubblica senza uno strato di sicurezza adeguato.

Se si preferisce NodePort, cambiare `type: LoadBalancer` in `NodePort` e, facoltativamente, scegliere `nodePort` ammessi dal cluster.

## Aggiornamento dell'immagine

Per una release aggiornata impostare:

```yaml
image: desalvo/ble-sensors-mqtt:X.Y.Z
```

quindi:

```bash
kubectl apply -k kubernetes/
kubectl rollout status deployment/ble-sensors-mqtt
```

Per seguire lo sviluppo su `main` è possibile usare `desalvo/ble-sensors-mqtt:latest`, ma in produzione sono raccomandati tag di versione immutabili. Con `latest`, impostare `imagePullPolicy: Always`.
