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
- Unlocking method / LUKS recovery keys: not applicable

## Pending

- Partition sizes and Btrfs subvolumes
- Swap capacity: 20 GiB recommended, awaiting confirmation
- Snapshot tooling and retention

No partitioning or formatting is authorized by this document. All disk writes remain disabled.
