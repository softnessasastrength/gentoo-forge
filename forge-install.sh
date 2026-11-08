#!/usr/bin/env bash
# Gentoo live-CD root helper, deliberately separate from FORGEWORTH conversation.
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT_DIR/SHA256SUMS" ]]; then
  (cd "$ROOT_DIR" && sha256sum --check --quiet SHA256SUMS)
fi
cd "$ROOT_DIR"
if [[ -x "$ROOT_DIR/python/bin/python3" ]]; then
  exec "$ROOT_DIR/python/bin/python3" -m installer.storage "$@"
fi
exec python3 -m installer.storage "$@"
