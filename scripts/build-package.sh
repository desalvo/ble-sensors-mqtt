#!/bin/sh
set -eu
root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 "$root_dir/scripts/build-manuals.py"
python3 "$root_dir/scripts/build-project-archives.py"
