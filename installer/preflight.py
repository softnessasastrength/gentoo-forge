"""Read-only production preflight. No networking setup or clock changes are made."""
from dataclasses import asdict, dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time
import urllib.request

from .storage import TOOLS, inspect


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str
    required: bool = True


def parse_memory(text):
    values = {}
    for name in ('MemTotal', 'MemAvailable'):
        match = re.search(r'^' + name + r':\s+(\d+) kB$', text, re.M)
        values[name] = int(match[1]) * 1024 if match else None
    if values['MemTotal'] is None or values['MemAvailable'] is None:
        raise ValueError('Memory measurements are incomplete')
    if not 0 <= values['MemAvailable'] <= values['MemTotal']:
        raise ValueError('Memory measurements are inconsistent')
    return values


def network_clock(now=None):
    now = time.time() if now is None else now
    request = urllib.request.Request('https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-openrc.txt', method='HEAD')
    with urllib.request.urlopen(request, timeout=15) as response:
        if not response.url.startswith('https://'):
            raise ValueError('HTTPS downgrade during network check')
        date = response.headers.get('Date')
        if not date:
            raise ValueError('Server date unavailable; cannot verify system clock')
        remote = parsedate_to_datetime(date)
        if remote.tzinfo is None:
            remote = remote.replace(tzinfo=timezone.utc)
        skew = abs(now - remote.timestamp())
        return {'https': True, 'clock_skew_seconds': round(skew), 'clock_acceptable': skew <= 86400}


def check_environment(disk=None, *, require_network=True, proc=Path('/proc'), sysfs=Path('/sys'),
                      machine=None, which=shutil.which, network=network_clock, inspect_disk=inspect):
    machine = platform.machine() if machine is None else machine
    checks = [Check('architecture', 'pass' if machine == 'x86_64' else 'fail', machine)]
    efi = sysfs / 'firmware/efi'
    checks.append(Check('uefi', 'pass' if efi.is_dir() else 'fail', 'UEFI firmware detected' if efi.is_dir() else 'Boot the Gentoo live media in UEFI mode'))
    secure = list((efi / 'efivars').glob('SecureBoot-*')) if efi.is_dir() else []
    if secure:
        try:
            data = secure[0].read_bytes()
            if len(data) != 5:
                raise ValueError('Unexpected EFI variable format')
            enabled = data[4] != 0
            checks.append(Check('secure_boot', 'fail' if enabled else 'pass',
                                'Secure Boot requires a separately qualified signing path' if enabled else 'Secure Boot disabled'))
        except (OSError, ValueError):
            checks.append(Check('secure_boot', 'fail', 'Secure Boot state cannot be verified'))
    else:
        checks.append(Check('secure_boot', 'not-checked', 'Secure Boot EFI variable unavailable', False))
    try:
        memory = parse_memory((proc / 'meminfo').read_text())
        available = memory['MemAvailable']
        checks.append(Check('memory', 'pass' if available >= 2 * 1024**3 else 'fail',
                            f'Available {available} bytes; require at least 2 GiB for bootstrap'))
        if memory['MemTotal'] < 8 * 1024**3:
            checks.append(Check('desktop_memory', 'warning', 'Source desktop builds may need reduced per-package concurrency', False))
    except (OSError, ValueError):
        checks.append(Check('memory', 'fail', 'Memory measurements unavailable'))
    missing = [tool for tool in (*TOOLS, 'tar', 'gpgv', 'chroot') if not which(tool)]
    checks.append(Check('prerequisites', 'fail' if missing else 'pass', ', '.join(missing) if missing else 'Required live-media tools are available'))
    if require_network:
        try:
            observation = network()
            checks.append(Check('network', 'pass' if observation['https'] else 'fail', 'Official Gentoo HTTPS endpoint reached (including DNS and TLS)'))
            checks.append(Check('clock', 'pass' if observation['clock_acceptable'] else 'fail',
                                f'Observed HTTP-date clock skew: {observation["clock_skew_seconds"]} seconds'))
        except Exception as exc:
            checks.append(Check('network_clock', 'fail', 'Connectivity/clock check unavailable: ' + type(exc).__name__))
    else:
        checks.append(Check('network_clock', 'not-checked', 'Explicit offline preflight; does not qualify package installation', False))
    target = None
    if disk is not None:
        try:
            target = asdict(inspect_disk(disk))
            checks.append(Check('target_identity', 'pass', target['path'] + ' serial ' + target['serial']))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            checks.append(Check('target_identity', 'fail', str(exc)))
    else:
        checks.append(Check('target_identity', 'not-checked', 'No target selected; storage execution cannot proceed', False))
    return {'version': 1, 'scope': 'read-only preflight', 'checks': [asdict(c) for c in checks],
            'environment_ready': all(c.state == 'pass' for c in checks if c.required),
            'target': target, 'writes_authorized': False, 'installation_verified': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk')
    parser.add_argument('--offline', action='store_true')
    arguments = parser.parse_args()
    result = check_environment(arguments.disk, require_network=not arguments.offline)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['environment_ready'] else 1)
