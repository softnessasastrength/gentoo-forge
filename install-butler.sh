#!/usr/bin/env bash
# Stage the permanent executable into an explicitly selected target filesystem.
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT_DIR/SHA256SUMS" ]]; then
  (cd "$ROOT_DIR" && sha256sum --check --quiet SHA256SUMS)
fi
if [[ -x "$ROOT_DIR/python/bin/python3" ]]; then
  exec "$ROOT_DIR/python/bin/python3" "$ROOT_DIR/tools/install_butler.py" "$@"
fi
exec python3 "$ROOT_DIR/tools/install_butler.py" "$@"
