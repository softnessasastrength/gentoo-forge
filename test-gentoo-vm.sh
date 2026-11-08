#!/usr/bin/env bash
# Run on a sufficiently resourced PC/CI runner, not the OOM-limited Chromebook.
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  exec "$ROOT_DIR/.venv/bin/python" -m tools.gentoo_vm "$@"
fi
exec python3 -m tools.gentoo_vm "$@"
