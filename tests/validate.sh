#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
for f in scripts/*.sh tests/*.sh; do bash -n "$f"; done
if command -v shellcheck >/dev/null; then shellcheck scripts/*.sh tests/*.sh; else echo 'shellcheck unavailable; syntax validation only'; fi
if grep -REn '(^|[[:space:]])(mkfs\.|wipefs|sgdisk|parted|dd[[:space:]])' scripts/; then
  echo 'Destructive command detected in foundation scripts' >&2; exit 1
fi
planner="scripts/10-plan.sh"
output="$(bash "$planner" --layout-bytes 107374182400)"
grep -Fq 'Partition table: GPT; firmware: UEFI' <<< "$output"
grep -Fq 'EFI System Partition: 1 GiB' <<< "$output"
grep -Fq 'Linux swap partition: 20 GiB' <<< "$output"
grep -Fq 'Btrfs root: remaining capacity (estimated usable: 78 GiB or more)' <<< "$output"
if bash "$planner" --layout-bytes 31138512896 >/dev/null 2>&1; then
  echo 'Planner accepted undersized disk' >&2; exit 1
fi
if bash "$planner" --layout-bytes not-a-number >/dev/null 2>&1; then
  echo 'Planner accepted invalid capacity' >&2; exit 1
fi
echo 'Validation passed (static checks and synthetic read-only layout tests).'
