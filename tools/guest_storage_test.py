"""Only executable inside the explicitly marked disposable Gentoo fixture VM."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from installer.storage import Audit, command, inspect, prepare, read_plan
from installer.bootstrap import TargetMounts, extract, base_configuration, write_target


def minimal_system(storage):
    size = int(os.environ['FORGE_STAGE3_SIZE'])
    expected = os.environ['FORGE_STAGE3_SHA256']
    with TargetMounts(storage) as target:
        archive = target.root / '.forgeworth-stage3.tar.xz'
        digest = hashlib.sha256()
        with open('/dev/vda', 'rb', buffering=0) as source, archive.open('xb') as output:
            remaining = size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise RuntimeError('Truncated read-only Stage3 fixture')
                output.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError('Guest Stage3 fixture hash mismatch')
        print('FORGE_PHASE: extracting authenticated Stage3', flush=True)
        extract(archive, target.root, expected, size)
        archive.unlink()
        base_configuration(target.root, storage)
        target.pseudo()
        print('FORGE_PHASE: verifying chroot and configuring base system', flush=True)
        target.chroot(['/usr/bin/env', 'bash', '-c', 'test -f /etc/gentoo-release && command -v emerge && command -v rc-update'])
        target.chroot(['/usr/bin/env', 'locale-gen'], timeout=120)
        target.chroot(['/usr/bin/env', 'env-update'])
        target.chroot(['/usr/bin/env', 'useradd', '-m', '-s', '/bin/bash', 'branden'])
        # Fixture accounts stay locked; no default passwords or autologin.
        target.chroot(['/usr/bin/env', 'passwd', '-l', 'root'])
        target.chroot(['/usr/bin/env', 'passwd', '-l', 'branden'])
        root_uuid = storage['filesystems']['root']['UUID']
        swap_uuid = storage['filesystems']['swap']['UUID']
        cmdline = f'root=UUID={root_uuid} rootfstype=btrfs rootflags=subvol=@ resume=UUID={swap_uuid} console=ttyS0,115200n8'
        write_target(target.root, 'etc/kernel/cmdline', cmdline + '\n')
        write_target(target.root, 'etc/default/grub',
                     'GRUB_TIMEOUT=0\nGRUB_TERMINAL="serial"\nGRUB_SERIAL_COMMAND="serial --speed=115200"\n'
                     + f'GRUB_CMDLINE_LINUX="{cmdline}"\n')
        make_conf = target.root / 'etc/portage/make.conf'
        original = make_conf.read_text()
        write_target(target.root, 'etc/portage/make.conf', original +
                     '\nGRUB_PLATFORMS="efi-64"\nMAKEOPTS="-j2 -l2"\n'
                     'FEATURES="${FEATURES} binpkg-request-signature"\n')
        write_target(target.root, 'etc/portage/binrepos.conf/forge.conf',
                     '[gentoo]\npriority = 10\nsync-uri = https://distfiles.gentoo.org/releases/amd64/binpackages/23.0/x86-64/\n')
        write_target(target.root, 'etc/portage/package.use/forge-kernel',
                     'sys-kernel/installkernel dracut grub\n')
        write_target(target.root, 'etc/dracut.conf.d/forge.conf',
                     'hostonly="no"\nadd_dracutmodules+=" btrfs resume "\n')
        print('FORGE_PHASE: authenticating repository and installing target boot packages', flush=True)
        target.chroot(['/usr/bin/emerge-webrsync'], timeout=600)
        # Explicit binary exception for the VM boot-stack dependency closure.
        # All binaries require signatures; production remains source-first.
        packages = ['sys-kernel/installkernel', 'sys-kernel/gentoo-kernel-bin',
                    'sys-boot/grub', 'sys-fs/btrfs-progs', 'sys-fs/dosfstools']
        options = ['/usr/bin/emerge', '--getbinpkg=y', '--usepkg=y',
                   '--binpkg-respect-use=y', '--autounmask=n', '--verbose']
        target.chroot([*options, '--pretend', *packages], timeout=300)
        target.chroot([*options, *packages], timeout=2400)
        print('FORGE_PHASE: installing target UEFI GRUB into the private ESP', flush=True)
        target.chroot(['/usr/bin/grub-install', '--target=x86_64-efi', '--efi-directory=/efi',
                       '--boot-directory=/boot', '--removable', '--no-nvram', '--recheck'], timeout=120)
        target.chroot(['/usr/bin/grub-mkconfig', '-o', '/boot/grub/grub.cfg'], timeout=120)
        if not (target.root / 'efi/EFI/BOOT/BOOTX64.EFI').is_file():
            raise RuntimeError('EFI boot file not installed')
        if not list((target.root / 'boot').glob('vmlinuz-*')) or not list((target.root / 'boot').glob('initramfs-*')):
            raise RuntimeError('Target kernel or initramfs missing')
        boot_check = '''#!/bin/sh
uuid=$(findmnt -n -o UUID /)
fs=$(findmnt -n -o FSTYPE /)
home=$(findmnt -n -o FSROOT /home)
init=$(cat /proc/1/comm)
efi=false; [ -d /sys/firmware/efi ] && efi=true
iso=false; [ -b /dev/sr0 ] && iso=true
ok=false
if [ "$uuid" = "ROOT_UUID" ] && [ "$fs" = btrfs ] && [ "$home" = /@home ] && [ "$init" = init ] && [ "$efi" = true ] && [ "$iso" = false ] && [ -f /run/openrc/softlevel ]; then ok=true; fi
printf 'FORGE_BOOT_RESULT:{"passed":%s,"root_uuid":"%s","root_fs":"%s","home_subvolume":"%s","pid1":"%s","uefi":%s,"iso_present":%s}\\n' "$ok" "$uuid" "$fs" "$home" "$init" "$efi" "$iso"
(sleep 2; poweroff) &
exit 0
'''.replace('ROOT_UUID', root_uuid)
        write_target(target.root, 'etc/local.d/forge-verify.start', boot_check, 0o755)
        target.chroot(['/usr/bin/env', 'rc-update', 'add', 'local', 'default'])
        storage['minimal_stage3_extracted'] = True
        storage['chroot_verified'] = True
        storage['kernel_source'] = 'sys-kernel/gentoo-kernel-bin: explicit signed binary VM fallback'
        storage['initramfs'] = 'generated with dracut for Btrfs/resume'
        storage['bootloader'] = 'UEFI GRUB removable fallback in private ESP'
        storage['portage_sync'] = 'emerge-webrsync completed in target'
        storage['desktop'] = 'not installed'
        storage['account_passwords'] = 'locked in unattended VM fixture'


def hash_partition(path):
    with open(path, 'rb', buffering=0) as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if os.geteuid() != 0 or 'forge_storage_fixture=1' not in Path('/proc/cmdline').read_text():
        raise PermissionError('Not the explicit disposable VM fixture')
    if not Path('/etc/gentoo-release').is_file() or not Path('/sys/firmware/efi').is_dir():
        raise RuntimeError('Fixture must boot actual Gentoo in UEFI mode')
    target = inspect('/dev/sda')
    if target.serial != 'FORGE-SMOKE-0001' or target.size != 64 * 1024**3 or target.model != 'QEMU HARDDISK':
        raise RuntimeError('Fixture identity mismatch: never operate on another disk')
    # Only this VM-only fixture setup may initialize its newly created blank disk.
    command(['sgdisk', '--clear', '--new=1:2048:+512M', '--typecode=1:0700',
             '--change-name=1:KEEP_NTFS', '/dev/sda'])
    for _ in range(50):
        if Path('/dev/sda1').exists():
            break
        time.sleep(.1)
    command(['mkfs.ntfs', '--fast', '--force', '--label', 'KEEP_NTFS', '/dev/sda1'], timeout=120)
    before = hash_partition('/dev/sda1')
    proposal = read_plan(target)
    start, end = proposal['selected_extent']
    confirmation = f'ALLOCATE {target.path} {target.serial} {start}-{end} {proposal["fingerprint"]}'
    result = prepare(target, proposal, nuke_it=True, interactive=True,
                     confirmation=confirmation, audit=Audit('/run/forge-test-audit.jsonl'))
    if hash_partition('/dev/sda1') != before:
        raise RuntimeError('Existing NTFS fixture changed')
    command(['mkdir', '-p', '/run/forge-mount'])
    command(['mount', '-t', 'btrfs', result['partitions']['root'], '/run/forge-mount'])
    try:
        try:
            inspect('/dev/sda')
        except ValueError:
            pass
        else:
            raise RuntimeError('Mounted descendant did not block target authorization')
        for name in ('@', '@home', '@snapshots', '@home_snapshots'):
            command(['btrfs', 'subvolume', 'create', '/run/forge-mount/' + name])
            command(['btrfs', 'subvolume', 'show', '/run/forge-mount/' + name])
        result['subvolumes'] = 'created and inspected in Gentoo VM'
    finally:
        command(['umount', '/run/forge-mount'])
    if os.environ.get('FORGE_STAGE3_SIZE'):
        minimal_system(result)
        if hash_partition('/dev/sda1') != before:
            raise RuntimeError('Existing NTFS changed during bootstrap')
    result.update({'ntfs_entire_partition_sha256_unchanged': True,
                   'mounted_descendant_rejected': True, 'uefi_live_boot': True,
                   'qualification': 'storage only', 'installed_system_boot': 'not tested'})
    print('FORGE_RESULT:' + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
