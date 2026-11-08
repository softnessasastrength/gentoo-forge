#!/usr/bin/env bash
# Debian/Crostini development dependencies; never touches block devices.
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == --help ]]; then
  echo 'Usage: bash setup-dev.sh [--python-only]'
  echo 'Default: install Debian packages, create .venv, install pinned UI dependencies.'
  echo '--python-only: skip apt and use existing Python/venv support.'
  exit 0
fi
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --python-only ) ]]; then
  echo 'Unknown option; use --help.' >&2; exit 2
fi
if [[ $EUID -eq 0 ]]; then
  echo 'Run as your ordinary user; the script uses sudo only for apt.' >&2; exit 1
fi
if [[ "${1:-}" != --python-only ]]; then
  command -v apt-get >/dev/null || { echo 'Requires Debian/Ubuntu apt-get; use --python-only elsewhere.' >&2; exit 1; }
  sudo apt-get update
  sudo apt-get install --no-install-recommends python3-venv qemu-system-x86 qemu-utils ovmf gpgv shellcheck
fi
python3 -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/python" -m pip install -r "$ROOT_DIR/tui/requirements.txt"
echo 'Ready. Launch with .venv/bin/python -m tui.app from the repository root.'
echo 'Optional isolated firmware check: .venv/bin/python -m tui.qemu'
