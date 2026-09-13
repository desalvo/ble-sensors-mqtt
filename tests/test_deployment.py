from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_systemd_uses_unified_config() -> None:
    unit = (ROOT / "systemd/ble-sensors-mqtt.service").read_text(encoding="utf-8")
    assert "--config /etc/ble-sensors-mqtt/config.toml" in unit
    assert "systemd_launcher.py" not in unit
    assert (ROOT / "config/app.example.toml").is_file()


def test_deployment_assets() -> None:
    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker/docker-compose.yml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    deployment = (ROOT / "kubernetes/deployment.yaml").read_text(encoding="utf-8")
    k8s_config = (ROOT / "kubernetes/configmap.yaml").read_text(encoding="utf-8")
    docker_env = (ROOT / "docker/.env.example").read_text(encoding="utf-8")

    assert "EXPOSE 8080/tcp 9105/tcp 1161/udp" in dockerfile
    assert "desalvo/ble-sensors-mqtt:1.0.0" in compose
    assert "linux/amd64,linux/arm64" in workflow
    assert "/run/dbus" in deployment
    assert "DBUS_SYSTEM_BUS_ADDRESS" in deployment
    assert "readOnlyRootFilesystem: true" in deployment
    assert "MQTT_CACHE_MAX_SIZE" in k8s_config
    assert "MQTT_CACHE_PATH" in docker_env
    assert "FRONTEND_ENABLED" in k8s_config
    assert "containerPort: 8080" in deployment
    assert (ROOT / "kubernetes/service-frontend-external.yaml").is_file()
    assert (ROOT / "src/ble_sensors_mqtt/frontend.py").is_file()
    assert (ROOT / "src/ble_sensors_mqtt/web_static/app.css").is_file()
    assert (ROOT / "scripts/install-from-github.sh").is_file()
    assert (ROOT / "scripts/check-bluetooth-host.sh").is_file()
    assert (ROOT / "kubernetes/bluetooth-test-pod.yaml").is_file()


def test_cross_platform_host_and_native_release_assets() -> None:
    workflow = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    hosts_en = (ROOT / "docs/HOSTS.en.md").read_text(encoding="utf-8")
    hosts_it = (ROOT / "docs/HOSTS.it.md").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "windows-2025" in workflow
    assert "macos-26" in workflow
    assert "macos-26-intel" in workflow
    assert "scripts/build-native-package.py" in workflow
    assert "Windows 11" in hosts_en
    assert "macOS Tahoe" in hosts_en
    assert "x86_64" in hosts_en and "arm64" in hosts_en
    assert "Windows 11" in hosts_it
    assert "Rocky Linux" in hosts_it
    assert 'Operating System :: Microsoft :: Windows :: Windows 11' in pyproject
    assert 'Operating System :: MacOS :: MacOS X' in pyproject
    assert (ROOT / "scripts/build-native-package.py").is_file()
    assert (ROOT / "scripts/install-native-optionals.py").is_file()
    native_builder = (ROOT / "scripts/build-native-package.py").read_text(encoding="utf-8")
    assert "Inno Setup" in native_builder
    assert "productbuild" in native_builder
    assert "ble-sensors-mqtt-settings" in native_builder
    assert "ble-sensors-mqtt-service" in native_builder
    assert "native-dist/*.exe" in workflow
    assert "native-dist/*.pkg" in workflow
    assert (ROOT / "src/ble_sensors_mqtt/config_gui.py").is_file()
    assert (ROOT / "src/ble_sensors_mqtt/windows_service.py").is_file()
    assert (ROOT / "docs/NATIVE-INSTALLERS.en.md").is_file()
    assert (ROOT / "docs/CONFIGURATION.en.md").is_file()


def test_dependency_constraints_allow_current_bthome_cryptography():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "cryptography>=49,<51" in project
    assert "cryptography>=45,<47" not in project


def test_release_check_bootstraps_required_tooling():
    script = (ROOT / "scripts" / "release-check.sh").read_text(encoding="utf-8")
    assert ".[all,dev,release]" in script
    assert "BLE_SENSORS_RELEASE_SKIP_BOOTSTRAP" in script


def test_systemd_installer_exposes_component_selection():
    script = (ROOT / "scripts" / "install-systemd.sh").read_text(encoding="utf-8")
    for option in ("--with-sensors", "--without-sensors", "--with-cloud", "--without-cloud", "--with-web", "--without-web"):
        assert option in script
    assert "Select optional software components to install:" in script
