"""Only executable inside the explicitly marked disposable Gentoo fixture VM."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import shutil

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
        target.pseudo(require_dns=False)
        print('FORGE_PHASE: verifying chroot and configuring base system', flush=True)
        target.chroot(['/usr/bin/env', 'bash', '-c', 'test -f /etc/gentoo-release && command -v emerge && command -v rc-update'])
        target.chroot(['/usr/bin/env', 'locale-gen'], timeout=120)
        target.chroot(['/usr/bin/env', 'env-update'])
        target.chroot(['/usr/bin/env', 'useradd', '-m', '-s', '/bin/bash', 'branden'])
        # Fixture accounts stay locked; no default passwords or autologin.
        target.chroot(['/usr/bin/env', 'passwd', '-l', 'root'])
        target.chroot(['/usr/bin/env', 'passwd', '-l', 'branden'])
        kernel = os.uname().release
        module_source = Path('/lib/modules') / kernel
        module_target = target.root / 'usr/lib/modules' / kernel
        module_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(module_source, module_target, symlinks=True)
        shutil.copyfile('/run/initramfs/live/boot/gentoo', target.root / 'boot/vmlinuz-forge-fixture')
        root_uuid = storage['filesystems']['root']['UUID']
        swap_uuid = storage['filesystems']['swap']['UUID']
        cmdline = f'root=UUID={root_uuid} rootfstype=btrfs rootflags=subvol=@ resume=UUID={swap_uuid} console=ttyS0,115200n8'
        write_target(target.root, 'etc/kernel/cmdline', cmdline + '\n')
        print('FORGE_PHASE: generating a normal Btrfs/resume initramfs', flush=True)
        command(['dracut', '--force', '--no-hostonly', '--no-hostonly-cmdline', '--gzip',
                 '--add', 'btrfs resume', '--omit', 'dmsquash-live dmsquash-live-ntfs livenet',
                 '--tmpdir', str(target.root / 'var/tmp'),
                 str(target.root / 'boot/initramfs-forge-fixture.img'), kernel], timeout=600)
        grub = ('set timeout=0\nserial --unit=0 --speed=115200\nterminal_input serial\nterminal_output serial\n'
                f'search --no-floppy --fs-uuid --set=root {root_uuid}\n'
                'menuentry "Gentoo Forge minimal qualification" {\n'
                f' linux /@/boot/vmlinuz-forge-fixture {cmdline}\n'
                ' initrd /@/boot/initramfs-forge-fixture.img\n}\n')
        write_target(target.root, 'boot/grub/grub.cfg', grub)
        print('FORGE_PHASE: installing UEFI GRUB into the private ESP', flush=True)
        command(['grub-install', '--target=x86_64-efi', '--efi-directory=' + str(target.root / 'efi'),
                 '--boot-directory=' + str(target.root / 'boot'), '--removable', '--no-nvram', '--recheck'], timeout=120)
        if not (target.root / 'efi/EFI/BOOT/BOOTX64.EFI').is_file():
            raise RuntimeError('EFI boot file not installed')
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
        storage['kernel_source'] = 'Gentoo live-media kernel, explicit VM qualification fallback only'
        storage['initramfs'] = 'generated with dracut for Btrfs/resume'
        storage['bootloader'] = 'UEFI GRUB removable fallback in private ESP'
        storage['portage_sync'] = 'not performed in this offline minimal fixture'
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
