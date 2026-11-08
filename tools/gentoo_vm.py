"""Run the storage qualification inside official Gentoo live media, never host disks.

Explicitly invoked integration test, not part of unit-test discovery. Runtime
dependencies belong in setup-dev.sh; this driver installs no host packages.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import socket
import subprocess
import tarfile
import tempfile
import time

from tools.iso9660 import ISO
from tui.qemu import firmware
from installer.media import load_verified_stage3

ISO_SHA256 = '8a1ff6aec1355d055fad53d22d93b91138d09874e648811b5aa0e032536028d3'
ISO_LABEL = 'Gentoo-amd64-20261101'
ROOT = Path(__file__).resolve().parents[1]


def check_resources(memory_mib, meminfo=None):
    if type(memory_mib) is not int or not 1536 <= memory_mib <= 8192:
        raise ValueError('Gentoo qualification requires 1536–8192 MiB guest RAM')
    text = Path('/proc/meminfo').read_text() if meminfo is None else meminfo
    match = re.search(r'^MemAvailable:\s+(\d+) kB$', text, re.M)
    if not match or int(match[1]) < (memory_mib + 1024) * 1024:
        raise RuntimeError('Insufficient available RAM: reserve guest RAM plus 1 GiB for the host; use CI or another PC')


def limit_guest_files():
    # A sparse 64 GiB image must never consume all the host's actual free space.
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**3, 8 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class Serial:
    def __init__(self, connection, logfile):
        self.connection = connection
        self.connection.settimeout(1)
        self.logfile = logfile
        self.buffer = bytearray()

    def wait(self, pattern, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = re.search(pattern, self.buffer)
            if match:
                data = bytes(self.buffer[:match.end()])
                del self.buffer[:match.end()]
                return data
            try:
                chunk = self.connection.recv(65536)
            except TimeoutError:
                continue
            if not chunk:
                raise RuntimeError('Guest serial connection ended before expected evidence')
            self.logfile.write(chunk)
            self.logfile.flush()
            self.buffer.extend(chunk)
            if len(self.buffer) > 2 * 1024**2:
                raise RuntimeError('Guest serial output exceeds safety bound')
        raise TimeoutError('Guest serial deadline expired; inspect the local serial log')

    def send(self, command):
        self.connection.sendall(command.encode() + b'\n')


def payload():
    buffer = io.BytesIO()
    files = ['installer/__init__.py', 'installer/storage.py', 'installer/partition_plan.py', 'installer/bootstrap.py', 'installer/boot.py',
             'tui/__init__.py', 'tui/safety.py', 'tui/personality.py', 'tui/process.py',
             'tools/guest_storage_test.py', 'tools/install_butler.py', 'butler', 'butler_cli.py',
             'docs/BUTLER.md', 'forgeworth/AGENTS.md']
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name in files:
            archive.add(ROOT / name, arcname=name)
    return base64.b64encode(buffer.getvalue()).decode()


def qualify(iso, report_directory, accelerator='kvm', stage3=None, memory_mib=2048, network=False):
    if os.geteuid() == 0:
        raise PermissionError('Run the QEMU driver unprivileged')
    if stage3 and not network:
        raise ValueError('Stage3 boot qualification requires explicit --network for target packages')
    check_resources(memory_mib)
    iso = Path(iso).resolve()
    if not iso.is_file():
        raise ValueError('ISO must be a regular file')
    with iso.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != ISO_SHA256:
            raise ValueError('ISO differs from the signed/checksummed Gentoo fixture release')
    report_directory = Path(report_directory).absolute()
    report_directory.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='forge-gentoo-vm-', dir='/tmp') as temporary:
        directory = Path(temporary)
        image = ISO(iso)
        (directory / 'kernel').write_bytes(image.file('boot/gentoo'))
        (directory / 'initrd').write_bytes(image.file('boot/gentoo.igz'))
        code, variables = firmware()
        shutil.copyfile(variables, directory / 'vars.fd')
        subprocess.run(['qemu-img', 'create', '-f', 'qcow2', str(directory / 'fixture.qcow2'), '64G'],
                       check=True, capture_output=True, timeout=10)
        argv = ['qemu-system-x86_64', '-name', 'forge-disposable-qualification', '-machine', 'q35',
                '-accel', accelerator, '-cpu', 'host' if accelerator == 'kvm' else 'qemu64',
                '-m', str(memory_mib), '-smp', '2', '-nodefaults', '-display', 'none', '-monitor', 'none',
                '-nic', 'user,model=virtio-net-pci' if network else 'none', '-no-reboot',
                '-drive', f'if=pflash,format=raw,readonly=on,file={code}',
                '-drive', f'if=pflash,format=raw,file={directory / "vars.fd"}',
                '-kernel', str(directory / 'kernel'), '-initrd', str(directory / 'initrd'),
                '-append', f'root=live:CDLABEL={ISO_LABEL} rd.live.dir=/ rd.live.squashimg=image.squashfs cdroot {"" if network else "nodhcp"} console=ttyS0,115200n8 forge_storage_fixture=1',
                '-drive', f'file={iso},format=raw,media=cdrom,readonly=on,if=none,id=cd0',
                '-device', 'ide-cd,drive=cd0,bus=ide.1',
                '-drive', f'file={directory / "fixture.qcow2"},format=qcow2,if=none,id=target',
                '-device', 'ide-hd,drive=target,bus=ide.0,serial=FORGE-SMOKE-0001',
                '-serial', f'unix:{directory / "serial.sock"},server=on,wait=off']
        if stage3:
            stage3 = Path(stage3).resolve()
            verification = load_verified_stage3(stage3)
            archive = stage3 / verification['filename']
            argv += ['-drive', f'file={archive},format=raw,readonly=on,if=none,id=stage3',
                     '-device', 'virtio-blk-pci,drive=stage3,serial=FORGE-STAGE3']
        with (report_directory / 'qemu.log').open('wb') as errors, (report_directory / 'serial.log').open('wb') as log:
            process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True,
                                       preexec_fn=limit_guest_files)
            try:
                with socket.socket(socket.AF_UNIX) as connection:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            connection.connect(str(directory / 'serial.sock'))
                            break
                        except (FileNotFoundError, ConnectionRefusedError):
                            if process.poll() is not None or time.monotonic() >= deadline:
                                raise RuntimeError('QEMU startup failed; inspect qemu.log')
                            time.sleep(.05)
                    serial = Serial(connection, log)
                    print('Booting official Gentoo live CD in private UEFI VM...', flush=True)
                    connection.sendall(b'\n')
                    serial.wait(rb'root@livecd[^\r\n]*#', 480)
                    serial.send("export PS1='FORGE# '; export PS2=''; stty -echo -ixon -ixoff; bind 'set enable-bracketed-paste off'; echo FORGE_READY")
                    serial.wait(rb'[\r\n]+FORGE_READY[\r\n]', 10)
                    data = payload()
                    serial.send("mkdir -p /run/forge-code; cd /run/forge-code; base64 -d <<'FORGE_PAYLOAD' | tar xz")
                    for start in range(0, len(data), 76):
                        serial.send(data[start:start + 76])
                    serial.send('FORGE_PAYLOAD')
                    if stage3:
                        serial.send('export FORGE_STAGE3_SIZE=' + str(verification['size']))
                        serial.send('export FORGE_STAGE3_SHA256=' + verification['sha256'])
                    serial.send('python3 -m tools.guest_storage_test; echo FORGE_TEST_EXIT:$?')
                    print('Running actual allocation/format/preservation checks inside Gentoo...', flush=True)
                    output = serial.wait(rb'FORGE_TEST_EXIT:[0-9]+', 3000)
                    status = int(re.search(rb'FORGE_TEST_EXIT:([0-9]+)', output)[1])
                    match = re.search(rb'FORGE_RESULT:(\{[^\r\n]+\})', output)
                    if status or not match:
                        raise RuntimeError('Gentoo qualification failed; inspect serial.log')
                    result = json.loads(match[1])
                    (report_directory / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
                    # Keep only evidence; never retain/attach a host block device.
                    serial.send('poweroff')
                    process.wait(timeout=60)
                    if stage3:
                        print('Booting installed disk with ISO, Stage3 device and direct kernel detached...', flush=True)
                        socket_path = directory / 'installed.sock'
                        boot_argv = ['qemu-system-x86_64', '-machine', 'q35', '-accel', accelerator,
                                     '-cpu', 'host' if accelerator == 'kvm' else 'qemu64', '-m', str(memory_mib), '-smp', '2',
                                     '-nodefaults', '-display', 'none', '-monitor', 'none', '-nic', 'user,model=virtio-net-pci' if network else 'none', '-no-reboot',
                                     '-drive', f'if=pflash,format=raw,readonly=on,file={code}',
                                     '-drive', f'if=pflash,format=raw,file={directory / "vars.fd"}',
                                     '-drive', f'file={directory / "fixture.qcow2"},format=qcow2,if=none,id=target',
                                     '-device', 'ide-hd,drive=target,bus=ide.0,serial=FORGE-SMOKE-0001',
                                     '-serial', f'unix:{socket_path},server=on,wait=off']
                        process = subprocess.Popen(boot_argv, stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True,
                                                   preexec_fn=limit_guest_files)
                        with socket.socket(socket.AF_UNIX) as installed:
                            deadline = time.monotonic() + 10
                            while not socket_path.exists():
                                if process.poll() is not None or time.monotonic() > deadline:
                                    raise RuntimeError('Installed boot QEMU startup failed')
                                time.sleep(.05)
                            installed.connect(str(socket_path))
                            boot_serial = Serial(installed, log)
                            observed = boot_serial.wait(rb'FORGE_BOOT_RESULT:\{[^\r\n]+\}', 480)
                            marker = re.search(rb'FORGE_BOOT_RESULT:(\{[^\r\n]+\})', observed)
                            evidence = json.loads(marker[1])
                            if not evidence.get('passed') or evidence.get('root_uuid') != result['filesystems']['root']['UUID']:
                                raise RuntimeError('Installed boot verification failed; inspect serial.log')
                            process.wait(timeout=60)
                            result['installed_system_boot'] = evidence
                            result['qualification'] = 'minimal Stage3 UEFI boot with target kernel packages; full Handbook path incomplete'
                            (report_directory / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n')
                    return result
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--accel', choices=('kvm', 'tcg'), default='kvm')
    parser.add_argument('--stage3', type=Path)
    parser.add_argument('--memory-mib', type=int, default=2048)
    parser.add_argument('--network', action='store_true', help='Allow outbound QEMU user networking for authenticated target packages')
    args = parser.parse_args()
    print(json.dumps(qualify(args.iso, args.report, args.accel, args.stage3, args.memory_mib, args.network), indent=2))
