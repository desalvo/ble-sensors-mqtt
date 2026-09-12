#!/bin/sh
set -eu
root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root_dir"

python3 -m compileall -q src tests scripts
ruff check .
pytest --cov=ble_sensors_mqtt --cov-report=term-missing
bandit -c pyproject.toml -r src
pip-audit
python3 scripts/build-manuals.py
rm -rf dist build ./*.egg-info
python3 -m build
python3 -m twine check dist/*
pip-audit --format cyclonedx-json --output dist/ble-sensors-mqtt-sbom.cdx.json
find . -type d -name __pycache__ -prune -exec rm -rf {} +
rm -rf .pytest_cache .ruff_cache
python3 scripts/verify-release.py
