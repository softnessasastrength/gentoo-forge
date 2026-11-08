#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${1:-$ROOT_DIR/config/hardware.env}"
[[ -f "$CONFIG" ]] || { echo "Copy config/hardware.env.example to config/hardware.env first" >&2; exit 1; }
# Only accept declarative KEY=VALUE assignments; do not source untrusted shell input.
disk="$(sed -nE 's/^TARGET_DISK="?([^"#]*)"?$/\1/p' "$CONFIG" | head -n1)"
[[ -n "$disk" ]] || { echo 'TARGET_DISK unset; no action taken' >&2; exit 1; }
[[ -b "$disk" ]] || { echo "Not a block device: $disk" >&2; exit 1; }
[[ "$(lsblk -dn -o TYPE "$disk")" == disk ]] || { echo 'Target must be a whole disk' >&2; exit 1; }
if lsblk -nr -o MOUNTPOINTS "$disk" | grep -q '[^[:space:]]'; then echo 'Target or child partition is mounted; refusing' >&2; exit 1; fi
printf 'PLAN ONLY (no writes)\nTarget: %s\n' "$disk"
lsblk -o NAME,PATH,SIZE,FSTYPE,MOUNTPOINTS,MODEL "$disk"
printf '\nProposed GPT/UEFI layout: 1 GiB EFI + 20 GiB swap + remaining Btrfs.\nIndependent root/home snapshots; hibernation and rollback require boot verification.\n'
printf 'Partitioning, formatting and installation are NOT implemented in this milestone.\n'
