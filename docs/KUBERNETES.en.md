# Kubernetes deployment

The `kubernetes/` directory runs `desalvo/ble-sensors-mqtt:<VERSION>` continuously as a single-replica Deployment with persistent state. BLE operation requires a Linux node with Bluetooth/BlueZ and access to the host system D-Bus. MQTT remains an outbound connection to the configured broker.

## Files

The supplied manifests are:

- `configmap.yaml`: non-secret runtime environment;
- `secret.example.yaml`: example MQTT/SNMP secret keys;
- `arguments-configmap.example.yaml`: optional repeatable/raw application arguments;
- `pvc.yaml`: persistent state volume;
- `deployment.yaml`: long-running daemon;
- `bluetooth-test-pod.yaml`: temporary pod for validating BLE scans through host BlueZ;
- `service.yaml`: internal ClusterIP for Prometheus TCP/9105 and SNMP UDP/1161;
- `service-prometheus-external.yaml`: optional external Prometheus LoadBalancer;
- `service-snmp-external.yaml`: optional external SNMP LoadBalancer;
- `kustomization.yaml`: safe default deployment without the external LoadBalancers.

## Prepare a Bluetooth node

On each node intended to run the pod, install/enable BlueZ and validate the local controller first:

```bash
sudo scripts/check-bluetooth-host.sh --strict
sudo systemctl enable --now bluetooth
sudo rfkill unblock bluetooth
bluetoothctl power on
bluetoothctl list
```

Then label one or more Bluetooth-ready nodes:

```bash
kubectl label node NODE_NAME ble-sensors-mqtt/bluetooth=true
```

The Deployment uses this label as a `nodeSelector`. Host `/run/dbus` is mounted read-only and `DBUS_SYSTEM_BUS_ADDRESS` points at the system bus socket, so Bleak uses host BlueZ. Privileged pods or HCI capabilities are not required when this D-Bus model works. For a cloud-only deployment, remove the node selector and D-Bus hostPath mount.

Before deploying the daemon, validate BLE scanning with the supplied test pod:

```bash
kubectl apply -f kubernetes/bluetooth-test-pod.yaml
kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/ble-sensors-mqtt-bluetooth-test --timeout=60s || true
kubectl logs ble-sensors-mqtt-bluetooth-test
kubectl delete -f kubernetes/bluetooth-test-pod.yaml
```

The test pod uses the same image, node selector, non-root user, and D-Bus mount as the Deployment, but runs only `--scan`. If BlueZ works on the node but the test pod cannot see sensors, inspect host D-Bus/`org.bluez` policy and permissions before considering privileged mode.

## Configure MQTT and exporters

Edit `kubernetes/configmap.yaml`, especially:

```yaml
MQTT_HOST: "mqtt.example.net"
MQTT_PORT: "8883"
MQTT_TLS: "true"
HOME_ASSISTANT_DISCOVERY: "true"
PROMETHEUS_ENABLED: "true"
SNMP_ENABLED: "false"
```

Create secrets without committing them to Git:

```bash
kubectl create secret generic ble-sensors-mqtt-secrets \
  --from-literal=MQTT_USERNAME='ble-sensors-publisher' \
  --from-file=mqtt-password=./mqtt-password
```

If SNMP is enabled:

```bash
kubectl create secret generic ble-sensors-mqtt-secrets \
  --from-literal=MQTT_USERNAME='ble-sensors-publisher' \
  --from-file=mqtt-password=./mqtt-password \
  --from-file=snmp-community=./snmp-community \
  --dry-run=client -o yaml | kubectl apply -f -
```

The pod security context sets `fsGroup: 10001` and the Secret volume uses mode `0440`, satisfying the application's secret-file permission checks while keeping the container non-root.

For repeatable options such as multiple `--device-name`, copy `arguments-configmap.example.yaml` to `arguments-configmap.yaml`, edit it, and either add it to the Kustomization or create it manually:

```bash
kubectl apply -f kubernetes/arguments-configmap.example.yaml
```

The file content is mounted as `/etc/ble-sensors-mqtt/arguments`; it uses one application argument per line.

## Deploy and keep the daemon running

```bash
kubectl apply -k kubernetes/
kubectl rollout status deployment/ble-sensors-mqtt
kubectl get pods -l app.kubernetes.io/name=ble-sensors-mqtt
kubectl logs -f deployment/ble-sensors-mqtt
```

The Deployment has one replica and `Recreate` strategy so two scanner instances do not compete for the same local Bluetooth adapter. Runtime retained-topic state is persisted on the PVC. Kubernetes restarts the pod after process/container failure.

Prometheus `/healthz` and `/readyz` are used as liveness/readiness probes. The default manifests therefore keep Prometheus enabled. If you deliberately disable Prometheus, remove or replace those HTTP probes.

## Internal access

The default `Service` is `ClusterIP` only:

```bash
kubectl get service ble-sensors-mqtt
```

Inside the cluster:

- Prometheus: `http://ble-sensors-mqtt:9105/metrics`;
- health: `http://ble-sensors-mqtt:9105/healthz`;
- readiness: `http://ble-sensors-mqtt:9105/readyz`;
- SNMP: UDP `ble-sensors-mqtt:1161` when enabled.

## Optional external Prometheus and SNMP

External exposure is intentionally not part of the default Kustomization. Apply only what is required:

```bash
kubectl apply -f kubernetes/service-prometheus-external.yaml
kubectl apply -f kubernetes/service-snmp-external.yaml
kubectl get service ble-sensors-mqtt-prometheus-external
kubectl get service ble-sensors-mqtt-snmp-external
```

Both manifests use `type: LoadBalancer`. On bare-metal Kubernetes, a LoadBalancer implementation such as MetalLB may be required. UDP LoadBalancer support is provider-specific.

Prometheus has no built-in authentication/TLS and SNMPv2c is plaintext. External services should be restricted using cloud firewall/security groups, Kubernetes NetworkPolicy where supported, a private LoadBalancer, VPN, or other management-network controls. Do not intentionally expose them to the public Internet without an appropriate security layer.

If a NodePort is preferred, change `type: LoadBalancer` to `NodePort` and, optionally, choose explicit `nodePort` values permitted by the cluster.

## Updating the image

For a released version, update:

```yaml
image: desalvo/ble-sensors-mqtt:X.Y.Z
```

then apply and wait for rollout:

```bash
kubectl apply -k kubernetes/
kubectl rollout status deployment/ble-sensors-mqtt
```

For development tracking of `main`, `desalvo/ble-sensors-mqtt:latest` can be used, but immutable version tags are recommended for production. If using `latest`, set `imagePullPolicy: Always`.
