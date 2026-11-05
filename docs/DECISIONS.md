# Installation decisions

## Confirmed

- Target: dedicated SSD (device identifier not yet selected)
- Hardware: AMD Ryzen 5 4500 / Radeon RX 6600 XT
- Firmware: UEFI
- Partition table: GPT
- Root filesystem: Btrfs

## Pending

- Partition layout and Btrfs subvolumes
- Swap strategy and capacity
- Hibernation
- LUKS encryption
- Snapshot tooling and retention

No partitioning or formatting is authorized by this document. All disk writes remain disabled.
