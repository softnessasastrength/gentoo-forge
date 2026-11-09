"""Target boot stack, shared by installation and isolated VM qualification.

Requires a mounted, authenticated Stage3 target and prepared pseudo-filesystems.
This module never selects, partitions or formats a disk and accepts no shell text.
The caller retains responsibility for target identity and human authorization.
"""
import re
from pathlib import Path

from .bootstrap import write_target
from .portage import CompilerSettings, configure_compiler, select_profile


# Executed by the target's own Python/Portage after repository authentication.
# Metadata comes from Portage (including eclasses), not ebuild text matching.
IUSE_PROBE = r'''import portage
features=set(portage.settings['FEATURES'].split())
assert 'binpkg-request-signature' in features and 'binpkg-ignore-signature' not in features
p = portage.db[portage.settings['ROOT']]['porttree'].dbapi
matches = p.xmatch('match-visible', 'sys-kernel/installkernel')
if not matches:
    raise SystemExit('No visible installkernel package in the authenticated repository')
cpv = portage.best(matches)
iuse = {flag.lstrip('+-') for flag in p.aux_get(cpv, ['IUSE'])[0].split()}
missing = {'grub', 'dracut'} - iuse
if missing:
    raise SystemExit('Requested installkernel flags are unavailable: ' + ', '.join(sorted(missing)))
print('FORGE_METADATA_VERIFIED:' + cpv)
'''


def install_boot_stack(target, storage, *, binary_fallback=True, serial_console=False, jobs=6, load=6, kernel_binary=True):
    """Install the prebuilt distribution kernel, dracut and GRUB.

    Prefer compatible signed official binaries, with source fallback.
    kernel_binary=False selects source gentoo-kernel when explicitly requested.
    binary_fallback explicitly allows signed official binary packages for this
    invocation's dependency closure. It does not enable global getbinpkg.
    Returns only after actual target files and command execution are verified.
    """
    if type(binary_fallback) is not bool or type(serial_console) is not bool or type(kernel_binary) is not bool:
        raise ValueError('Boot options must be explicit booleans')
    if type(jobs) is not int or type(load) is not int or not 1 <= jobs <= 256 or not 1 <= load <= 256:
        raise ValueError('Compilation limits must be integers between 1 and 256')
    root_uuid = storage['filesystems']['root']['UUID']
    swap_uuid = storage['filesystems']['swap']['UUID']
    if not all(re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value) for value in (root_uuid, swap_uuid)):
        raise ValueError('Boot files require validated filesystem UUIDs')
    cmdline = f'root=UUID={root_uuid} rootfstype=btrfs rootflags=subvol=@ resume=UUID={swap_uuid}'
    if serial_console:
        cmdline += ' console=ttyS0,115200n8'
    write_target(target.root, 'etc/kernel/cmdline', cmdline + '\n')
    write_target(target.root, 'etc/default/grub',
                 ('GRUB_TIMEOUT=0\nGRUB_TERMINAL="serial"\nGRUB_SERIAL_COMMAND="serial --speed=115200"\n'
                  if serial_console else 'GRUB_TIMEOUT=5\n') + f'GRUB_CMDLINE_LINUX="{cmdline}"\n')
    make_conf = target.root / 'etc/portage/make.conf'
    original = make_conf.read_text()
    include = 'source /etc/portage/forge-boot.conf'
    if include not in original.splitlines():
        write_target(target.root, 'etc/portage/make.conf', original + '\n' + include + '\n')
    write_target(target.root, 'etc/portage/forge-boot.conf',
                 f'GRUB_PLATFORMS="efi-64"\nMAKEOPTS="-j{jobs} -l{load}"\n'
                 'FEATURES="${FEATURES} binpkg-request-signature -binpkg-ignore-signature"\n')
    if binary_fallback:
        write_target(target.root, 'etc/portage/binrepos.conf/forge.conf',
                     '[gentoo]\npriority = 10\nsync-uri = https://distfiles.gentoo.org/releases/amd64/binpackages/23.0/x86-64/\n')
    write_target(target.root, 'etc/portage/package.use/forge-kernel',
                 'sys-kernel/installkernel dracut grub\n')
    write_target(target.root, 'etc/dracut.conf.d/forge.conf',
                 'hostonly="no"\nadd_dracutmodules+=" btrfs resume "\n')
    print('FORGE_PHASE: authenticating repository and installing target boot packages', flush=True)
    target.chroot(['/usr/bin/emerge-webrsync'], timeout=600)
    selected_profile = select_profile(target, 'minimal')
    compiler = configure_compiler(target, CompilerSettings.for_cpu(Path('/proc/cpuinfo').read_text(), jobs, load))
    write_target(target.root, 'var/lib/gentoo-forge/verify-kernel-use.py', IUSE_PROBE)
    target.chroot(['/usr/bin/python3', '/var/lib/gentoo-forge/verify-kernel-use.py'], timeout=120)
    packages = ['sys-kernel/installkernel', 'sys-kernel/gentoo-kernel-bin' if kernel_binary else 'sys-kernel/gentoo-kernel',
                'sys-boot/grub', 'sys-fs/btrfs-progs', 'sys-fs/dosfstools']
    options = ['/usr/bin/emerge', '--getbinpkg=y' if binary_fallback else '--getbinpkg=n',
               '--usepkg=y' if binary_fallback else '--usepkg=n',
               '--binpkg-respect-use=y', '--autounmask=n', '--verbose']
    target.chroot([*options, '--pretend', *packages], timeout=300)
    target.chroot([*options, *packages], timeout=2400)
    print('FORGE_PHASE: installing target UEFI GRUB into the private ESP', flush=True)
    target.chroot(['/usr/bin/env', 'grub-install', '--target=x86_64-efi', '--efi-directory=/efi',
                   '--boot-directory=/boot', '--removable', '--no-nvram', '--recheck'], timeout=120)
    target.chroot(['/usr/bin/env', 'grub-mkconfig', '-o', '/boot/grub/grub.cfg'], timeout=120)
    if not (target.root / 'efi/EFI/BOOT/BOOTX64.EFI').is_file():
        raise RuntimeError('EFI boot file not installed')
    images = sorted((target.root / 'boot').glob('initramfs-*'))
    if not list((target.root / 'boot').glob('vmlinuz-*')) or not images:
        raise RuntimeError('Target kernel or initramfs missing')
    target.chroot(['/usr/bin/env', 'grub-script-check', '/boot/grub/grub.cfg'], timeout=120)
    observed_uuid = target.chroot(['/usr/bin/env', 'grub-probe', '--target=fs_uuid', '/boot'], timeout=120).strip()
    if observed_uuid != root_uuid:
        raise RuntimeError('GRUB resolves /boot to an unexpected filesystem UUID')
    for image in images:
        if image.is_symlink() or not image.is_file():
            raise RuntimeError('Unexpected initramfs image type')
        modules = target.chroot(['/usr/bin/env', 'lsinitrd', '-m', '/boot/' + image.name], timeout=120)
        if not {'btrfs', 'resume'}.issubset({line.strip() for line in modules.splitlines()}):
            raise RuntimeError('Generated initramfs lacks required Btrfs/resume modules')
    return {'profile': selected_profile, 'compiler': compiler, 'kernel_package': packages[1], 'binary_fallback': binary_fallback,
            'initramfs': 'dracut with Btrfs/resume', 'bootloader': 'UEFI GRUB removable fallback'}
