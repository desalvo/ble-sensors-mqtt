from __future__ import annotations

import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = runpy.run_path(str(ROOT / "scripts/systemd_launcher.py"))
load_arguments = cast(Callable[[Path], list[str]], LAUNCHER["load_arguments"])


def test_systemd_example_arguments_are_valid(tmp_path: Path) -> None:
    assert load_arguments(ROOT / "config/systemd-args.example.json")[:2] == [
        "--mqtt-host",
        "mqtt.example.net",
    ]

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_arguments(bad)


def test_deployment_assets() -> None:
    dockerfile = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker/docker-compose.yml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    deployment = (ROOT / "kubernetes/deployment.yaml").read_text(encoding="utf-8")

    assert "EXPOSE 9105/tcp 1161/udp" in dockerfile
    assert "desalvo/ble-sensors-mqtt:1.0.0" in compose
    assert "linux/amd64,linux/arm64" in workflow
    assert "/run/dbus" in deployment
    assert "DBUS_SYSTEM_BUS_ADDRESS" in deployment
    assert "readOnlyRootFilesystem: true" in deployment
    assert (ROOT / "scripts/install-from-github.sh").is_file()
    assert (ROOT / "scripts/check-bluetooth-host.sh").is_file()
    assert (ROOT / "kubernetes/bluetooth-test-pod.yaml").is_file()
