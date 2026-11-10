"""Gentoo live-CD storage preparation, isolated from the unprivileged UI/AI.

The public CLI is qualification-locked until a disposable Gentoo VM test passes.
No supplied JSON inventory, shell fragment or model output is accepted as authority.
"""
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from tui.safety import validate_target
from .partition_plan import (plan as free_space_plan, commands as free_space_commands,
                             authorize_space, GUIDS)

GIB = 1024**3
# Keep physical writes locked until the exact executor has passed Gentoo VM tests.
PHYSICAL_WRITES_QUALIFIED = False
TOOLS = ('lsblk', 'sfdisk', 'sgdisk', 'mkfs.fat', 'mkswap', 'mkfs.btrfs', 'blkid', 'mount', 'umount', 'btrfs')
VIRTUAL_FS = {'proc', 'sysfs', 'tmpfs', 'ramfs', 'rootfs', 'devtmpfs', 'devpts',
              'cgroup', 'cgroup2', 'mqueue', 'securityfs', 'pstore', 'debugfs',
              'tracefs', 'configfs', 'efivarfs', 'fusectl', 'hugetlbfs', 'binfmt_misc',
              'nsfs', 'autofs', 'bpf'}


def command(argv, *, timeout=30):
    """Only fixed argument vectors constructed by this module reach this function."""
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=timeout, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if result.returncode:
        raise RuntimeError(f'{Path(argv[0]).name} failed with exit {result.returncode}; inspect the local audit log before recovery')
    return result.stdout


def inventory():
    value = json.loads(command(['lsblk', '--json', '--bytes', '--paths', '--tree',
                                '--output', 'PATH,KNAME,TYPE,SIZE,MODEL,SERIAL,RO,MAJ:MIN,MOUNTPOINTS']))
    if not isinstance(value, dict) or not isinstance(value.get('blockdevices'), list):
        raise ValueError('Invalid live block inventory')
    for node in nodes(value):
        if node.get('type') == 'disk' and not node.get('serial'):
            # Gentoo lsblk can omit udev serials even when the kernel's SCSI
            # VPD page contains the physical serial. Never synthesize one.
            page = Path('/sys/dev/block') / node['maj:min'] / 'device/vpd_pg80'
            try:
                data = page.read_bytes()
                length = int.from_bytes(data[2:4], 'big')
                if len(data) >= 4 and data[1] == 0x80 and 0 < length <= 256 and len(data) == 4 + length:
                    serial = data[4:].decode('ascii').strip()
                    if serial and serial.isprintable():
                        node['serial'] = serial
            except (OSError, UnicodeError):
                pass
    return value


def nodes(value):
    pending = list(value['blockdevices'])
    count = 0
    while pending:
        count += 1
        if count > 4096:
            raise ValueError('Device tree exceeds safety bound')
        node = pending.pop()
        if not isinstance(node, dict) or not re.fullmatch(r'\d+:\d+', str(node.get('maj:min', ''))):
            raise ValueError('Missing kernel device identity')
        yield node
        children = node.get('children', [])
        if not isinstance(children, list):
            raise ValueError('Incomplete device ancestry')
        pending.extend(children)


def unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)


def active_devices(value, mountinfo, swaps, resolve_device):
    """Resolve mount/swap identities against the kernel inventory, including aliases.

    Overlay layers must resolve to explicit underlying mounts. All device mounts
    in this namespace are protected, not only / and /boot.
    """
    all_nodes = list(nodes(value))
    known = {n['maj:min'] for n in all_nodes}
    active = set()
    root_seen = False
    mounts = []
    for line in mountinfo.splitlines():
        fields = line.split()
        try:
            separator = fields.index('-')
            devno, target = fields[2], unescape(fields[4])
            filesystem, source = fields[separator + 1:separator + 3]
            options = fields[separator + 3]
        except (ValueError, IndexError) as exc:
            raise ValueError('Malformed mount ancestry') from exc
        root_seen |= target == '/'
        mounts.append((target, filesystem, source, devno, options))
    def protect(entry, seen):
        target, filesystem, source, devno, options = entry
        if target in seen:
            raise ValueError('Cyclic overlay ancestry')
        if filesystem in VIRTUAL_FS:
            return
        if filesystem == 'overlay':
            settings = dict(p.split('=', 1) for p in options.split(',') if '=' in p)
            if not all(key in settings for key in ('lowerdir', 'upperdir', 'workdir')):
                raise ValueError('Incomplete overlay ancestry')
            layers = settings['lowerdir'].split(':') + [settings['upperdir'], settings['workdir']]
            for layer in layers:
                layer = unescape(layer)
                if not layer.startswith('/') or '..' in Path(layer).parts:
                    raise ValueError('Noncanonical overlay layer path')
                candidates = [m for m in mounts if m[0] != target and (layer == m[0] or layer.startswith(m[0].rstrip('/') + '/'))]
                if not candidates:
                    raise ValueError('Unresolved overlay backing mount')
                protect(max(candidates, key=lambda m: len(m[0])), seen | {target})
            return
        if devno not in known:
            if not source.startswith('/dev/'):
                raise ValueError('Unresolved filesystem ancestry: ' + filesystem)
            devno = resolve_device(unescape(source).split('[', 1)[0])
        if devno not in known:
            raise ValueError('Mounted device missing from inventory')
        active.add(devno)
    for entry in mounts:
        protect(entry, set())
    if not root_seen:
        raise ValueError('Root mount evidence is missing')
    lines = swaps.splitlines()
    if not lines or not lines[0].startswith('Filename'):
        raise ValueError('Active swap evidence is unavailable')
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 5 or fields[1] != 'partition' or not fields[0].startswith('/dev/'):
            raise ValueError('Swapfile or unresolved swap ancestry blocks storage preparation')
        device = resolve_device(unescape(fields[0]))
        if device not in known:
            raise ValueError('Swap device missing from inventory')
        active.add(device)
    return [n['path'] for n in all_nodes if n['maj:min'] in active]


def device_number(path):
    info = os.stat(path)
    if not stat.S_ISBLK(info.st_mode):
        raise ValueError('Expected an actual block device')
    return f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'


@dataclass(frozen=True)
class Target:
    path: str
    serial: str
    model: str
    size: int
    devno: str


def inspect(path):
    value = inventory()
    active = active_devices(value, Path('/proc/self/mountinfo').read_text(),
                            Path('/proc/swaps').read_text(), device_number)
    disk = validate_target(value, path, active, [])
    if disk.size < 64 * GIB:
        raise ValueError('Storage profile requires at least 64 GiB; full source builds need additional host capacity')
    if any(not text.isprintable() for text in (disk.serial, disk.model)):
        raise ValueError('Non-printable disk identity')
    tree = next(n for n in value['blockdevices'] if n['path'] == path)
    for node in nodes({'blockdevices': [tree]}):
        holders = Path('/sys/dev/block') / node['maj:min'] / 'holders'
        if not holders.is_dir() or any(holders.iterdir()):
            raise ValueError('Device holders are unknown or active')
    devno = tree['maj:min']
    if device_number(path) != devno:
        raise ValueError('Device path identity changed during inspection')
    return Target(**asdict(disk), devno=devno)


def read_plan(target):
    return free_space_plan(json.loads(command(['sfdisk', '--json', target.path])), target.path, target.size)


class Audit:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.absolute().parent.resolve() != self.path.absolute().parent:
            raise ValueError('Audit directory ancestry must be canonical and not use symlinks')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink():
            raise ValueError('Audit directory must not be a symlink')
        parent = self.path.parent.stat()
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
            raise ValueError('Audit directory must be owned and not writable by other accounts')

    def write(self, action, **fields):
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
                raise ValueError('Audit file is not a private owned regular file')
            os.fchmod(stream.fileno(), 0o600)
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps({'time': time.time(), 'action': action, **fields}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())


def open_target(target):
    fd = os.open(target.path, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISBLK(info.st_mode) or f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' != target.devno:
            raise ValueError('Opened device does not match approved kernel identity')
        size = bytearray(8)
        fcntl.ioctl(fd, 0x80081272, size)  # BLKGETSIZE64: actual opened device.
        if int.from_bytes(size, sys.byteorder) != target.size:
            raise ValueError('Opened device size changed')
        return fd
    except BaseException:
        os.close(fd)
        raise


def partition_devices(target, expected_numbers):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = inventory()
        parents = [n for n in value['blockdevices'] if n.get('maj:min') == target.devno]
        if len(parents) != 1:
            raise ValueError('Approved disk disappeared')
        result = {}
        for node in parents[0].get('children', []):
            if node.get('type') != 'part':
                raise ValueError('Unexpected device holder after partitioning')
            sysnode = Path('/sys/dev/block') / node['maj:min']
            if sysnode.resolve().parent != (Path('/sys/dev/block') / target.devno).resolve():
                raise ValueError('Partition parent identity mismatch')
            number = int((sysnode / 'partition').read_text())
            if number in result:
                raise ValueError('Duplicate partition number')
            result[number] = node['path']
        if set(result) == set(expected_numbers):
            return result
        time.sleep(.1)
    raise RuntimeError('Kernel did not expose the exact expected partition set')


def filesystem(path):
    text = command(['blkid', '--probe', '--output', 'export', path])
    fields = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    if not fields.get('UUID'):
        raise ValueError('Filesystem UUID verification failed')
    return fields


def backup_gpt(target, disk_fd, audit):
    verification = command(['sgdisk', '--verify', target.path])
    if 'No problems found.' not in verification or re.search(r'(?im)^\s*(warning|caution|error)', verification):
        raise ValueError('GPT consistency check did not pass; refusing to mutate the table')
    fd, name = tempfile.mkstemp(prefix='gpt-before-', suffix='.bin', dir=audit.path.parent)
    os.close(fd)
    result = subprocess.run(['sgdisk', '--backup=' + name, f'/proc/self/fd/{disk_fd}'],
                            pass_fds=(disk_fd,), stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=60, env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    if result.returncode or Path(name).stat().st_size < 4096:
        raise RuntimeError('GPT backup failed; no partition changes were attempted')
    with open(name, 'rb') as stream:
        backup_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        os.fsync(stream.fileno())
    record = {'path': name, 'sha256': backup_hash, 'bytes': Path(name).stat().st_size}
    audit.write('gpt-backup-verified', **record)
    return record


def validate_allocated_table(proposal, table, partitions):
    if (table.get('label') != 'gpt' or table.get('id') != proposal['table_id']
            or table.get('device') != proposal['device'] or table.get('unit') != 'sectors'
            or table.get('sectorsize') != proposal['sector_size']):
        raise ValueError('GPT disk identity or geometry changed')
    entries = table.get('partitions')
    if not isinstance(entries, list) or len(entries) != len(proposal['existing']) + 3:
        raise ValueError('Unexpected partition count after allocation')
    for original in proposal['existing']:
        if original not in entries:
            raise ValueError('Existing partition metadata changed; stop and inspect GPT recovery evidence')
    for part in proposal['new']:
        matches = [p for p in entries if p.get('node') == partitions[part['number']]]
        if len(matches) != 1:
            raise ValueError('New partition identity is ambiguous')
        actual = matches[0]
        if (actual['start'] != part['start'] or actual['size'] != part['end'] - part['start'] + 1
                or actual['type'].lower() != GUIDS[part['purpose']]):
            raise ValueError('New partition extent or type verification failed')


def prepare(target, proposal, *, nuke_it, confirmation, interactive, audit):
    """Private executor for isolated qualification. CLI release lock is separate.

    No resume may repeat this stage automatically: a failure requires reinspection
    and a new explicit erase authorization. No Stage3 or installation is claimed.
    """
    if os.geteuid() != 0:
        raise PermissionError('Storage helper requires a separate root terminal')
    if not all(shutil.which(tool) for tool in TOOLS):
        raise RuntimeError('Gentoo live media is missing required storage tools; run forge-install.sh doctor')
    audit.write('proposed', target=asdict(target), plan=proposal, commands=free_space_commands(proposal))
    fresh = inspect(target.path)
    fresh_plan = read_plan(fresh)
    authorize_space(target, fresh, proposal, fresh_plan, nuke_it=nuke_it,
                    interactive=interactive, confirmation=confirmation)
    audit.write('approved', target=asdict(fresh), confirmation=confirmation)
    lock_id = hashlib.sha256(json.dumps(asdict(target), sort_keys=True).encode()).hexdigest()[:24]
    lock_path = Path('/run') / ('gentoo-forge-' + lock_id + '.lock')
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Hold the exact opened block object while changing GPT. Descendant
        # formatting happens only after parent identity is freshly rechecked.
        disk_fd = open_target(target)
        try:
            backup = backup_gpt(target, disk_fd, audit)
            for argv in free_space_commands(proposal):
                if inspect(target.path) != target or read_plan(target) != proposal:
                    raise ValueError('Disk identity changed before partition operation')
                audit.write('command-start', argv=argv)
                # /proc/self/fd pins the approved block object across path races.
                actual = argv[:-1] + [f'/proc/self/fd/{disk_fd}']
                result = subprocess.run(actual, pass_fds=(disk_fd,), stdin=subprocess.DEVNULL,
                                        capture_output=True, timeout=60,
                                        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
                if result.returncode:
                    raise RuntimeError('GPT command failed; storage state is incomplete')
                audit.write('command-completed', argv=argv)
            fcntl.ioctl(disk_fd, 0x125f)  # BLKRRPART
        finally:
            os.close(disk_fd)
        table_after = json.loads(command(['sfdisk', '--json', target.path]))['partitiontable']
        expected_numbers = [int(re.search(r'(\d+)$', p['node'])[1]) for p in proposal['existing']]
        expected_numbers += [p['number'] for p in proposal['new']]
        partitions = partition_devices(target, expected_numbers)
        validate_allocated_table(proposal, table_after, partitions)
        prefixes = {'efi': ['mkfs.fat', '-F', '32', '-n', 'FORGE_EFI'],
                    'swap': ['mkswap', '--label', 'FORGE_SWAP'],
                    'root': ['mkfs.btrfs', '-f', '-L', 'FORGE_ROOT']}
        created = {}
        for part_plan in proposal['new']:
            number, purpose = part_plan['number'], part_plan['purpose']
            prefix = prefixes[purpose]
            if inspect(target.path) != target:
                raise ValueError('Disk became active or changed identity before formatting')
            # Verify the child belongs to the same approved parent immediately
            # before acquiring its exclusive file description.
            if partition_devices(target, expected_numbers) != partitions:
                raise ValueError('Partition identity changed before formatting')
            if json.loads(command(['sfdisk', '--json', target.path]))['partitiontable'] != table_after:
                raise ValueError('Partition table changed before formatting')
            part = partitions[number]
            # Pin the block object. Formatting programs acquire their own
            # exclusive opens; retaining a competing exclusive claim would
            # incorrectly make those built-in safety checks fail.
            part_fd = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                info = os.fstat(part_fd)
                if not stat.S_ISBLK(info.st_mode) or device_number(part) != f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}':
                    raise ValueError('Opened partition identity changed')
                opened_size = bytearray(8)
                fcntl.ioctl(part_fd, 0x80081272, opened_size)
                expected_size = (part_plan['end'] - part_plan['start'] + 1) * proposal['sector_size']
                if int.from_bytes(opened_size, sys.byteorder) != expected_size:
                    raise ValueError('Opened partition size does not match the authorized extent')
                audit.write('command-start', argv=prefix + [part])
                result = subprocess.run(prefix + [f'/proc/self/fd/{part_fd}'], pass_fds=(part_fd,),
                                        stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
                                        env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
                if result.returncode:
                    raise RuntimeError('Filesystem command failed; storage state is incomplete')
                audit.write('command-completed', argv=prefix + [part])
                created[purpose] = part
            finally:
                os.close(part_fd)
        filesystems = {purpose: filesystem(path) for purpose, path in created.items()}
        if [filesystems[p].get('TYPE') for p in ('efi', 'swap', 'root')] != ['vfat', 'swap', 'btrfs']:
            raise ValueError('Filesystem type verification failed')
        if json.loads(command(['sfdisk', '--json', target.path]))['partitiontable'] != table_after:
            raise ValueError('Partition table changed during formatting')
        audit.write('storage-filesystems-verified', target=asdict(target), partitions=created, filesystems=filesystems)
        return {'target': asdict(target), 'partitions': created, 'filesystems': filesystems, 'gpt_backup': backup,
                'stage': 'storage-filesystems-verified', 'installation': 'not started',
                'subvolumes': 'not created', 'hibernation': 'unverified', 'rollback': 'unverified'}
    except BaseException as exc:
        audit.write('incomplete', target=asdict(target), error=type(exc).__name__,
                    recovery='Do not automatically rerun. Inspect disk/audit; obtain fresh erase authorization to retry.')
        raise
    finally:
        os.close(fd)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Gentoo Forge separately invoked root storage helper')
    parser.add_argument('action', choices=('doctor', 'plan', 'storage'))
    parser.add_argument('--disk', help='Explicit canonical whole-disk path; never selected automatically')
    parser.add_argument('--nuke-it', action='store_true')
    args = parser.parse_args()
    if args.action == 'doctor':
        missing = [tool for tool in TOOLS if not shutil.which(tool)]
        print(json.dumps({'missing_tools': missing, 'physical_storage_qualified': PHYSICAL_WRITES_QUALIFIED,
                          'target': 'Gentoo live CD', 'ai_privileged': False}, indent=2))
        return bool(missing)
    if not args.disk:
        parser.error('--disk is required; no automatic disk selection')
    try:
        target = inspect(args.disk)
        proposal = read_plan(target)
        print(json.dumps({'target': asdict(target), 'plan': proposal,
                          'proposed_commands': free_space_commands(proposal)}, indent=2))
        if args.action == 'plan':
            return 0
        if not PHYSICAL_WRITES_QUALIFIED:
            raise PermissionError('Physical allocation remains locked pending preservation tests on the Gentoo live CD; NTFS will not be erased')
        if os.geteuid() != 0 or not args.nuke_it or not sys.stdin.isatty() or not sys.stdout.isatty():
            raise PermissionError('Use a separate root terminal with --nuke-it and exact interactive confirmation')
        start, end = proposal['selected_extent']
        expected = f'ALLOCATE {target.path} {target.serial} {start}-{end} {proposal["fingerprint"]}'
        print('DESTRUCTIVE STORAGE PREPARATION: new partitions in the displayed free extent will be formatted.')
        print(f'Disk: {target.path}\nModel: {target.model}\nSerial: {target.serial}\nBytes: {target.size}')
        print('Existing partitions are preserved. This does not install a bootable system.\nType exactly:\n' + expected)
        confirmation = input('Confirmation: ')
        result = prepare(target, proposal, nuke_it=args.nuke_it, confirmation=confirmation,
                         interactive=True, audit=Audit('/var/log/gentoo-forge/storage.jsonl'))
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
