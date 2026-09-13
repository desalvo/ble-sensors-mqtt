# Supported hosts and Bluetooth adapters

## Linux

The primary unattended deployment target is Linux on **x86_64 or arm64**. Supported families include Debian and derivatives (Debian, Ubuntu, Raspberry Pi OS) and Red Hat families (RHEL, Rocky Linux, AlmaLinux, CentOS Stream, Fedora). Python 3.11+, BlueZ, D-Bus and a working Bluetooth controller are required.

Both internal Bluetooth controllers and USB Bluetooth dongles are supported when they are visible to BlueZ. Check the host with:

```bash
sudo scripts/check-bluetooth-host.sh --strict
bluetoothctl list
```

On systems with multiple controllers, select a Linux BlueZ adapter explicitly:

```bash
ble-sensors-mqtt --scan --bluetooth-adapter hci1
ble-sensors-mqtt --mqtt-host 127.0.0.1 --bluetooth-adapter hci1
```

The default remains the controller selected by Bleak/BlueZ. USB dongles do not require direct raw-HCI access from the application; the normal systemd installation talks to BlueZ through D-Bus. Docker/Kubernetes continue to use host BlueZ through `/run/dbus`.

For a complete systemd installation:

```bash
sudo scripts/install-from-github.sh --mqtt-host mqtt.example.net
```

The bootstrap recognizes `apt-get`, `dnf` and `yum`, installs common prerequisites including `usbutils`, and therefore covers the Debian and Red Hat families above.

## Windows 11 and later

The Python application and native CI bundle support Windows through Bleak's Windows Bluetooth backend. Use a Bluetooth adapter supported by Windows (internal or USB) and verify it in Windows Settings/Device Manager before scanning. The OS chooses the Bluetooth controller; `--bluetooth-adapter` is Linux-only.

Tagged releases build both a portable x86_64 ZIP and a standard graphical `-setup.exe` installer. The installer registers the Windows Service and adds **ble-sensors-mqtt Settings** to the Start menu. CLI use remains available from the portable bundle:

```powershell
.\ble-sensors-mqtt.exe --scan
.\ble-sensors-mqtt.exe --mqtt-host 127.0.0.1 --prometheus
```

Persistent MQTT cache defaults under `%LOCALAPPDATA%\ble-sensors-mqtt\mqtt-cache.sqlite3`. POSIX mode-bit checks are not applied on Windows; protect secret files with Windows ACLs. Windows native artifacts are smoke-tested by CI, but BLE hardware is not available on GitHub-hosted runners, so physical-adapter validation must be performed on the target host.

## macOS Tahoe (26) and later

Tagged releases build separate native ZIPs and standard `.pkg` installers for Apple Silicon and Intel on GitHub's macOS 26 runners. The package installs **ble-sensors-mqtt Settings.app** in `/Applications`; the portable CLI remains available:

```bash
./ble-sensors-mqtt --scan
./ble-sensors-mqtt --mqtt-host 127.0.0.1 --prometheus
```

The default MQTT cache is under `~/Library/Application Support/ble-sensors-mqtt/`. macOS manages the Bluetooth controller; `--bluetooth-adapter` is Linux-only. Grant Bluetooth permission to the terminal/application when macOS requests it under **System Settings > Privacy & Security > Bluetooth**.

The bundle is built on macOS 26 so it targets Tahoe and later. Native artifacts are smoke-tested without physical BLE hardware in CI.

## Native bundle scope

The native builder always includes the core SwitchBot/Bleak/MQTT functionality. During CI it attempts to install every optional built-in sensor/cloud dependency individually; platform-incompatible optional libraries are reported and omitted instead of making the whole native artifact fail. `--list-plugins` shows what the bundle actually contains. Third-party entry-point plugins are not automatically frozen; use the normal Python installation or rebuild the native package with that plugin installed.


For graphical service configuration and installer behavior, see `NATIVE-INSTALLERS.en.md`. For the shared TOML schema, see `CONFIGURATION.en.md`.
