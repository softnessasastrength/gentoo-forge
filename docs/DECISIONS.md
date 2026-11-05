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
- Kernel boot integration: Dracut, verified swap resume UUID, conservative updates, and GRUB snapshot integration selected; runtime compatibility and exact installkernel behavior pending validation


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

- Btrfs subvolume policy: minimal separation, root @ mounted at / and home @home mounted at /home, with independent root and home snapshot storage; final Snapper mount paths and GRUB snapshot integration require validation before installer execution.

- EFI System Partition mount: /efi (1 GiB ESP); /boot remains inside the Btrfs root subvolume, not a separate partition.
- Boot artifacts: GRUB x86-64 UEFI executable and EFI assets on /efi; versioned kernel images, matching Dracut initramfs images, and GRUB configuration in Btrfs /boot. Resolve actual filenames and installkernel behavior at build time; do not hardcode unverified paths.
- Boot consistency policy: preserve a known-good kernel, matching modules/initramfs, and boot entry across updates; keep gentoo-kernel-bin fallback. Regenerate and validate GRUB entries against actual Btrfs subvolume paths; never claim a root snapshot is bootable without a VM boot test.
- Snapshot recovery boundary: ESP is outside Btrfs snapshots; maintain an independent EFI/GRUB recovery procedure and test restoration of root snapshots with their matching boot artifacts.

- Recovery selection: GRUB snapshot entry is a temporary diagnostic boot only; permanent rollback is a separate, explicit, device-aware confirmation after inspection. Selecting a GRUB entry must never automatically commit rollback.
- Hibernation/rollback policy: before committing a permanent rollback, detect any pending hibernation state using a validated mechanism; if present, explain that the suspended session will be lost and require explicit confirmation before invalidating it. If detection or invalidation cannot be verified, fail closed and block rollback.
- Recovery invariants: never resume a stale hibernation image after changing the root filesystem; preserve a known-good kernel/initramfs/modules set and fallback entry; confirm the selected snapshot's Btrfs identity, bootability, and kernel-module compatibility before committing; preserve independent /home data and snapshot history; record an auditable rollback plan and recovery outcome without secrets; keep a separate EFI/GRUB repair path.
- Implementation status: recovery flow is policy only; GRUB snapshot integration, Snapper rollback mechanics, resume-image detection/invalidation, and power-loss recovery must pass disposable-VM tests before destructive execution is enabled.

- LiveCD bootstrap: hybrid online/offline. Support verified HTTPS retrieval or explicitly supplied local Stage 3, Portage snapshot, and required installation artifacts; no implicit trust in local caches.
- Bootstrap safety: read-only preflight checks for UEFI boot, architecture, root privileges for eventual install, Python/curses, lsblk/blkid, partitioning/filesystem tools, Btrfs, tar, cryptographic verification tools, network/DNS/HTTPS/time when online, and available disk/memory. Missing dependencies produce actionable diagnostics, never automatic unreviewed disk changes.
- Artifact verification: pin resolved architecture/profile and release metadata; verify authenticity using trusted Gentoo signing keys and signatures where provided, plus expected cryptographic digests. Checksums alone do not authenticate untrusted local media. Reject absent, stale/incompatible, tampered, or unverifiable inputs; fail closed. Record provenance without secrets.
- Offline constraints: verify all required inputs and dependencies are present before installation authorization; no silent network fallback or substitution. Warn that full source compilation and package resolution may require additional distfiles/binpkgs beyond a Stage 3 and Portage snapshot; offline completeness must be proven in disposable VM tests.
- Installer bootstrap remains read-only; no disk writes or destructive install authorization are implied by these decisions.

- Portage package policy: source-first. Compile packages from verified source by default; binary acceleration is optional, scoped to explicitly approved packages or sets, and must never silently enable a binary package repository.
- Binary package trust: require authenticated repository metadata, trusted signing keys/signatures when available, verified package digests, matching architecture/ABI/USE/profile constraints, and an auditable per-package approval record. Reject unverifiable or mismatched binaries; no silent source/binary substitution.
- Package resolution: resolve exact Gentoo profile, package atoms, dependency graph, USE flags, ABI_X86 requirements, licenses, masks, keywording, and conflicts against the selected repository snapshot before installation. Present proposed exceptions and obtain explicit approval; fail closed on unresolved dependencies.
- Reproducibility: record Stage 3 identity, verified release provenance, Gentoo repository snapshot/commit, chosen mirrors, source distfile digests, binary package provenance, selected flags, and package plan in a non-secret installation manifest.
- Hybrid offline completeness: preflight the full resolved dependency closure and required distfiles/binpkgs for the selected profile, including KDE, kernel, firmware, and gaming packages; do not claim offline-ready from Stage 3 and Portage metadata alone. Missing or unverifiable artifacts block offline installation.
- Implementation status: package policy is documented, not a working resolver; Portage behavior, signing support, dependency closure, and offline installation require disposable-VM validation.

- Installation resumability: checkpoint-based, with verified outputs and explicit phase transitions. A checkpoint records planned inputs, verified target identity, artifact digests, completed outputs, and phase status; never trust a completion marker alone.
- Resume safety: re-discover physical target and verify stable device identity, partition UUIDs, expected mounts/filesystems, manifest version and integrity, and outputs before continuing. Refuse resume on mismatches or ambiguous state. Never replay partitioning, formatting, swap initialization, or other destructive steps automatically; require a fresh plan and device-specific authorization if such work is necessary.
- Phase retries: use idempotent, independently validated steps where feasible. Reuse verified downloads/build outputs, retry safe package operations after consistency checks, and explicitly distinguish interrupted extraction/configuration from completed installation. Fail closed on partially applied, non-idempotent operations and preserve diagnostic evidence.
- Logs: structured, timestamped phase/status/error events plus readable live output; sanitized, persistent records and optional diagnostic export. Never record passwords, tokens, secret material, or raw environment dumps. Redact sensitive command arguments and output; review exported diagnostics for identifiers and personal data.
- Log durability: keep a working log in live media memory and persist a sanitized copy to the installed target only after that target is safely mounted and verified. On failures before that point, offer explicit export to user-selected removable media; never assume live media storage is persistent.
- Resume/recovery implementation status: specification only, not implemented or tested; simulate interruption, corrupt checkpoints, device swaps, and power-loss scenarios in disposable VMs before enabling disk writes.

## Pending

- Validate package-specific USE flags against current Gentoo tree at install time; no unverified flags committed

- Verify exact Plasma/OpenRC profile path and Stage 3 release metadata before bootstrap

- Verify minimal Btrfs subvolume mount topology, Snapper root/home configs, and exact partition boundaries (account for GPT metadata and alignment)
- Validate snapshot retention implementation, home-specific retention, and GRUB rollback integration

No partitioning or formatting is authorized by this document. All disk writes remain disabled.
