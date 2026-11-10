"""Only executable inside the explicitly marked disposable Gentoo fixture VM."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from installer.storage import Audit, command, inspect, prepare, read_plan
from installer.bootstrap import TargetMounts, extract, base_configuration, write_target, create_subvolumes
from installer.boot import install_boot_stack
from installer.services import install_base_services
from installer.graphics import install_amd_graphics
from tools.install_butler import install as install_butler
from tools.guest_payload import copy_payload


def minimal_system(storage):
    size = int(os.environ['FORGE_STAGE3_SIZE'])
    expected = os.environ['FORGE_STAGE3_SHA256']
    with TargetMounts(storage) as target:
        archive = target.root / '.forgeworth-stage3.tar.xz'
        digest = hashlib.sha256()
        with open('/dev/disk/by-id/virtio-FORGE-STAGE3', 'rb', buffering=0) as source, archive.open('xb') as output:
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
        target.activate_swap()
        target.pseudo()
        print('FORGE_PHASE: verifying chroot and configuring base system', flush=True)
        target.chroot(['/usr/bin/env', 'bash', '-c', 'test -f /etc/gentoo-release && command -v emerge && command -v rc-update'])
        target.chroot(['/usr/bin/env', 'locale-gen'], timeout=120)
        target.chroot(['/usr/bin/env', 'env-update'])
        target.chroot(['/usr/bin/env', 'useradd', '-m', '-s', '/bin/bash', 'branden'])
        # Fixture accounts stay locked; no default passwords or autologin.
        target.chroot(['/usr/bin/env', 'passwd', '-l', 'root'])
        target.chroot(['/usr/bin/env', 'passwd', '-l', 'branden'])
        boot = install_boot_stack(target, storage, binary_fallback=True, serial_console=True, jobs=2, load=2)
        root_uuid = storage['filesystems']['root']['UUID']
        if os.environ.get('FORGE_BASE_SERVICES') == '1':
            print('FORGE_PHASE: installing target system services', flush=True)
            storage['base_services'] = install_base_services(target, binary_fallback=True, replace_dhcpcd=True)
        if os.environ.get('FORGE_AMD_GRAPHICS') == '1':
            print('FORGE_PHASE: installing AMDGPU and Mesa RADV', flush=True)
            storage['amd_graphics'] = install_amd_graphics(target)
        native_expected = bool(os.environ.get('FORGE_CODEX_SIZE'))
        if native_expected:
            copy_payload('/dev/disk/by-id/virtio-FORGE-CODEX', Path('/run/forge-code/bin/codex'),
                         int(os.environ['FORGE_CODEX_SIZE']), os.environ['FORGE_CODEX_SHA256'])
        install_butler(target.root)
        boot_check = '''#!/bin/sh
uuid=$(findmnt -n -o UUID /)
fs=$(findmnt -n -o FSTYPE /)
home=$(findmnt -n -o FSROOT /home)
init=$(cat /proc/1/comm)
efi=false; [ -d /sys/firmware/efi ] && efi=true
iso=false; [ -b /dev/sr0 ] && iso=true
butler=false
if su -l -s /bin/bash branden -c 'command -v butler && butler --offline' >/var/log/forge-butler-check.log 2>&1 && grep -q 'FORGEWORTH offline help' /var/log/forge-butler-check.log; then butler=true; fi
native=false
native_ok=true
if [ EXPECT_NATIVE = true ]; then
    if su -l -s /bin/bash branden -c 'butler --check-instructions' >/var/log/forge-native-check.log 2>&1 && grep -q 'Verified: Codex discovered the complete canonical' /var/log/forge-native-check.log; then native=true; else native_ok=false; fi
fi
ok=false
if [ "$uuid" = "ROOT_UUID" ] && [ "$fs" = btrfs ] && [ "$home" = /@home ] && [ "$init" = init ] && [ "$efi" = true ] && [ "$iso" = false ] && [ "$butler" = true ] && [ "$native_ok" = true ] && [ -f /run/openrc/softlevel ]; then ok=true; fi
printf 'FORGE_BOOT_RESULT:{"passed":%s,"root_uuid":"%s","root_fs":"%s","home_subvolume":"%s","pid1":"%s","uefi":%s,"iso_present":%s,"butler_user_offline":%s,"native_instruction_discovery":%s}\\n' "$ok" "$uuid" "$fs" "$home" "$init" "$efi" "$iso" "$butler" "$native" >/dev/ttyS0
(sleep 2; poweroff) &
exit 0
'''.replace('ROOT_UUID', root_uuid).replace('EXPECT_NATIVE', 'true' if native_expected else 'false')
        write_target(target.root, 'etc/local.d/forge-verify.start', boot_check, 0o755)
        target.chroot(['/usr/bin/env', 'rc-update', 'add', 'local', 'default'])
        storage['minimal_stage3_extracted'] = True
        storage['chroot_verified'] = True
        storage['boot_stack'] = boot
        storage['initramfs'] = 'generated with dracut for Btrfs/resume'
        storage['bootloader'] = 'UEFI GRUB removable fallback in private ESP'
        storage['portage_sync'] = 'emerge-webrsync completed in target'
        storage['desktop'] = 'not installed'
        storage['butler'] = 'staged permanent executable; ordinary-user offline check required after boot, Codex inference not tested'
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
    finally:
        command(['umount', '/run/forge-mount'])
    result['subvolumes'] = create_subvolumes(result)
    if hash_partition('/dev/sda1') != before:
        raise RuntimeError('Existing NTFS changed during subvolume setup')
    result.update({'ntfs_entire_partition_sha256_unchanged': True,
                   'mounted_descendant_rejected': True, 'uefi_live_boot': True,
                   'qualification': 'storage only', 'installed_system_boot': 'not tested'})
    print('FORGE_STORAGE_RESULT:' + json.dumps(result), flush=True)
    if os.environ.get('FORGE_STAGE3_SIZE'):
        minimal_system(result)
        if hash_partition('/dev/sda1') != before:
            raise RuntimeError('Existing NTFS changed during bootstrap')
    print('FORGE_RESULT:' + json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
