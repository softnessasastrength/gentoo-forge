# Target and compatibility review

Reference targets are the [amd64 Handbook](https://wiki.gentoo.org/wiki/Handbook:AMD64/Full/Installation)
and [Snapper documentation](https://wiki.gentoo.org/wiki/Snapper). A fresh review
attempt on 2026-11-08 was blocked by the documentation site's robots policy;
current compatibility has not been independently verified in this session.
The proposed configuration below is not a certified workstation configuration.
Current ebuild USE flags and service dependencies still require validation in a
synced Portage tree before generating install commands.

The intended machine is Ryzen 5 4500 (Zen 2, `-march=znver2`), RX 6600 XT, 16 GiB
RAM and a user-selected dedicated SSD. Plan GPT/UEFI with 1 GiB FAT ESP, 20 GiB swap
partition and remaining Btrfs. Use separate root/home subvolumes and independent
Snapper configurations. Retention: 6 hourly, 7 daily, 4 weekly, 3 monthly, 0 yearly;
number cleanup up to 10 pre/post snapshots. Do not assume nested home is included
in a root snapshot. Verify cleanup scheduling under OpenRC explicitly.

Target OpenRC standard amd64 multilib Stage3, Plasma Wayland/XWayland, SDDM,
NetworkManager, PipeWire, AMDGPU/Mesa RADV, firmware and AMD microcode,
`gentoo-kernel` with dracut, UEFI GRUB, Steam/Proton/Wine/GameMode. Verify 32-bit
Mesa/Vulkan ABI dependencies, licensing, session management and OpenRC services
against the chosen profile. Source-first means no global binary preference;
selected binary exceptions must be explicit and recorded. Initial MAKEOPTS are
`-j6 -l6`; memory pressure may require lower concurrency. Host `forge`, user
`branden`, timezone `America/New_York`, locale `en_US.UTF-8`.

## Required acceptance tests before writes are enabled

- Verify Stage3 signature and digest from trusted Gentoo release keys. Never
  execute metadata or configuration as shell input.
- Boot the installed distribution kernel under OVMF with correct Btrfs root,
  firmware and microcode in the dracut image. Inspect generated GRUB entries.
- Confirm swap UUID in fstab, resume argument and dracut resume support. 20 GiB
  exceeds physical RAM, but capacity alone does not prove hibernation works.
  Exercise actual hibernate/resume and verify filesystem integrity afterward.
- Create independent root and home snapshots; exercise retention cleanup. Boot
  an older root, restore a writable root and verify mount/default-subvolume
  semantics and separate home preservation. GRUB menu entries alone are not rollback.
- Recover from a live ISO by mounting Btrfs top level, inspecting snapshots,
  selecting a known-good writable root, checking fstab and regenerating initramfs
  and GRUB as needed. Preserve the broken root until recovery is verified.
- Interrupt each stage and verify safe restart with identity and mount checks
  repeated. Test only disposable disks in an isolated VM without host devices.

All of these are pending. Bootstrap through finalization therefore remain locked.

