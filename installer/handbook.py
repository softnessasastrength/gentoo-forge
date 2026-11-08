"""Auditable coverage registry. Code existence never implies installation success."""
from dataclasses import asdict, dataclass
import json

REFERENCE = 'https://wiki.gentoo.org/wiki/Handbook:AMD64/Full/Installation'
REVIEWED = '2026-11-08'


@dataclass(frozen=True)
class Requirement:
    key: str
    section: str
    behavior: str
    implementation: str
    tests: str
    verification: str
    status: str
    required: bool = True


REQUIREMENTS = (
    Requirement('media', 'Media', 'Authenticated live media and portable runtime', 'tools/fetch_gentoo_fixture.py', 'tests/test_media.py', 'Verify release signature/hash and boot actual Gentoo', 'vm-verified'),
    Requirement('live-image', 'Media', 'Bootable Forge USB/external SSD image', '', '', 'Boot generated Forge image on disposable UEFI VM', 'pending'),
    Requirement('preflight', 'Networking', 'Architecture, UEFI, memory, clock, DNS/HTTPS and prerequisites', 'installer/preflight.py', 'tests/test_preflight.py', 'Fail closed for unsupported boot/network/resource state', 'implemented'),
    Requirement('wifi', 'Networking', 'Optional Wi-Fi/static IP/proxy setup', '', '', 'Manual setup using Gentoo live networking tools; no credentials logged', 'manual-only', False),
    Requirement('disk-identity', 'Disks', 'Explicit serial, kernel identity, mounted ancestry and swap checks', 'installer/storage.py', 'tests/test_storage.py', 'Fresh observations and mounted-descendant rejection', 'vm-verified'),
    Requirement('disk-authorization', 'Disks', 'Separate --nuke-it and exact identity/extent confirmation', 'installer/partition_plan.py', 'tests/test_partition_plan.py', 'Reject changed identity/plan, noninteractive and generic yes', 'unit-tested'),
    Requirement('gpt', 'Disks', 'GPT free-space allocation preserving existing entries', 'installer/storage.py', 'tests/test_partition_plan.py', 'Compare old entry and entire synthetic NTFS hash before/after', 'vm-verified'),
    Requirement('gpt-recovery', 'Disks', 'GPT backup and interrupted allocation recovery', 'installer/storage.py', 'tests/test_storage.py', 'Private hashed backup implemented; interrupted recovery execution still pending', 'partial'),
    Requirement('filesystems', 'Disks', '1 GiB FAT32 EFI, 20 GiB swap, remaining Btrfs', 'installer/storage.py', 'tests/test_storage.py', 'Read actual filesystem types, UUIDs and GPT sector extents', 'vm-verified'),
    Requirement('subvolumes', 'Disks', 'Independent root/home and snapshot subvolumes', 'tools/guest_storage_test.py', '', 'Create/show @, @home, @snapshots, @home_snapshots in Gentoo VM', 'vm-verified'),
    Requirement('swap-active', 'Disks', 'Controlled installation swap activation and cleanup', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Activate only selected swap; verify UUID and deactivate during cleanup', 'unit-tested'),
    Requirement('stage3-auth', 'Stage', 'Select and authenticate official OpenRC multilib Stage3', 'installer/media.py', 'tests/test_media.py', 'Trusted primary fingerprint, signed index/checksum, exact archive hash/size', 'integration-verified'),
    Requirement('stage3-extract', 'Stage', 'Validated xattrs/numeric-owner extraction onto target', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Extract signed real Stage3 and inspect resulting root', 'implemented'),
    Requirement('compile', 'Stage', 'Hardware-compatible compiler flags and configurable concurrency', '', '', 'Check actual target ISA and emitted make.conf; compile a package', 'pending'),
    Requirement('chroot', 'Base', 'Pseudo-filesystems, DNS, isolated propagation and cleanup', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Run target executable; unwind mounts after success and injected failure', 'implemented'),
    Requirement('repos', 'Base', 'Authenticated repository bootstrap and synchronization', '', '', 'Run verified webrsync/sync and inspect repository signature settings', 'pending'),
    Requirement('profile', 'Base', 'Select actual available stable Plasma/OpenRC multilib profile', '', '', 'Resolve from synced profiles.desc and verify selected profile', 'pending'),
    Requirement('use', 'Base', 'Per-package USE/IUSE, CPU_FLAGS_X86, graphics and multilib ABI validation', '', '', 'Portage metadata validation plus readable emerge pretend plan', 'pending'),
    Requirement('licenses', 'Base', 'Explicit package licenses and source-first binary exceptions', '', '', 'No global permissive license or binary preference; inspect emerge plan', 'pending'),
    Requirement('news-world', 'Base', 'News review, world update and safe maintenance', '', '', 'Report unread news; run selected world update and verify dependency plan', 'pending'),
    Requirement('locale', 'Base', 'America/New_York and en_US.UTF-8 generation/selection', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Check target localtime, locale -a and configured LANG', 'implemented'),
    Requirement('firmware', 'Kernel', 'AMDGPU firmware and AMD microcode', '', '', 'Install selected firmware and inspect initramfs contents', 'pending'),
    Requirement('dist-kernel', 'Kernel', 'Gentoo distribution kernel via installkernel', 'installer/boot.py', 'tests/test_boot.py', 'Install distribution-kernel package with validated grub/dracut flags', 'unit-tested'),
    Requirement('initramfs', 'Kernel', 'Dracut Btrfs and resume support', 'installer/boot.py', 'tests/test_boot.py', 'Generate image through target installkernel and independently boot it', 'implemented'),
    Requirement('hibernate', 'Kernel', 'Verified hibernate/resume using selected swap UUID', '', '', 'Actual guest/hardware hibernate and resume; VM saved state is insufficient', 'pending'),
    Requirement('fstab', 'System', 'UUID-based root/home/snapshots/ESP/swap mounts', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Read mounts after installed-system boot and compare UUIDs/subvolumes', 'implemented'),
    Requirement('hostname', 'System', 'Hostname forge and local hosts', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Check hostname after first boot', 'implemented'),
    Requirement('networkmanager', 'System', 'NetworkManager and OpenRC service configuration', '', '', 'Installed boot gets link, route, DNS and HTTPS', 'pending'),
    Requirement('accounts', 'System', 'User branden, safe authentication, sudo and locked root policy', 'tools/guest_storage_test.py', '', 'Fixture creates locked users only; real authenticated login/sudo pending', 'partial'),
    Requirement('logger', 'Tools', 'System logger and OpenRC registration', '', '', 'Installed logger accepts and persists a test entry', 'pending'),
    Requirement('cron', 'Tools', 'Cron daemon and OpenRC scheduling', '', '', 'Installed cron executes a harmless test task', 'pending'),
    Requirement('clock', 'Tools', 'Installed time synchronization', '', '', 'Chrony service and synchronization report after boot', 'pending'),
    Requirement('fs-tools', 'Tools', 'Installed Btrfs/FAT filesystem utilities', '', '', 'Verify tools exist in target, not only on live media', 'pending'),
    Requirement('ssh', 'Tools', 'Optional SSH and shell completion', '', '', 'Explicit opt-in only, no root password login by default', 'manual-only', False),
    Requirement('grub', 'Bootloader', 'GRUB UEFI installation and generated boot configuration', 'installer/boot.py', 'tests/test_boot.py', 'Inspect target-generated GRUB config and boot with ISO detached', 'implemented'),
    Requirement('reboot', 'Finalizing', 'Independent installed-system first boot', 'tools/gentoo_vm.py', '', 'OVMF boots target alone; actual root UUID/OpenRC/home/EFI evidence', 'implemented'),
    Requirement('cleanup', 'Finalizing', 'Unmounts, stage archive cleanup and recovery checkpoints', 'installer/bootstrap.py', 'tests/test_bootstrap.py', 'Interrupt and repeat supported stages without reformatting', 'partial'),
    Requirement('plasma', 'Desktop extension', 'Plasma, SDDM, Wayland and XWayland', '', '', 'Actual SDDM user login and desktop/session verification', 'pending'),
    Requirement('graphics-audio', 'Desktop extension', 'AMDGPU/RADV and PipeWire', '', '', 'Observe real renderer/audio devices and services on supported hardware', 'pending'),
    Requirement('gaming', 'Gaming extension', 'Optional Steam/Proton/Wine/GameMode with 32-bit ABI', '', '', 'Resolve dependencies/licenses; launch and verify representative workloads', 'pending', False),
    Requirement('snapper', 'Snapshot extension', 'Root/home Snapper configurations and requested retention', '', '', 'Create independent snapshots and verify OpenRC cleanup schedules', 'pending'),
    Requirement('rollback', 'Snapshot extension', 'Bootable writable root rollback and recovery procedure', '', '', 'Restore/boot older root while independently preserving home', 'pending'),
    Requirement('butler', 'FORGEWORTH extension', 'Permanent unprivileged butler executable and shared policy', 'tools/install_butler.py', 'tests/test_butler.py', 'Staged install/upgrade/uninstall and real native instruction discovery pass', 'integration-verified'),
    Requirement('butler-reboot', 'FORGEWORTH extension', 'Butler usable after installed Plasma login', '', '', 'Type butler in installed user terminal; fresh authentication and inference', 'pending'),
)

ALTERNATIVES = {
    'BIOS/MBR': 'unsupported in the selected UEFI/GPT path; no automatic conversion',
    'systemd': 'unsupported in the selected OpenRC path',
    'no-multilib': 'unsupported because gaming baseline requires 32-bit ABI support',
    'manual kernel/systemd-boot/EFI stub': 'alternative Handbook routes; distribution kernel and GRUB selected',
    'Secure Boot/UKI': 'not yet supported or qualified; do not silently disable firmware security',
    'LUKS/LVM/RAID': 'not yet supported; unknown mappings fail closed',
    'PPTP/PPPoE and other network alternatives': 'manual live-media configuration; no installer automation',
}


def report():
    return {'reference': REFERENCE, 'reviewed': REVIEWED, 'requirements': [asdict(r) for r in REQUIREMENTS],
            'alternatives': ALTERNATIVES,
            'definition_of_done_satisfied': all(r.status in ('vm-verified', 'hardware-verified') for r in REQUIREMENTS if r.required)}


if __name__ == '__main__':
    print(json.dumps(report(), indent=2))
