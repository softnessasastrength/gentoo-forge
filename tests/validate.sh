#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
for f in ./*.sh scripts/*.sh tests/*.sh; do bash -n "$f"; done
if command -v shellcheck >/dev/null; then shellcheck ./*.sh scripts/*.sh tests/*.sh; else echo 'shellcheck unavailable; syntax validation only'; fi
if grep -REn '(^|[[:space:]])(mkfs\.|wipefs|sgdisk|parted|dd[[:space:]])' scripts/; then echo 'Destructive command detected in foundation scripts' >&2; exit 1; fi
echo 'Validation passed.'
