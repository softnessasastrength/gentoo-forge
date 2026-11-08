#!/usr/bin/env bash
# Build a portable folder; does not flash a USB device or install host packages.
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
  PYTHON_BIN=python3
fi
exec "$PYTHON_BIN" "$ROOT_DIR/tools/build_livecd.py" "$@"
