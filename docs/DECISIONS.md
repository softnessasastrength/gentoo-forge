# Installation decisions

## Confirmed

- Target: dedicated SSD (device identifier not yet selected)
- Hardware: AMD Ryzen 5 4500 / Radeon RX 6600 XT
- Firmware: UEFI
- Partition table: GPT
- Root filesystem: Btrfs
- Partition layout: three GPT partitions, EFI System Partition (proposed 1 GiB) + dedicated Linux swap (proposed 20 GiB) + Btrfs root (remaining space)
- Installed RAM: 16 GiB
- Hibernation: enabled (resume support must be configured and tested)
- Disk encryption: none (explicit choice; root and hibernation swap unencrypted)
- Snapshot manager: Snapper with automatic timeline snapshots and cleanup
- Root snapshot retention: 6 hourly, 7 daily, 4 weekly, 3 monthly, 0 yearly; up to 10 pre/post update pairs
- Home snapshot policy: independent automatic Snapper snapshots for /home (separate subvolume and configuration; retention initially same as root, subject to validation)
- Rollback approach: GRUB boot-menu snapshot recovery integration (implementation and boot artifact consistency to be tested)
- Unlocking method / LUKS recovery keys: not applicable

## Pending

- Partition sizes and Btrfs subvolumes
- Swap capacity: 20 GiB recommended, awaiting confirmation
- Validate snapshot retention implementation, home-specific retention, and GRUB rollback integration

No partitioning or formatting is authorized by this document. All disk writes remain disabled.
