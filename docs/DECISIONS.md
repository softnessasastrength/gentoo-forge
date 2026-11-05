# Installation decisions

## Confirmed

- Target: dedicated SSD (device identifier not yet selected)
- Hardware: AMD Ryzen 5 4500 / Radeon RX 6600 XT
- Init system: OpenRC
- Compiler: GCC (LLVM available separately)
- CPU optimization: -march=znver2 -O2 -pipe
- Build parallelism: MAKEOPTS="-j6 -l6"
- USE flags: profile defaults with targeted package.use overrides
- Graphics: kernel amdgpu, Mesa RADV, Wayland primary, XWayland compatibility; Mesa VIDEO_CARDS=radeonsi (validated against package metadata)
- Audio: PipeWire (WirePlumber session manager planned)
- Multimedia: full codec support and VA-API hardware acceleration
- Gaming: Steam, Proton, Wine, GameMode, and 32-bit graphics/Vulkan compatibility
- Graphics package flags: Mesa vulkan vaapi wayland X and ABI_X86=32,64 verified in current package metadata; actual package.use must be tested against resolved profile
- Stage 3: standard amd64 OpenRC, multilib
- Intended profile: desktop/Plasma/OpenRC (resolve exact profile path against installed Gentoo profile tree)
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


- Primary kernel: source-built sys-kernel/gentoo-kernel (distribution kernel configuration)
- Recovery kernel: retain precompiled sys-kernel/gentoo-kernel-bin as fallback; preserve known-good kernel/initramfs/GRUB entry across updates
- Kernel boot integration: initramfs generator, swap resume UUID, kernel update policy, and GRUB snapshot integration pending explicit decisions

## Pending

- Validate package-specific USE flags against current Gentoo tree at install time; no unverified flags committed

- Verify exact Plasma/OpenRC profile path and Stage 3 release metadata before bootstrap

- Partition sizes and Btrfs subvolumes
- Swap capacity: 20 GiB recommended, awaiting confirmation
- Validate snapshot retention implementation, home-specific retention, and GRUB rollback integration

No partitioning or formatting is authorized by this document. All disk writes remain disabled.
