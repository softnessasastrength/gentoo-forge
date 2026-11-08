# AMD64 Handbook traceability

Reference: https://wiki.gentoo.org/wiki/Handbook:AMD64/Full/Installation. Retrieved in full via HTTPS on 2026-11-08.

The selected path is UEFI/GPT, OpenRC multilib, Btrfs, distribution kernel/dracut and GRUB.
Implemented, unit-tested, integration-verified, VM-verified and hardware-verified are distinct states.
Test file references identify coverage; retained run evidence proves actual execution.
No hardware verification or complete installed-system boot is currently claimed.

| ID | Handbook area | Applicable behavior | Implementation | Automated coverage | Verification procedure | Current evidence |
|---|---|---|---|---|---|---|
| media | Media | Authenticated live media and portable runtime | tools/fetch_gentoo_fixture.py | tests/test_media.py | Verify release signature/hash and boot actual Gentoo | vm-verified |
| live-image | Media | Bootable Forge USB/external SSD image | Pending | Pending | Boot generated Forge image on disposable UEFI VM | pending |
| preflight | Networking | Architecture, UEFI, memory, clock, DNS/HTTPS and prerequisites | installer/preflight.py | tests/test_preflight.py | Fail closed for unsupported boot/network/resource state | implemented |
| wifi | Networking | Optional Wi-Fi/static IP/proxy setup | Pending | Pending | Manual setup using Gentoo live networking tools; no credentials logged | manual-only |
| disk-identity | Disks | Explicit serial, kernel identity, mounted ancestry and swap checks | installer/storage.py | tests/test_storage.py | Fresh observations and mounted-descendant rejection | vm-verified |
| disk-authorization | Disks | Separate --nuke-it and exact identity/extent confirmation | installer/partition_plan.py | tests/test_partition_plan.py | Reject changed identity/plan, noninteractive and generic yes | unit-tested |
| gpt | Disks | GPT free-space allocation preserving existing entries | installer/storage.py | tests/test_partition_plan.py | Compare old entry and entire synthetic NTFS hash before/after | vm-verified |
| gpt-recovery | Disks | GPT backup and interrupted allocation recovery | installer/storage.py | tests/test_storage.py | Private hashed backup implemented; interrupted recovery execution still pending | partial |
| filesystems | Disks | 1 GiB FAT32 EFI, 20 GiB swap, remaining Btrfs | installer/storage.py | tests/test_storage.py | Read actual filesystem types, UUIDs and GPT sector extents | vm-verified |
| subvolumes | Disks | Independent root/home and snapshot subvolumes | tools/guest_storage_test.py | Pending | Create/show @, @home, @snapshots, @home_snapshots in Gentoo VM | vm-verified |
| swap-active | Disks | Controlled installation swap activation and cleanup | Pending | Pending | Activate only selected swap; verify UUID and deactivate during cleanup | pending |
| stage3-auth | Stage | Select and authenticate official OpenRC multilib Stage3 | installer/media.py | tests/test_media.py | Trusted primary fingerprint, signed index/checksum, exact archive hash/size | integration-verified |
| stage3-extract | Stage | Validated xattrs/numeric-owner extraction onto target | installer/bootstrap.py | tests/test_bootstrap.py | Extract signed real Stage3 and inspect resulting root | implemented |
| compile | Stage | Hardware-compatible compiler flags and configurable concurrency | Pending | Pending | Check actual target ISA and emitted make.conf; compile a package | pending |
| chroot | Base | Pseudo-filesystems, DNS, isolated propagation and cleanup | installer/bootstrap.py | tests/test_bootstrap.py | Run target executable; unwind mounts after success and injected failure | implemented |
| repos | Base | Authenticated repository bootstrap and synchronization | Pending | Pending | Run verified webrsync/sync and inspect repository signature settings | pending |
| profile | Base | Select actual available stable Plasma/OpenRC multilib profile | Pending | Pending | Resolve from synced profiles.desc and verify selected profile | pending |
| use | Base | Per-package USE/IUSE, CPU_FLAGS_X86, graphics and multilib ABI validation | Pending | Pending | Portage metadata validation plus readable emerge pretend plan | pending |
| licenses | Base | Explicit package licenses and source-first binary exceptions | Pending | Pending | No global permissive license or binary preference; inspect emerge plan | pending |
| news-world | Base | News review, world update and safe maintenance | Pending | Pending | Report unread news; run selected world update and verify dependency plan | pending |
| locale | Base | America/New_York and en_US.UTF-8 generation/selection | installer/bootstrap.py | tests/test_bootstrap.py | Check target localtime, locale -a and configured LANG | implemented |
| firmware | Kernel | AMDGPU firmware and AMD microcode | Pending | Pending | Install selected firmware and inspect initramfs contents | pending |
| dist-kernel | Kernel | Gentoo distribution kernel via installkernel | installer/boot.py | tests/test_boot.py | Install distribution-kernel package with validated grub/dracut flags | unit-tested |
| initramfs | Kernel | Dracut Btrfs and resume support | installer/boot.py | tests/test_boot.py | Generate image through target installkernel and independently boot it | implemented |
| hibernate | Kernel | Verified hibernate/resume using selected swap UUID | Pending | Pending | Actual guest/hardware hibernate and resume; VM saved state is insufficient | pending |
| fstab | System | UUID-based root/home/snapshots/ESP/swap mounts | installer/bootstrap.py | tests/test_bootstrap.py | Read mounts after installed-system boot and compare UUIDs/subvolumes | implemented |
| hostname | System | Hostname forge and local hosts | installer/bootstrap.py | tests/test_bootstrap.py | Check hostname after first boot | implemented |
| networkmanager | System | NetworkManager and OpenRC service configuration | Pending | Pending | Installed boot gets link, route, DNS and HTTPS | pending |
| accounts | System | User branden, safe authentication, sudo and locked root policy | tools/guest_storage_test.py | Pending | Fixture creates locked users only; real authenticated login/sudo pending | partial |
| logger | Tools | System logger and OpenRC registration | Pending | Pending | Installed logger accepts and persists a test entry | pending |
| cron | Tools | Cron daemon and OpenRC scheduling | Pending | Pending | Installed cron executes a harmless test task | pending |
| clock | Tools | Installed time synchronization | Pending | Pending | Chrony service and synchronization report after boot | pending |
| fs-tools | Tools | Installed Btrfs/FAT filesystem utilities | Pending | Pending | Verify tools exist in target, not only on live media | pending |
| ssh | Tools | Optional SSH and shell completion | Pending | Pending | Explicit opt-in only, no root password login by default | manual-only |
| grub | Bootloader | GRUB UEFI installation and generated boot configuration | installer/boot.py | tests/test_boot.py | Inspect target-generated GRUB config and boot with ISO detached | implemented |
| reboot | Finalizing | Independent installed-system first boot | tools/gentoo_vm.py | Pending | OVMF boots target alone; actual root UUID/OpenRC/home/EFI evidence | implemented |
| cleanup | Finalizing | Unmounts, stage archive cleanup and recovery checkpoints | installer/bootstrap.py | tests/test_bootstrap.py | Interrupt and repeat supported stages without reformatting | partial |
| plasma | Desktop extension | Plasma, SDDM, Wayland and XWayland | Pending | Pending | Actual SDDM user login and desktop/session verification | pending |
| graphics-audio | Desktop extension | AMDGPU/RADV and PipeWire | Pending | Pending | Observe real renderer/audio devices and services on supported hardware | pending |
| gaming | Gaming extension | Optional Steam/Proton/Wine/GameMode with 32-bit ABI | Pending | Pending | Resolve dependencies/licenses; launch and verify representative workloads | pending |
| snapper | Snapshot extension | Root/home Snapper configurations and requested retention | Pending | Pending | Create independent snapshots and verify OpenRC cleanup schedules | pending |
| rollback | Snapshot extension | Bootable writable root rollback and recovery procedure | Pending | Pending | Restore/boot older root while independently preserving home | pending |
| butler | FORGEWORTH extension | Permanent unprivileged butler executable and shared policy | tools/install_butler.py | tests/test_butler.py | Staged install/upgrade/uninstall and real native instruction discovery pass | integration-verified |
| butler-reboot | FORGEWORTH extension | Butler usable after installed Plasma login | Pending | Pending | Type butler in installed user terminal; fresh authentication and inference | pending |

## Alternatives and optional choices

- **BIOS/MBR:** unsupported in the selected UEFI/GPT path; no automatic conversion.
- **systemd:** unsupported in the selected OpenRC path.
- **no-multilib:** unsupported because gaming baseline requires 32-bit ABI support.
- **manual kernel/systemd-boot/EFI stub:** alternative Handbook routes; distribution kernel and GRUB selected.
- **Secure Boot/UKI:** not yet supported or qualified; do not silently disable firmware security.
- **LUKS/LVM/RAID:** not yet supported; unknown mappings fail closed.
- **PPTP/PPPoE and other network alternatives:** manual live-media configuration; no installer automation.

## Evidence boundary

The recorded Gentoo UEFI VM storage run passed, including an unchanged entire NTFS fixture hash.
The Chromebook minimal attempt stopped during Stage3 extraction after host memory pressure.
Remote run 42506097798 completed extraction, then failed at missing offline DNS configuration; no installed boot was recorded.
Current remote qualification procedure and limitations: [MINIMAL-VM.md](MINIMAL-VM.md).
The machine-readable registry is `python -m installer.handbook`. Its completion flag stays false while required stages lack VM evidence.
Regenerate this file with `python -m tools.render_handbook`; CI checks it remains synchronized.
