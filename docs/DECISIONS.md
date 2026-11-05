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
- Partition layout: three GPT partitions, EFI System Partition (confirmed 1 GiB) + dedicated Linux swap (confirmed 20 GiB) + Btrfs root (remaining space)
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


- Initramfs: Dracut (verify Gentoo installkernel integration and resume module before implementation)
- Hibernation resume: dedicated swap partition via verified UUID; never hardcode a guessed UUID
- Kernel updates: conservative; retain tested primary kernel, matching modules/initramfs, and precompiled fallback kernel
- GRUB recovery: Btrfs snapshot boot-menu integration plus manual recovery path; verify boot artifacts and avoid stale hibernation resume on rollback


- Secure Boot: disabled (explicit choice; no signing enforcement)
- Firmware policy: Portage-managed firmware and microcode package updates; not unattended firmware flashing
- CPU microcode: AMD microcode with early loading, verify Dracut and kernel integration
- GPU firmware: AMDGPU firmware appropriate for Radeon RX 6600 XT, verify initramfs inclusion where necessary
- Bootloader: GRUB x86-64 UEFI with primary, fallback, and validated Btrfs snapshot recovery entries


- Network management: NetworkManager on OpenRC (enable NetworkManager in default runlevel; avoid competing interface managers)
- Hostname: forge
- Default locale: en_US.UTF-8
- Timezone: America/New_York
- Hardware clock: UTC
- Validation pending: verify installed OpenRC NetworkManager service name, dependencies, and runtime operation before enabling installer logic


- Regular user: branden (unprivileged desktop account)
- Privilege elevation: sudo with wheel-group authorization and password authentication; no NOPASSWD default
- Root account: password-enabled for recovery; password supplied securely at install time, never stored in repository or logs
- Security baseline: nftables inbound firewall policy, SSH server disabled by default, manually approved system updates
- Login manager: SDDM for KDE Plasma; verify OpenRC display-manager service and Wayland compatibility
- Secrets policy: never commit passwords, hashes, tokens, or recovery secrets; prompt securely during authorized installation

- Installation target policy: dedicated SSD is disposable; clean-install workflow may erase it only after live device identity verification, full plan review, and explicit per-device confirmation. No current authorization to execute disk writes.

## Pending

- Validate package-specific USE flags against current Gentoo tree at install time; no unverified flags committed

- Verify exact Plasma/OpenRC profile path and Stage 3 release metadata before bootstrap

- Btrfs subvolume implementation and exact partition boundaries (account for GPT metadata and alignment)
- Validate snapshot retention implementation, home-specific retention, and GRUB rollback integration

No partitioning or formatting is authorized by this document. All disk writes remain disabled.
