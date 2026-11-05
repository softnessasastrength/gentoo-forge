#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
command -v lsblk >/dev/null || { echo 'ERROR: lsblk missing' >&2; exit 1; }
command -v findmnt >/dev/null || { echo 'ERROR: findmnt missing' >&2; exit 1; }
echo 'gentoo-forge: READ-ONLY preflight'
echo 'CPU:'; grep -m1 'model name' /proc/cpuinfo || true
echo 'Graphics:'; if command -v lspci >/dev/null; then lspci | grep -Ei 'VGA|Display|3D' || true; else echo 'lspci not installed'; fi
echo 'Firmware:'; if [[ -d /sys/firmware/efi ]]; then echo UEFI; else echo 'Legacy BIOS or container'; fi
echo 'Disks (read-only):'; lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL
echo 'No changes were made.'
