# Windows and macOS graphical installers

## Windows 11 and later

Tagged releases produce both a portable ZIP and a standard graphical Inno Setup installer:

`ble-sensors-mqtt-v<version>-windows-x86_64-setup.exe`

The installer requires Administrator approval, installs the runtime under `Program Files\ble-sensors-mqtt`, registers an automatic Windows Service named `ble-sensors-mqtt`, preserves configuration across upgrades/uninstalls in `%ProgramData%\ble-sensors-mqtt`, and adds **ble-sensors-mqtt Settings** to the Start menu.

The service is installed but is intentionally not started with an empty MQTT configuration. At the end of an interactive install the Settings application opens. Configure the broker and desired exporters, then choose **Save & restart service** or **Start service**. Operations requiring elevation automatically request UAC; no elevated terminal is required.

The Settings GUI contains General, MQTT, Cache, Monitoring, Bluetooth & sensors, and Advanced tabs. It can save/restart the service, start/stop it, test Bluetooth, and open the configuration directory. The same configuration remains editable as TOML for automation.

## macOS Tahoe 26 and later

Tagged releases produce architecture-specific standard `.pkg` installers for Apple Silicon and Intel, plus portable ZIPs. The package installs:

- `/Applications/ble-sensors-mqtt Settings.app`;
- the frozen runtime under `/Library/Application Support/ble-sensors-mqtt/runtime`;
- documentation under `/Library/Application Support/ble-sensors-mqtt/docs`.

The graphical Settings application stores per-user configuration in `~/Library/Application Support/ble-sensors-mqtt/config.toml`. **Start service** creates and loads `~/Library/LaunchAgents/com.desalvo.ble-sensors-mqtt.plist`; **Stop service** unloads it; **Save & restart service** applies changes immediately. This LaunchAgent design deliberately keeps BLE access in the logged-in user context, which is better aligned with macOS Bluetooth privacy controls than a root LaunchDaemon.

Use **Test Bluetooth** once after installation. macOS may then request Bluetooth permission for the installed runtime; permission can subsequently be reviewed in **System Settings > Privacy & Security > Bluetooth**.

## Signing

CI can build the installers without signing credentials, but unsigned Windows/macOS binaries may display SmartScreen/Gatekeeper warnings. Production distribution should add Authenticode signing on Windows and Developer ID signing/notarization on macOS. The installer build is separated from signing so repository secrets can be added later without changing runtime configuration.

## Web frontend on installed systems

The native Windows/macOS bundles include the optional web dependencies. Enable **Web frontend** in the native Settings application, choose bind address/port, save and restart the service/agent. The browser frontend then provides sensor status, user/RBAC management, LDAP/OIDC, TOTP MFA, runtime settings and encrypted backup/restore. The native Settings utility remains available as an out-of-band recovery path if web authentication is misconfigured.
