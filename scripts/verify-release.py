#!/usr/bin/env python3
"""Fail closed on common release-package mistakes."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def fail(message: str) -> None:
    print(f"release verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


if not re.fullmatch(r"\d+\.\d+\.\d+", VERSION):
    fail(f"VERSION is not semantic x.y.z: {VERSION!r}")

pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
if f'version = "{VERSION}"' not in pyproject:
    fail("VERSION and pyproject.toml disagree")

for language in ("en", "it"):
    pdf = ROOT / "docs" / f"ble-sensors-mqtt-manual-v{VERSION}-{language}.pdf"
    if not pdf.is_file() or pdf.stat().st_size < 10_000:
        fail(f"missing or suspicious manual: {pdf.name}")

FORBIDDEN_RELEASE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", ".git"}
FORBIDDEN_RELEASE_SUFFIXES = {".pyc", ".pyo"}


def verify_member_names(names: list[str], artifact_name: str) -> None:
    for name in names:
        parts = Path(name).parts
        if any(part in FORBIDDEN_RELEASE_PARTS for part in parts):
            fail(f"development artifact present in {artifact_name}: {name}")
        if Path(name).suffix in FORBIDDEN_RELEASE_SUFFIXES:
            fail(f"development artifact present in {artifact_name}: {name}")


wheels = list((ROOT / "dist").glob("*.whl"))
sdists = list((ROOT / "dist").glob("*.tar.gz"))
if len(wheels) != 1 or len(sdists) != 1:
    fail("exactly one wheel and one sdist are required")

with zipfile.ZipFile(wheels[0]) as archive:
    names = archive.namelist()
    verify_member_names(names, wheels[0].name)
    if not any(name.endswith("ble_sensors_mqtt/cli.py") for name in names):
        fail("wheel does not contain the application package")
    metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
    if len(metadata_names) != 1:
        fail("wheel must contain exactly one METADATA file")
    metadata = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
    if metadata.get("Name") != "ble-sensors-mqtt":
        fail("wheel metadata has the wrong project name")
    if metadata.get("Version") != VERSION:
        fail("wheel metadata version disagrees with VERSION")
    if metadata.get("Requires-Python") != ">=3.11":
        fail("wheel metadata Requires-Python must be >=3.11")
    requirements = metadata.get_all("Requires-Dist", [])
    for direct in ("bleak", "paho-mqtt", "PySwitchbot"):
        if not any(req.lower().startswith(direct.lower()) for req in requirements):
            fail(f"wheel metadata is missing direct dependency: {direct}")


with tarfile.open(sdists[0], "r:gz") as archive:
    verify_member_names(archive.getnames(), sdists[0].name)

manifest = {}
for artifact in sorted(wheels + sdists):
    manifest[artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
(ROOT / "dist" / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("release verification passed")
