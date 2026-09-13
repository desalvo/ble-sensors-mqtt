#!/usr/bin/env python3
"""Build native portable bundles plus standard Windows/macOS installers."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
MODULES = (
    "bleak", "paho", "switchbot", "xiaomi_ble", "govee_ble", "inkbird_ble", "thermopro_ble",
    "qingping_ble", "bthome_ble", "sensorpush_ble", "mopeka_iot_ble",
    "ruuvitag_sensor", "airthings_ble", "tinytuya", "habluetooth",
    "home_assistant_bluetooth", "flask", "authlib", "ldap3", "cryptography",
)


def default_suffix() -> str:
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("x86-64", "x86_64")
    if sys.platform == "win32":
        return f"windows-{machine}"
    if sys.platform == "darwin":
        return f"macos-tahoe-{machine}"
    return f"{sys.platform}-{machine}"


def run(command: list[str], **kwargs) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True, **kwargs)


def collect_args() -> list[str]:
    result = ["--copy-metadata", "ble-sensors-mqtt", "--collect-all", "ble_sensors_mqtt"]
    distributions = importlib.metadata.packages_distributions()
    copied = {"ble-sensors-mqtt"}
    for module in MODULES:
        if importlib.util.find_spec(module) is None:
            continue
        result += ["--collect-all", module]
        for distribution in distributions.get(module, []):
            if distribution not in copied:
                result += ["--recursive-copy-metadata", distribution]
                copied.add(distribution)
    return result


def pyinstaller(script: Path, name: str, dist: Path, work: Path, *, windowed=False, onefile=False, extras=None) -> Path:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile" if onefile else "--onedir",
        "--windowed" if windowed else "--console",
        "--name", name,
        "--distpath", str(dist), "--workpath", str(work / name), "--specpath", str(work / name),
    ]
    command += collect_args() if script.name == "frozen_entry.py" else []
    if extras:
        command += extras
    command.append(str(script))
    run(command, cwd=ROOT)
    if sys.platform == "win32":
        return dist / (f"{name}.exe" if onefile else name)
    if windowed:
        return dist / f"{name}.app"
    return dist / name


def checksum(path: Path) -> Path:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    out = path.with_suffix(path.suffix + ".sha256")
    out.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    return out


def portable(runtime_dir: Path, output_dir: Path, suffix: str) -> Path:
    stage = ROOT / "build" / "portable-stage" / "ble-sensors-mqtt"
    shutil.rmtree(stage.parent, ignore_errors=True)
    shutil.copytree(runtime_dir, stage)
    for source in (ROOT / "README.md", ROOT / "README.it.md", ROOT / "LICENSE", ROOT / "config" / "app.example.toml"):
        shutil.copy2(source, stage / source.name)
    docs = stage / "docs"
    docs.mkdir(exist_ok=True)
    for name in ("HOSTS.en.md", "HOSTS.it.md", "USAGE.en.md", "USAGE.it.md", "FRONTEND.en.md", "FRONTEND.it.md", "BLE-SENSORS-MQTT-MIB.txt"):
        source = ROOT / "docs" / name
        if source.exists():
            shutil.copy2(source, docs / name)
    base = output_dir / f"ble-sensors-mqtt-v{VERSION}-{suffix}-portable"
    return Path(shutil.make_archive(str(base), "zip", root_dir=stage.parent, base_dir=stage.name))


def windows_installer(runtime_dir: Path, tools: Path, output_dir: Path, suffix: str) -> Path:
    settings = pyinstaller(
        ROOT / "scripts" / "config_gui_entry.py", "ble-sensors-mqtt-settings", tools,
        ROOT / "build" / "native-work", windowed=True, onefile=True,
    )
    service = pyinstaller(
        ROOT / "scripts" / "windows_service_entry.py", "ble-sensors-mqtt-service", tools,
        ROOT / "build" / "native-work", onefile=True,
        extras=["--hidden-import", "win32timezone", "--collect-all", "win32serviceutil"],
    )

    generated = ROOT / "build" / "installer"
    generated.mkdir(parents=True, exist_ok=True)
    cfg = (ROOT / "config" / "app.example.toml").read_text(encoding="utf-8")
    cfg = cfg.replace('state_file = ""', 'state_file = "C:\\\\ProgramData\\\\ble-sensors-mqtt\\\\state.json"')
    cfg = cfg.replace('path = ""\nmax_size = "1GiB"', 'path = "C:\\\\ProgramData\\\\ble-sensors-mqtt\\\\mqtt-cache.sqlite3"\nmax_size = "1GiB"', 1)
    windows_cfg = generated / "config.windows.toml"
    windows_cfg.write_text(cfg, encoding="utf-8")

    iss = generated / "ble-sensors-mqtt.iss"
    app_dir = str(runtime_dir).replace("\\", "\\\\")
    settings_s = str(settings).replace("\\", "\\\\")
    service_s = str(service).replace("\\", "\\\\")
    cfg_s = str(windows_cfg).replace("\\", "\\\\")
    out_s = str(output_dir).replace("\\", "\\\\")
    iss.write_text(f'''[Setup]\nAppId={{{{8D5E9C02-CE41-4AF6-BB11-C97E571E0E51}}}}\nAppName=ble-sensors-mqtt\nAppVersion={VERSION}\nAppPublisher=Alessandro De Salvo\nDefaultDirName={{autopf}}\\ble-sensors-mqtt\nDefaultGroupName=ble-sensors-mqtt\nOutputDir={out_s}\nOutputBaseFilename=ble-sensors-mqtt-v{VERSION}-{suffix}-setup\nCompression=lzma2\nSolidCompression=yes\nPrivilegesRequired=admin\nArchitecturesAllowed=x64compatible\nArchitecturesInstallIn64BitMode=x64compatible\nUninstallDisplayName=ble-sensors-mqtt\n\n[Types]\nName: \"full\"; Description: \"Full installation\"\nName: \"compact\"; Description: \"Core service only\"\nName: \"custom\"; Description: \"Custom installation\"; Flags: iscustom\n\n[Components]\nName: \"core\"; Description: \"Core runtime (required)\"; Types: full compact custom; Flags: fixed\nName: \"service\"; Description: \"Windows background service\"; Types: full compact\nName: \"settings\"; Description: \"Graphical Settings application\"; Types: full\n\n[Dirs]\nName: "{{commonappdata}}\\ble-sensors-mqtt"\n\n[Files]\nSource: "{app_dir}\\*"; DestDir: "{{app}}\\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs\nSource: "{settings_s}"; DestDir: "{{app}}"; Components: settings; Flags: ignoreversion\nSource: "{service_s}"; DestDir: "{{app}}"; Components: service; Flags: ignoreversion\nSource: "{cfg_s}"; DestDir: "{{commonappdata}}\\ble-sensors-mqtt"; DestName: "config.toml"; Flags: onlyifdoesntexist uninsneveruninstall\n\n[Icons]\nName: "{{group}}\\ble-sensors-mqtt Settings"; Filename: "{{app}}\\ble-sensors-mqtt-settings.exe"; Components: settings\nName: "{{group}}\\Open configuration folder"; Filename: "{{sys}}\\explorer.exe"; Parameters: "{{commonappdata}}\\ble-sensors-mqtt"\n\n[Run]\nFilename: "{{app}}\\ble-sensors-mqtt-service.exe"; Parameters: "--startup=auto install"; Components: service; Flags: runhidden waituntilterminated\nFilename: "{{app}}\\ble-sensors-mqtt-settings.exe"; Description: "Configure ble-sensors-mqtt"; Components: settings; Flags: postinstall nowait skipifsilent\n\n[UninstallRun]\nFilename: "{{app}}\\ble-sensors-mqtt-service.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"\nFilename: "{{app}}\\ble-sensors-mqtt-service.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"\n''', encoding="utf-8")
    iscc = shutil.which("ISCC.exe") or shutil.which("iscc")
    if not iscc:
        for candidate in (
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
        ):
            if candidate.exists():
                iscc = str(candidate)
                break
    if not iscc:
        raise SystemExit("Inno Setup compiler (ISCC) is required on the Windows runner")
    run([iscc, str(iss)], cwd=ROOT)
    return output_dir / f"ble-sensors-mqtt-v{VERSION}-{suffix}-setup.exe"


def macos_installer(runtime_dir: Path, tools: Path, output_dir: Path, suffix: str) -> Path:
    settings_app = pyinstaller(
        ROOT / "scripts" / "config_gui_entry.py", "ble-sensors-mqtt Settings", tools,
        ROOT / "build" / "native-work", windowed=True, onefile=False,
    )
    build = ROOT / "build"
    core_root = build / "macos-core-root"
    settings_root = build / "macos-settings-root"
    for root in (core_root, settings_root):
        shutil.rmtree(root, ignore_errors=True)

    runtime_target = core_root / "Library" / "Application Support" / "ble-sensors-mqtt" / "runtime"
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(runtime_dir, runtime_target)
    docs_target = core_root / "Library" / "Application Support" / "ble-sensors-mqtt" / "docs"
    docs_target.mkdir(parents=True, exist_ok=True)
    for name in ("HOSTS.en.md", "HOSTS.it.md", "USAGE.en.md", "USAGE.it.md", "FRONTEND.en.md", "FRONTEND.it.md", "BLE-SENSORS-MQTT-MIB.txt"):
        source = ROOT / "docs" / name
        if source.exists():
            shutil.copy2(source, docs_target / name)

    applications = settings_root / "Applications"
    applications.mkdir(parents=True, exist_ok=True)
    shutil.copytree(settings_app, applications / settings_app.name)

    core_pkg = build / "ble-sensors-mqtt-core.pkg"
    settings_pkg = build / "ble-sensors-mqtt-settings.pkg"
    run(["pkgbuild", "--root", str(core_root), "--identifier", "com.desalvo.ble-sensors-mqtt.core",
         "--version", VERSION, "--install-location", "/", str(core_pkg)])
    run(["pkgbuild", "--root", str(settings_root), "--identifier", "com.desalvo.ble-sensors-mqtt.settings",
         "--version", VERSION, "--install-location", "/", str(settings_pkg)])

    distribution = build / "Distribution.xml"
    distribution.write_text(f'''<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>ble-sensors-mqtt {VERSION}</title>
  <options customize="always" require-scripts="false" rootVolumeOnly="true"/>
  <choices-outline>
    <line choice="core"/>
    <line choice="settings"/>
  </choices-outline>
  <choice id="core" title="Core runtime" description="Required BLE/MQTT runtime." enabled="false" selected="true">
    <pkg-ref id="com.desalvo.ble-sensors-mqtt.core"/>
  </choice>
  <choice id="settings" title="Graphical Settings" description="Optional graphical configuration and LaunchAgent management." selected="true">
    <pkg-ref id="com.desalvo.ble-sensors-mqtt.settings"/>
  </choice>
  <pkg-ref id="com.desalvo.ble-sensors-mqtt.core" version="{VERSION}">{core_pkg.name}</pkg-ref>
  <pkg-ref id="com.desalvo.ble-sensors-mqtt.settings" version="{VERSION}">{settings_pkg.name}</pkg-ref>
</installer-gui-script>
''', encoding="utf-8")
    installer = output_dir / f"ble-sensors-mqtt-v{VERSION}-{suffix}.pkg"
    run(["productbuild", "--distribution", str(distribution), "--package-path", str(build), str(installer)])
    return installer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-suffix", default=default_suffix())
    parser.add_argument("--output-dir", type=Path, default=ROOT / "native-dist")
    args = parser.parse_args()
    if sys.platform not in {"win32", "darwin"}:
        raise SystemExit("native package build is intended for Windows or macOS runners")

    work = ROOT / "build" / "native-work"
    dist = ROOT / "build" / "native-dist"
    tools = ROOT / "build" / "native-tools"
    for directory in (work, dist, tools):
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    runtime_dir = pyinstaller(ROOT / "scripts" / "frozen_entry.py", "ble-sensors-mqtt", dist, work)
    executable = runtime_dir / ("ble-sensors-mqtt.exe" if sys.platform == "win32" else "ble-sensors-mqtt")
    run([str(executable), "--version"])
    run([str(executable), "--list-plugins"])

    artifacts = [portable(runtime_dir, args.output_dir, args.artifact_suffix)]
    if sys.platform == "win32":
        artifacts.append(windows_installer(runtime_dir, tools, args.output_dir, args.artifact_suffix))
    else:
        artifacts.append(macos_installer(runtime_dir, tools, args.output_dir, args.artifact_suffix))
    for artifact in artifacts:
        checksum(artifact)
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
