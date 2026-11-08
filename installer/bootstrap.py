"""Stage3 validation, owned target mounts and supervised chroot primitives.

No disk selection or destructive authorization lives here. Callers must supply
the verified storage result produced by the separate root storage operation.
"""
from contextlib import AbstractContextManager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile

from .storage import Target, command, filesystem, inspect


def write_target(root, relative, text, mode=0o644):
    root = Path(root).resolve()
    relative = PurePosixPath(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Target configuration path escapes root')
    target = root / str(relative)
    if not target.parent.resolve().is_relative_to(root):
        raise ValueError('Target configuration parent escapes root')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.forge-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def validate_archive(path):
    count = 0
    names, symlinks = [], set()
    with tarfile.open(path, 'r|xz') as archive:
        for member in archive:
            count += 1
            if count > 500000:
                raise ValueError('Stage3 member count exceeds bound')
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or '.forgeworth-stage3.tar.xz' in name.parts:
                raise ValueError('Unsafe Stage3 member path')
            device = member.ischr() and str(name) in ('dev/null', 'dev/console') and (member.devmajor, member.devminor) == ({'dev/null': (1, 3), 'dev/console': (5, 1)}[str(name)])
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk() or device):
                raise ValueError('Unexpected special file in Stage3')
            normalized = posixpath.normpath(str(name))
            names.append(normalized)
            if member.issym() or member.islnk():
                link = member.linkname
                if member.islnk() and link.startswith('/'):
                    raise ValueError('Absolute Stage3 hard link')
                resolved = posixpath.normpath(posixpath.join(str(name.parent) if member.issym() and not link.startswith('/') else '', link.lstrip('/')))
                if resolved == '..' or resolved.startswith('../'):
                    raise ValueError('Stage3 link escapes target root')
                if member.issym():
                    symlinks.add(normalized)
    # Absolute in-target service links are normal in Gentoo Stage3. They may be
    # created, but no archive entry may write through any symlink ancestor.
    for name in names:
        parts = PurePosixPath(name).parts
        if any('/'.join(parts[:i]) in symlinks for i in range(1, len(parts))):
            raise ValueError('Stage3 archive writes through a symlink ancestor')
    if not count:
        raise ValueError('Empty Stage3 archive')
    return count


def verify_archive(path, expected_sha256, expected_size):
    path = Path(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.is_symlink():
        raise ValueError('Stage3 extraction requires a regular verified archive')
    with path.open('rb') as stream:
        if os.fstat(stream.fileno()).st_size != expected_size:
            raise ValueError('Stage3 size changed')
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_sha256:
            raise ValueError('Stage3 digest changed')
    return validate_archive(path)


def extract(path, root, expected_sha256, expected_size):
    if os.geteuid() != 0:
        raise PermissionError('Numeric-owner Stage3 extraction requires the separate root engine')
    root = Path(root).resolve()
    if not os.path.ismount(root) or root == Path('/'):
        raise ValueError('Extraction requires an explicit mounted target, never the live root')
    verify_archive(path, expected_sha256, expected_size)
    command(['tar', '--xattrs-include=*.*', '--numeric-owner', '-xJpf', str(path), '-C', str(root)], timeout=600)
    for name in ('etc/gentoo-release', 'usr/bin/bash', 'etc/portage/make.conf'):
        if not (root / name).is_file():
            raise RuntimeError('Stage3 extraction verification failed: ' + name)


class TargetMounts(AbstractContextManager):
    def __init__(self, storage):
        self.storage = storage
        self.temporary = None
        self.mounts = []
        self.swap_active = False

    def mount(self, argv, target, recursive=False):
        command(argv)
        self.mounts.append((Path(target), recursive))

    def __enter__(self):
        if os.geteuid() != 0:
            raise PermissionError('Target mount context requires separate root execution')
        if inspect(self.storage['target']['path']) != Target(**self.storage['target']):
            raise ValueError('Storage identity changed before mounting')
        for role in ('root', 'efi', 'swap'):
            found = filesystem(self.storage['partitions'][role])
            expected = self.storage['filesystems'][role]
            if (found['UUID'], found['TYPE']) != (expected['UUID'], expected['TYPE']):
                raise ValueError('Target filesystem identity changed')
        # /run is later recursively bind-mounted into the target. Keeping the
        # target itself beneath /run would recursively include its own mount.
        # Never use TemporaryDirectory around a mounted filesystem: its GC
        # finalizer can recursively erase the installation after failed unmounts.
        self.temporary = tempfile.mkdtemp(prefix='forge-target-', dir='/mnt')
        self.root = Path(self.temporary)
        try:
            self.mount(['mount', '-t', 'btrfs', '-o', 'subvol=@,nodev,nosuid',
                        self.storage['partitions']['root'], str(self.root)], self.root)
            for relative, subvolume in (('home', '@home'), ('.snapshots', '@snapshots'), ('home/.snapshots', '@home_snapshots')):
                target = self.root / relative
                target.mkdir(parents=True, exist_ok=True)
                self.mount(['mount', '-t', 'btrfs', '-o', f'subvol={subvolume},nodev,nosuid',
                            self.storage['partitions']['root'], str(target)], target)
            efi = self.root / 'efi'
            efi.mkdir()
            self.mount(['mount', '-t', 'vfat', '-o', 'umask=0077,nodev,nosuid',
                        self.storage['partitions']['efi'], str(efi)], efi)
            return self
        except BaseException:
            self.__exit__(*__import__('sys').exc_info())
            raise

    def activate_swap(self):
        """Opt-in use of only the already authorized installation swap device."""
        if not self.mounts or self.swap_active:
            raise ValueError('Swap activation requires an active target mount context')
        path = self.storage['partitions']['swap']
        observed = filesystem(path)
        expected = self.storage['filesystems']['swap']
        if observed['TYPE'] != 'swap' or observed['UUID'] != expected['UUID']:
            raise ValueError('Installation swap identity changed')
        command(['swapon', '--priority', '10', path])
        self.swap_active = True

    def pseudo(self, *, require_dns=True):
        for name in ('proc', 'sys', 'dev', 'run'):
            target = self.root / name
            target.mkdir(exist_ok=True)
            if name == 'proc':
                self.mount(['mount', '-t', 'proc', 'proc', str(target)], target)
            else:
                self.mount(['mount', '--rbind', '/' + name, str(target)], target, recursive=True)
                command(['mount', '--make-rslave', str(target)])
        try:
            resolver = Path('/etc/resolv.conf').read_text()
        except FileNotFoundError as exc:
            if require_dns:
                raise RuntimeError('Live DNS configuration is missing; establish networking before package installation') from exc
            resolver = '# Explicit offline fixture: no DNS resolver configured.\n'
        write_target(self.root, 'etc/resolv.conf', resolver)

    def chroot(self, argv, timeout=300):
        if not argv or not argv[0].startswith('/'):
            raise ValueError('Chroot programs require explicit absolute paths')
        # Compilation output can be enormous. Spool it outside RAM, and retain
        # a bounded diagnostic tail on failure instead of hiding Portage errors.
        with tempfile.TemporaryFile(dir=self.root / 'var/tmp') as output:
            process = subprocess.Popen(['chroot', str(self.root), *argv],
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True,
                                       env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
            try:
                returncode = process.wait(timeout=timeout)
            finally:
                # Cover timeout, cancellation and children left after leader exit.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            length = output.tell()
            output.seek(max(0, length - 16384))
            tail = output.read().decode('utf-8', errors='replace')
            # Untrusted compiler/package text must not emit terminal controls.
            tail = ''.join(c if c in '\n\t' or c.isprintable() else '?' for c in tail)
            if returncode:
                raise RuntimeError(f'Target {Path(argv[0]).name} failed with exit {returncode}:\n{tail}')
            return tail

    def __exit__(self, *args):
        failures = []
        if self.swap_active:
            try:
                command(['swapoff', self.storage['partitions']['swap']], timeout=120)
                self.swap_active = False
            except (OSError, RuntimeError, subprocess.SubprocessError):
                failures.append('swap ' + self.storage['partitions']['swap'])
        remaining_mounts = []
        for target, recursive in reversed(self.mounts):
            try:
                command(['umount', *(['--recursive'] if recursive else []), str(target)])
            except (OSError, RuntimeError, subprocess.SubprocessError):
                failures.append(str(target))
                remaining_mounts.append((target, recursive))
        self.mounts = list(reversed(remaining_mounts))
        if failures:
            raise RuntimeError('Target cleanup incomplete; inspect and unmount manually: ' + ', '.join(failures))
        if self.temporary:
            os.rmdir(self.temporary)  # Empty mountpoint only; never recursive cleanup.
        return False


def base_configuration(root, storage):
    fs = storage['filesystems']
    btrfs = fs['root']['UUID']
    lines = [f'UUID={btrfs} / btrfs subvol=@,compress=zstd,noatime 0 0',
             f'UUID={btrfs} /home btrfs subvol=@home,compress=zstd,noatime 0 0',
             f'UUID={btrfs} /.snapshots btrfs subvol=@snapshots,compress=zstd,noatime 0 0',
             f'UUID={btrfs} /home/.snapshots btrfs subvol=@home_snapshots,compress=zstd,noatime 0 0',
             f'UUID={fs["efi"]["UUID"]} /efi vfat umask=0077 0 0',
             f'UUID={fs["swap"]["UUID"]} none swap sw 0 0']
    write_target(root, 'etc/fstab', '\n'.join(lines) + '\n')
    write_target(root, 'etc/conf.d/hostname', 'hostname="forge"\n')
    write_target(root, 'etc/hostname', 'forge\n')
    write_target(root, 'etc/hosts', '127.0.0.1 localhost forge\n::1 localhost forge\n')
    write_target(root, 'etc/locale.gen', 'en_US.UTF-8 UTF-8\n')
    write_target(root, 'etc/env.d/02locale', 'LANG="en_US.UTF-8"\nLC_COLLATE="C.UTF-8"\n')
    write_target(root, 'etc/timezone', 'America/New_York\n')
    timezone = Path(root) / 'usr/share/zoneinfo/America/New_York'
    if timezone.is_file():
        destination = Path(root) / 'etc/localtime'
        destination.unlink(missing_ok=True)
        shutil.copyfile(timezone, destination)
