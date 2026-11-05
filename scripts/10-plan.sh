#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${1:-$ROOT_DIR/config/hardware.env}"
GIB=1073741824
EFI_GIB=1
SWAP_GIB=20
MIN_ROOT_GIB=8
# Conservative accounting reserve; actual GPT boundaries/alignment require implementation review.
RESERVE_GIB=1
layout() {
  local bytes="$1" required_gib=$((EFI_GIB + SWAP_GIB + MIN_ROOT_GIB + RESERVE_GIB))
  [[ "$bytes" =~ ^[0-9]+$ ]] || { echo 'ERROR: disk size must be an integer number of bytes' >&2; return 1; }
  (( ${#bytes} < 19 )) || { echo 'ERROR: disk size too large for safe shell arithmetic' >&2; return 1; }
  (( bytes >= required_gib * GIB )) || { echo "ERROR: target must be at least ${required_gib} GiB for the proposed layout" >&2; return 1; }
  printf 'READ-ONLY LAYOUT ESTIMATE (no partition writes)\n'
  printf 'Partition table: GPT; firmware: UEFI\n'
  printf '1: EFI System Partition: %s GiB\n' "$EFI_GIB"
  printf '2: Linux swap partition: %s GiB (hibernation)\n' "$SWAP_GIB"
  printf '3: Btrfs root: remaining capacity (estimated usable: %s GiB or more)\n' "$((bytes / GIB - EFI_GIB - SWAP_GIB - RESERVE_GIB))"
  printf 'Reserve: up to %s GiB for alignment/GPT and capacity rounding; boundaries NOT finalized.\n' "$RESERVE_GIB"
  printf 'No partitioning, formatting, or installation is implemented.\n'
}
# Explicit synthetic-only test interface. No disk discovery and no writes.
if [[ "${1:-}" == --layout-bytes ]]; then
  [[ $# -eq 2 ]] || { echo 'Usage: 10-plan.sh --layout-bytes INTEGER' >&2; exit 2; }
  layout "$2"
  exit
fi
[[ -f "$CONFIG" ]] || { echo 'Copy config/hardware.env.example to config/hardware.env first' >&2; exit 1; }
# Parse declarative config without sourcing shell code.
disk="$(sed -nE 's/^TARGET_DISK="([^"]*)"$/\1/p' "$CONFIG" | head -n1)"
[[ -n "$disk" ]] || { echo 'TARGET_DISK unset; no action taken' >&2; exit 1; }
[[ -b "$disk" ]] || { echo "Not a block device: $disk" >&2; exit 1; }
[[ "$(lsblk -dn -o TYPE "$disk")" == disk ]] || { echo 'Target must be a whole disk' >&2; exit 1; }
if lsblk -nr -o MOUNTPOINTS "$disk" | grep -q '[^[:space:]]'; then
  echo 'Target or child partition is mounted; refusing' >&2; exit 1
fi
printf 'PLAN ONLY (no writes)\nTarget: %s\n' "$disk"
lsblk -o NAME,PATH,SIZE,FSTYPE,MOUNTPOINTS,MODEL "$disk"
bytes="$(lsblk -bdn -o SIZE "$disk")"
layout "$bytes"
