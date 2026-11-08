"""Read-only VirtualBox smoke-test guidance, evidence and report model.

No VM creation, package installation, disk writes or model command dispatch.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from .process import run
from .safety import validate_target

GIB = 1024**3
STATUSES = ('pending', 'completed', 'failed', 'skipped')


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    purpose: str
    guidance: str


STEPS = (
    Step('host', 'Verify host resources', 'Avoid exhausting the machine running VirtualBox.',
         'Run detection in host role on the actual Linux host, choosing the directory that will hold the VDI. '
         'Inside a guest, host resources cannot be measured. On other hosts, check Task Manager or Activity Monitor '
         'and free space at the VM storage location; record measurements as user-reported evidence. '
         'Aim for 4–6 vCPUs, 8–12 GiB RAM and 80–120 GiB disk only when headroom is verified.'),
    Step('vm', 'Create disposable VM', 'Separate experimental installation from host storage.',
         'In VirtualBox Manager choose New → Linux → Gentoo (64-bit) or Other Linux (64-bit). '
         'Skip unattended installation. Allocate only resources approved by the host check. '
         'Create a NEW dynamically allocated VDI, 80–120 GiB; never attach raw host disks. '
         'Enable EFI in Settings → System. Use NAT with cable connected. '
         'Use VMSVGA and 128 MiB video memory; start with 3D acceleration disabled.'),
    Step('iso', 'Attach ISO and boot EFI', 'Boot trusted installation media in the intended firmware mode.',
         'Download the current amd64 Gentoo installation ISO and verify its signature/digest using the Handbook. '
         'Settings → Storage → optical drive → Choose a disk file → select ISO. '
         'Set optical before hard disk in boot order and start the VM. '
         'Suggested, NOT executed: test -d /sys/firmware/efi && echo UEFI. '
         'An EFI shell often means missing ISO or incorrect boot order; use the firmware boot manager.'),
    Step('launch', 'Launch FORGEWORTH', 'Make the guide and read-only inspection available in the guest.',
         'In the ISO environment establish networking, obtain this repository, install Python/venv and Textual '
         'as described in docs/FORGEWORTH-TUI.md, then run python -m tui.app --virtualbox. '
         'Keep the TUI unprivileged; do not enable Codex as root. The legacy menu is available if Textual is absent. '
         'Keep the report on explicitly chosen persistent storage or copy it out before reboot; ISO /tmp is volatile.'),
    Step('inspect', 'Run safe preflight', 'Inspect the current machine without changing disks.',
         'Use Preflight in the main panel. Detect also collects bounded read-only DMI, PCI, lsblk, '
         'route, init and filesystem observations. Guest observations do not verify the host or the installed system.'),
    Step('snapshot', 'Take pre-install VM snapshot', 'Provide an additional recovery point.',
         'In VirtualBox Manager take a named snapshot before destructive stages. Confirm the attached VDI belongs '
         'to this disposable VM. A snapshot is not a substitute for verifying the exact target disk.'),
    Step('target', 'Select and validate target', 'Prevent accidental loss of host or guest data.',
         'Explicitly select a whole disk from the detected list, inspect capacity/model/serial/WWN/UUID, '
         'and use Validate selection. Missing identifiers, unknown mount/swap state or mounted descendants block validation. '
         'Validation is read-only and grants NO erase permission. VirtualBox detection never proves disposability. '
         'Future writes require fresh physical-equivalent checks, --nuke-it and a separate exact interactive confirmation.'),
    Step('install', 'Complete installation — unavailable', 'Exercise the actual installer in a later milestone.',
         'Bootstrap through finalization are LOCKED in this release. Record this step skipped with that reason. '
         'Do not substitute a simulated progress bar for an installation. No --nuke-it execution path is enabled.'),
    Step('reboot', 'Reboot from installed VDI', 'Prove the installed disk boots without the ISO.',
         'Only after a real installation: export/copy reports out, shut down, detach the ISO, '
         'keep EFI enabled and start from the VDI. Record firmware/GRUB errors exactly. This release cannot install yet.'),
    Step('uefi', 'Validate installed UEFI', 'Confirm the installed system used UEFI.',
         'After booting the VDI without ISO, suggested NOT executed: test -d /sys/firmware/efi; '
         'efibootmgr -v. Compare entries and ESP identity with the selected disk. ISO EFI detection is insufficient.'),
    Step('grub', 'Validate GRUB', 'Verify kernel and initramfs entries actually boot.',
         'Record a successful VDI boot and inspect GRUB entries/root UUIDs. Suggested NOT executed: '
         'findmnt /; cat /proc/cmdline; ls /boot. On failure preserve exact error, ESP mounts and grub-install output. '
         'Use the ISO to inspect read-only first; never run a guessed repair command from a model.'),
    Step('openrc', 'Validate OpenRC', 'Verify the installed init and services independently.',
         'On the installed system, suggested NOT executed: ps -p 1 -o comm=; rc-status; rc-update show. '
         'Record failures rather than assuming package installation enabled services.'),
    Step('network', 'Validate networking', 'Check routing, DNS and connectivity separately.',
         'Suggested NOT executed: ip -br address; ip route; getent hosts gentoo.org; nmcli general status. '
         'A route alone does not prove DNS or internet connectivity. NAT needs cable connected in VirtualBox.'),
    Step('storage', 'Validate installed storage', 'Confirm mounts, swap and independent home subvolume.',
         'Suggested NOT executed: findmnt /; findmnt /home; lsblk -f; swapon --show; btrfs subvolume list /. '
         'Compare disk identifiers and inspect ESP, 20 GiB swap and Btrfs layout independently.'),
    Step('plasma', 'Validate virtual graphics and Plasma', 'Exercise the virtual adapter rather than physical AMD settings.',
         'Use the detected PCI display device. VMSVGA generally uses vmwgfx/Mesa; VBoxVGA/VBoxSVGA may use vboxvideo. '
         'Do not force AMDGPU or RADV merely because the physical target has Radeon hardware. '
         'Verify available drivers against the running kernel. After SDDM login check Plasma, '
         'Wayland and XWayland separately. Suggested NOT executed: lspci -nnk; echo "$XDG_SESSION_TYPE". '
         'A console ISO cannot verify desktop behavior. Try X11 separately if Wayland is unsupported.'),
    Step('hibernate', 'Test hibernation separately', 'Prove guest resume rather than host VM saved state.',
         'Default UNVERIFIED. VirtualBox Save State is not guest hibernation. Verify guest ACPI support, '
         'swap UUID/capacity and dracut resume configuration; snapshot first and test only the disposable VM. '
         'Record unsupported as skipped with evidence. Do not infer success from swap availability.'),
    Step('rollback', 'Test Btrfs rollback separately', 'Prove root recovery while preserving separate home.',
         'Default UNVERIFIED. Snapshot a known-good disposable VM; verify independent Snapper root/home configs '
         'and GRUB root-subvolume handling. Boot a restored writable root and verify data/home preservation. '
         'Snapshot creation or GRUB menu presence alone is not rollback success. Keep ISO recovery available.'),
)
STEP_MAP = {step.key: step for step in STEPS}


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(text):
    """Bound report text and redact common credential forms; users must still review exports."""
    text = re.sub(r'(?i)(authorization\s*:\s*bearer\s+|(?:api[_-]?key|token|password|secret)\s*[=:]\s*)\S+', r'\1[REDACTED]', str(text))
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    return ''.join(c for c in text[:12000] if c in '\n\t' or c.isprintable())


def virtualization(dmi):
    values = [str(value).strip() for value in dmi.values() if value]
    if any('virtualbox' in value.lower() or 'innotek' in value.lower() for value in values):
        return 'detected'
    return 'not detected' if values else 'cannot be determined'


def recommend(resources, role, detection):
    if role != 'host' or detection == 'detected':
        return {'status': 'unverified', 'reason': 'Guest resources cannot verify host headroom; run on the actual host.'}
    try:
        cpu = resources['cpus']
        load = resources['load_1m']
        ram = resources['available_bytes']
        free = resources['storage_free_bytes']
        if any(value is None or value < 0 for value in (cpu, load, ram, free)):
            raise ValueError()
        spare = cpu - math.ceil(load) - 2
        if spare < 4 or ram < 12 * GIB or free < 90 * GIB:
            return {'status': 'insufficient', 'reason': 'Need 4 spare vCPUs plus 2 reserved, 8 GiB guest RAM plus 4 GiB reserved, and 80 GiB disk plus 10 GiB free.'}
        return {'status': 'conditional', 'vcpus': min(6, spare),
                'ram_gib': 12 if ram >= 16 * GIB else 8,
                'disk_gib': 120 if free >= 130 * GIB else 80,
                'reason': 'Local host measurements at detection time only. Confirm host role and competing workloads. Dynamic VDI growth still needs real free space.'}
    except (KeyError, TypeError, ValueError, OverflowError):
        return {'status': 'unverified', 'reason': 'Host resource measurements are incomplete; no allocation recommended.'}


def graphics_adapter(output):
    """Keep driver lines attached to their PCI display function, not other devices."""
    blocks = []
    current = []
    for line in output.splitlines() + ['END']:
        if line and not line[0].isspace():
            if current and any(term in current[0].lower() for term in ('vga', 'display controller', '3d controller')):
                blocks.append('\n'.join(current))
            current = [line]
        elif current:
            current.append(line)
    return '\n\n'.join(blocks)


def local_facts(storage_path):
    """Runs in a collector process; never traverses arbitrary device contents."""
    def read(path):
        try:
            return Path(path).read_text()[:4096].strip()
        except (OSError, UnicodeError):
            return None
    dmi = {key: read('/sys/class/dmi/id/' + key) for key in ('sys_vendor', 'product_name', 'board_vendor')}
    available = None
    meminfo = read('/proc/meminfo') or ''
    match = re.search(r'^MemAvailable:\s+(\d+) kB$', meminfo, re.M)
    if match:
        available = int(match[1]) * 1024
    try:
        free = shutil.disk_usage(storage_path).free
    except OSError:
        free = None
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = None
    swaps_text = read('/proc/swaps')
    swaps = None if swaps_text is None else [line.split()[0] for line in swaps_text.splitlines()[1:] if line.split()]
    return {'dmi': dmi, 'virtualization': virtualization(dmi),
            'efi': Path('/sys/firmware/efi').is_dir(), 'swaps': swaps,
            'container_hint': Path('/.dockerenv').exists() or Path('/run/.containerenv').exists(),
            'resources': {'cpus': os.cpu_count(),
                          'total_memory_bytes': int(re.search(r'^MemTotal:\s+(\d+) kB$', meminfo, re.M)[1]) * 1024 if re.search(r'^MemTotal:\s+(\d+) kB$', meminfo, re.M) else None, 'load_1m': load, 'available_bytes': available,
                          'storage_free_bytes': free, 'storage_path': str(Path(storage_path).absolute())}}


PROBES = {
    'disks': ['lsblk', '--json', '--bytes', '--paths', '--output', 'NAME,PATH,TYPE,SIZE,MODEL,SERIAL,WWN,UUID,RO,MOUNTPOINTS'],
    'graphics': ['lspci', '-nnk'],
    'routes': ['ip', '-json', 'route'],
    'root_mount': ['findmnt', '--json', '--output', 'SOURCE,TARGET,FSTYPE,OPTIONS', '/'],
    'init': ['ps', '-p', '1', '-o', 'comm='],
}


async def collect(role='guest', storage_path='.'):
    if role not in ('host', 'guest'):
        raise ValueError('Role must be host or guest')
    facts = {'virtualization': 'cannot be determined', 'errors': []}
    try:
        code, output = await run([sys.executable, '-m', 'tui.virtualbox', '--facts', storage_path],
                                 cwd=Path(__file__).resolve().parent.parent, timeout=5)
        if code:
            raise ValueError('Local collector failed')
        facts.update(json.loads(output))
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
        facts['errors'].append('facts: ' + type(exc).__name__)
    async def probe(name, argv):
        try:
            code, output = await run(argv, timeout=8, limit=128000)
            return name, {'argv': argv, 'exit_code': code, 'output': clean(output), 'source': 'observed'}
        except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
            return name, {'argv': argv, 'exit_code': None, 'error': type(exc).__name__, 'source': 'observed'}
    results = await asyncio.gather(*(probe(name, argv) for name, argv in PROBES.items()))
    diagnostics = dict(results)
    inventory = None
    if diagnostics['disks'].get('exit_code') == 0:
        try:
            # Truncated or malformed excerpts cannot serve as validation inventories.
            inventory = json.loads(diagnostics['disks']['output'])
        except ValueError:
            facts['errors'].append('disks: invalid or truncated JSON')
    for name, result in diagnostics.items():
        if result.get('exit_code') != 0:
            facts['errors'].append(name + ': ' + result.get('error', 'exit ' + str(result.get('exit_code'))))
    graphics = diagnostics['graphics'].get('output', '')
    facts.update({'role': role, 'observed_at': now(), 'diagnostics': diagnostics,
                  'inventory': inventory, 'graphics': graphics_adapter(graphics),
                  'recommendation': recommend(facts.get('resources', {}), role, facts['virtualization'])})
    if facts.get('container_hint'):
        facts['recommendation'] = {'status': 'unverified', 'reason': 'Container detected; local limits do not establish physical host headroom.'}
    return facts


def validate_selection(facts, path, expected=None):
    if facts.get('role') != 'guest':
        raise ValueError('Target selection is disabled in host role. Collect guest diagnostics first.')
    inventory = facts.get('inventory')
    if inventory is None:
        raise ValueError('Disk inventory is unavailable')
    # All mounted descendants are rejected by the shared validator, including
    # mapper/RAID children shown by lsblk. Unknown root/swap state fails closed.
    mount = facts.get('diagnostics', {}).get('root_mount', {})
    if mount.get('exit_code') != 0:
        raise ValueError('Root mount ancestry is unavailable')
    try:
        roots = json.loads(mount['output'])['filesystems']
        if not roots or roots[0]['target'] != '/' or not roots[0]['source']:
            raise ValueError('Root mount data is incomplete')
        if not roots[0]['source'].startswith('/dev/'):
            raise ValueError('Root mount data is incomplete')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Root mount data is incomplete') from exc
    swaps = facts.get('swaps')
    # Swapfiles and mapper paths need an additional ancestry resolver, not a guess.
    if swaps is not None and any(not re.fullmatch(r'/dev/(?:sd[a-z]+\d*|vd[a-z]+\d*|nvme\d+n\d+(?:p\d+)?)', path) for path in swaps):
        raise ValueError('Swap ancestry cannot be resolved; target validation blocked')
    # A syntactically plausible /dev source is not evidence of resolved ancestry.
    # Btrfs findmnt sources can contain a subvolume suffix, e.g. /dev/sda3[/@].
    root_path = roots[0]['source'].split('[', 1)[0]
    known = set()
    pending = list(inventory.get('blockdevices', [])) if isinstance(inventory, dict) else []
    while pending:
        node = pending.pop()
        if not isinstance(node, dict) or not isinstance(node.get('path'), str):
            raise ValueError('Device ancestry inventory is malformed')
        known.add(node['path'])
        children = node.get('children', [])
        if not isinstance(children, list):
            raise ValueError('Device ancestry inventory is malformed')
        pending.extend(children)
    if root_path not in known or swaps is None or any(device not in known for device in swaps):
        raise ValueError('Root or swap ancestry is unresolved; target validation blocked')
    disk = validate_target(inventory, path, [root_path], swaps)
    if expected is not None:
        identity = {'path': disk.path, 'size': disk.size, 'model': disk.model, 'serial': disk.serial}
        proposal = {key: expected.get(key) for key in identity}
        for key in ('serial', 'model'):
            proposal[key] = (proposal[key] or '').strip()
        if proposal != identity:
            raise ValueError('Disk identity changed after selection. Refresh and explicitly select again.')
    return disk


class SmokeReport:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.suffix != '.json':
            raise ValueError('Report path must end in .json')
        self.data = {'schema_version': 1, 'created_at': now(), 'configuration': {'writes_enabled': False, 'vm_defaults': {'source': 'suggested, not observed', 'vcpus': '4–6', 'ram_gib': '8–12', 'disk_gib': '80–120', 'firmware': 'EFI', 'network': 'NAT', 'graphics': 'VMSVGA, 3D initially off'}},
                     'observations': [], 'selected_disk': None, 'disk_validation': 'pending',
                     'steps': {step.key: {'status': 'pending', 'source': 'none', 'evidence': ''} for step in STEPS},
                     'errors': [], 'installation_smoke_test': 'unverified'}
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if saved.get('schema_version') != 1 or set(saved.get('steps', {})) != set(STEP_MAP):
                raise ValueError('Unsupported or incomplete VirtualBox report')
            if any(result.get('status') not in STATUSES or result.get('source') not in ('none', 'observed', 'user-reported')
                   for result in saved['steps'].values()):
                raise ValueError('Invalid step result')
            self.data = saved
            # Reports never restore authorization or a live device validation.
            self.data['configuration']['writes_enabled'] = False
            self.data['disk_validation'] = 'pending: revalidate after restart'
            self.data['installation_smoke_test'] = 'unverified'

    def record(self, key, status, evidence, source='user-reported'):
        if key not in STEP_MAP or status not in STATUSES or source not in ('user-reported', 'observed'):
            raise ValueError('Invalid step result')
        if status != 'pending' and not evidence.strip():
            raise ValueError('Evidence or a reason is required')
        if source == 'observed' and key != 'inspect':
            raise ValueError('Only safe preflight has an automated step verifier')
        self.data['steps'][key] = {'status': status, 'source': source, 'evidence': clean(evidence), 'updated_at': now()}
        self.save()

    def observe(self, facts):
        self.data['observations'] = (self.data['observations'] + [facts])[-10:]
        self.data['configuration']['last_collection_role'] = facts.get('role')
        self.data['disk_validation'] = 'pending: diagnostics refreshed'
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data['updated_at'] = now()
        # Constant outcome: no write executor exists in this milestone.
        self.data['installation_smoke_test'] = 'unverified'
        fd, temp = tempfile.mkstemp(prefix='.vbox-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(self.data, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def summary(self):
        counts = {status: sum(r['status'] == status for r in self.data['steps'].values()) for status in STATUSES}
        return ('VirtualBox guided workflow: ' + ', '.join(f'{n} {status}' for status, n in counts.items())
                + '. Complete installation smoke test: UNVERIFIED. Disk writes: LOCKED.')

    def export(self):
        self.save()
        text = self.summary() + '\n\nCompleted user-reported steps are attestations, not automated verification.\n'
        text += '\nDisk validation: ' + self.data['disk_validation'] + '\n'
        if self.data['observations']:
            latest = self.data['observations'][-1]
            text += '\nLatest local observations: ' + json.dumps({key: latest.get(key) for key in
                        ('observed_at', 'role', 'virtualization', 'efi', 'graphics', 'errors')}) + '\n'
        text += '\nDetailed configuration, command results and logs are in the adjacent JSON report.\n'
        for step in STEPS:
            result = self.data['steps'][step.key]
            text += f'\n{step.title}: {result["status"]} ({result["source"]})\n{result["evidence"]}\n'
        target = self.path.with_suffix('.txt')
        fd, temp = tempfile.mkstemp(prefix='.vbox-summary-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(text)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return self.path, target


def offline_answer(question, report, serious=False):
    q = question.lower()
    if any(term in q for term in ('disk', 'drive', 'erase', 'wipe', 'safe to', 'nuke', 'data loss', 'format', 'destruct', 'partition')):
        key = 'target'
    elif 'grub' in q or 'recover' in q or 'recovery' in q:
        key = 'grub'
    elif 'boot' in q or 'iso' in q:
        key = 'iso'
    elif 'doing' in q or 'installer' in q or 'progress' in q:
        key = 'install'
    elif 'graphic' in q or 'plasma' in q or 'radeon' in q:
        key = 'plasma'
    elif 'hibern' in q:
        key = 'hibernate'
    elif 'rollback' in q or 'snapshot' in q:
        key = 'rollback'
    elif 'network' in q:
        key = 'network'
    else:
        key = 'vm'
    step = STEP_MAP[key]
    tone = '' if key == 'target' or serious else 'Very good, sir. Let us inspect the evidence before blaming the furniture. '
    return (tone + step.guidance + '\nRecorded step: ' + report.data['steps'][key]['status']
            + '. Evidence (' + report.data['steps'][key]['source'] + '): '
            + report.data['steps'][key]['evidence'][:1000]
            + '. Disk validation: ' + report.data['disk_validation'] + '.\n'
            + ('Latest LOCAL observations (not installed-system verification): '
               + json.dumps({k: report.data['observations'][-1].get(k) for k in
                             ('observed_at', 'role', 'virtualization', 'efi', 'graphics', 'errors')})[:2000]
               if report.data['observations'] else 'No diagnostics collected yet.')
            + '\n' + report.summary())


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--facts':
        print(json.dumps(local_facts(sys.argv[2])))
    else:
        raise SystemExit('Internal read-only collector: --facts STORAGE_DIRECTORY')

