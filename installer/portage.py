"""Validated target profile and compiler configuration; never a shell template API."""
from dataclasses import dataclass
from pathlib import Path
import re

from .bootstrap import write_target

PROFILES = {
    'minimal': 'default/linux/amd64/23.0',
    'plasma': 'default/linux/amd64/23.0/desktop/plasma',
}


def profile_path(description, edition):
    """Select an exact stable OpenRC multilib profile from authenticated metadata."""
    if edition not in PROFILES:
        raise ValueError('Supported editions are minimal and plasma')
    wanted = PROFILES[edition]
    matches = []
    for line in description.splitlines():
        fields = line.split('#', 1)[0].split()
        if len(fields) == 3 and fields[:2] == ['amd64', wanted]:
            matches.append(fields[2])
    if matches != ['stable']:
        raise ValueError('Requested profile is missing, ambiguous or not stable')
    return wanted


def select_profile(target, edition='minimal'):
    profiles = target.root / 'var/db/repos/gentoo/profiles'
    if not profiles.resolve().is_relative_to(target.root.resolve()):
        raise ValueError('Repository profiles escape the installation target')
    wanted = profile_path((profiles / 'profiles.desc').read_text(), edition)
    if not (profiles / wanted).is_dir():
        raise ValueError('Selected profile directory is unavailable')
    target.chroot(['/usr/bin/eselect', 'profile', 'set', wanted], timeout=120)
    # Verify from inside the chroot: valid absolute target symlinks must not be
    # accidentally resolved against the development/live host filesystem.
    probe = "import os,portage; p=os.path.realpath('/etc/portage/make.profile'); assert p == '/var/db/repos/gentoo/profiles/" + wanted + "'; assert portage.settings['ARCH']=='amd64'; assert {'amd64','x86'}.issubset(set(portage.settings.get('MULTILIB_ABIS','').split())); assert 'systemd' not in portage.settings['USE'].split(); print(p)"
    target.chroot(['/usr/bin/python3', '-c', probe], timeout=120)
    return wanted


@dataclass(frozen=True)
class CompilerSettings:
    march: str = 'x86-64'
    jobs: int = 6
    load: int = 6

    @classmethod
    def for_cpu(cls, cpuinfo, jobs=6, load=6):
        vendors = re.findall(r'^vendor_id\s*:\s*(.+)$', cpuinfo, re.M)
        names = re.findall(r'^model name\s*:\s*(.+)$', cpuinfo, re.M)
        known = bool(names) and vendors and set(vendors) == {'AuthenticAMD'} and all(
            re.fullmatch(r'AMD Ryzen 5 4500(?: 6-Core Processor)?', name.strip()) for name in names)
        return cls('znver2' if known else 'x86-64', jobs, load)

    def validate(self):
        if self.march not in ('x86-64', 'znver2'):
            raise ValueError('Unsupported compiler architecture')
        for value in (self.jobs, self.load):
            if type(value) is not int or not 1 <= value <= 256:
                raise ValueError('Compilation limits must be integers between 1 and 256')


def configure_compiler(target, settings):
    settings.validate()
    make_conf = target.root / 'etc/portage/make.conf'
    original = make_conf.read_text()
    include = 'source /etc/portage/forge-compiler.conf'
    if include not in original.splitlines():
        write_target(target.root, 'etc/portage/make.conf', original + '\n' + include + '\n')
    write_target(target.root, 'etc/portage/forge-compiler.conf',
                 f'COMMON_FLAGS="-march={settings.march} -O2 -pipe"\n'
                 'CFLAGS="${COMMON_FLAGS}"\nCXXFLAGS="${COMMON_FLAGS}"\n'
                 'FCFLAGS="${COMMON_FLAGS}"\nFFLAGS="${COMMON_FLAGS}"\n'
                 f'MAKEOPTS="-j{settings.jobs} -l{settings.load}"\n')
    return {'march': settings.march, 'jobs': settings.jobs, 'load': settings.load}


def validate_use_flags(target, requests):
    """Ask target Portage for evaluated IUSE; never parse ebuild source text."""
    import json
    for atom, flags in requests.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9+_-]*/[A-Za-z0-9][A-Za-z0-9+_.-]*', atom):
            raise ValueError('Invalid package atom')
        if any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_+-]*', flag) for flag in flags):
            raise ValueError('Invalid USE flag')
    probe = '''import json,sys,portage
p=portage.db[portage.settings['ROOT']]['porttree'].dbapi
for atom,flags in json.loads(sys.argv[1]).items():
    matches=p.xmatch('match-visible',atom)
    if not matches: raise SystemExit('No visible package: '+atom)
    cpv=portage.best(matches)
    iuse={f.lstrip('+-') for f in p.aux_get(cpv,['IUSE'])[0].split()}
    missing=set(flags)-iuse
    if missing: raise SystemExit('Unavailable USE flags for '+atom+': '+','.join(sorted(missing)))
'''
    target.chroot(['/usr/bin/python3', '-c', probe, json.dumps(requests, sort_keys=True)], timeout=120)
