#!/usr/bin/env python3
"""Best-effort install of optional sensor/cloud dependencies for native bundles."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
requirements = data["project"]["optional-dependencies"]["all"]
failed: list[str] = []
for requirement in requirements:
    print(f"::group::optional dependency {requirement}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", requirement],
        check=False,
    )
    print("::endgroup::")
    if result.returncode:
        failed.append(requirement)

if failed:
    print("Optional dependencies unavailable on this platform:")
    for item in failed:
        print(f"  - {item}")
else:
    print("All optional sensor/cloud dependencies installed.")
