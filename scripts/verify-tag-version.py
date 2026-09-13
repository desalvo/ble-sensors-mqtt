#!/usr/bin/env python3
"""Verify GITHUB_REF_NAME matches VERSION for cross-platform release jobs."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tag = os.environ.get("GITHUB_REF_NAME", "")
version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
if tag != f"v{version}":
    raise SystemExit(f"tag {tag!r} != v{version}")
print(f"release tag verified: {tag}")
