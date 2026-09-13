#!/bin/sh
set -eu
root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root_dir"

# Make manual release checks reproducible outside CI as well. The CI already
# installs these extras, so pip normally reports them as satisfied. Set
# BLE_SENSORS_RELEASE_SKIP_BOOTSTRAP=1 only when the environment was prepared
# explicitly/offline.
if [ "${BLE_SENSORS_RELEASE_SKIP_BOOTSTRAP:-0}" != 1 ]; then
  python3 -m pip install --upgrade pip 'setuptools>=83' wheel
  python3 -m pip install --upgrade '.[all,dev,release]'
fi

python3 -m compileall -q src tests scripts
python3 -m ruff check .
python3 -m pytest --cov=ble_sensors_mqtt --cov-report=term-missing
python3 -m bandit -c pyproject.toml -r src
python3 -m pip_audit
python3 scripts/build-manuals.py
rm -rf dist build ./*.egg-info
python3 -m build
python3 -m twine check dist/*
python3 -m pip_audit --format cyclonedx-json --output dist/ble-sensors-mqtt-sbom.cdx.json
find . -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache .ruff_cache
python3 scripts/verify-release.py
