"""Build a credential-free amd64 Linux folder for a live session. Python 3.12+."""
import argparse
import email
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    'python': {
        'url': 'https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.13.18%2B20261026-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz',
        'sha256': 'df15fe60d3ff55bf9dcf25824b5572756bb8816ff93865a273d3301d7066a8b7',
    },
    'codex': {
        'url': 'https://github.com/openai/codex/releases/download/rust-v0.166.0/codex-x86_64-unknown-linux-musl.tar.gz',
        'sha256': 'a0bf572d2f93f056c6712a6da348e96078dc84f3885fd7be67807ef389cb3978',
    },
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(asset, target):
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'gentoo-forge-livecd-builder'})
    with urllib.request.urlopen(request, timeout=60) as response, target.open('xb') as stream:
        count = 0
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > 160 * 1024**2:
                raise ValueError('Runtime download exceeds size limit')
            stream.write(chunk)
    if digest(target) != asset['sha256']:
        target.unlink()
        raise ValueError('Runtime SHA-256 mismatch')


def copy_app(destination):
    """Explicit allowlist; no git tree, user config, history, auth or reports."""
    destination.mkdir()
    for name in ('AGENTS.md', 'README.md', 'butler_cli.py', 'butler'):
        shutil.copyfile(ROOT / name, destination / name)
    shutil.copytree(ROOT / 'forgeworth', destination / 'forgeworth', ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('tui', 'scripts'):
        (destination / name).mkdir()
        pattern = '*.py' if name == 'tui' else '*.sh'
        for path in sorted((ROOT / name).glob(pattern)):
            if path.is_symlink():
                raise ValueError('Source symlinks are not permitted')
            shutil.copyfile(path, destination / name / path.name)
    (destination / 'config').mkdir()
    shutil.copyfile(ROOT / 'config/hardware.env.example', destination / 'config/hardware.env.example')
    (destination / 'docs').mkdir()
    for name in ('LIVE-CD.md', 'BUTLER.md', 'SAFETY.md', 'INSTALLATION-TARGET.md'):
        shutil.copyfile(ROOT / 'docs' / name, destination / 'docs' / name)


def wheel_lock(wheelhouse):
    lines = []
    for path in sorted(wheelhouse.glob('*.whl')):
        with zipfile.ZipFile(path) as wheel:
            metadata = [p for p in wheel.namelist() if p.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                raise ValueError('Invalid wheel metadata')
            data = email.message_from_bytes(wheel.read(metadata[0]))
        name, version = data['Name'], data['Version']
        if not name or not version or not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or not re.fullmatch(r'[A-Za-z0-9_.+!-]+', version):
            raise ValueError('Invalid wheel identity')
        lines.append(f'{name}=={version} --hash=sha256:{digest(path)}')
    if not lines:
        raise ValueError('No dependency wheels were downloaded')
    return '\n'.join(lines) + '\n'


def manifest(directory):
    lines = []
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory)
        if '\n' in str(relative) or '\\' in str(relative):
            raise ValueError('Unsupported manifest filename')
        if path.is_symlink():
            # Runtime's relative internal library links are checked on extraction.
            if not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('External runtime symlink')
        if path.is_file() and str(relative) != 'SHA256SUMS':
            lines.append(f'{digest(path)}  {relative}')
    (directory / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')


def build(output, *, with_codex=True):
    if sys.version_info < (3, 12):
        raise RuntimeError('Building requires Python 3.12+ for safe archive extraction')
    if os.geteuid() == 0:
        raise PermissionError('Build as an ordinary user')
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Output exists; choose a new directory rather than overwriting it')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.forge-build-', dir=output.parent) as temp:
        workspace = Path(temp)
        bundle = workspace / 'bundle'
        bundle.mkdir()
        copy_app(bundle / 'app')
        shutil.copyfile(ROOT / 'livecd.sh', bundle / 'livecd.sh')
        (bundle / 'livecd.sh').chmod(0o755)
        for name in ('butler', 'butler_cli.py', 'install-butler.sh'):
            shutil.copyfile(ROOT / name, bundle / name)
        (bundle / 'butler').chmod(0o755)
        (bundle / 'tools').mkdir()
        shutil.copyfile(ROOT / 'tools/install_butler.py', bundle / 'tools/install_butler.py')
        (bundle / 'docs').mkdir()
        for name in ('LIVE-CD.md', 'BUTLER.md'):
            shutil.copyfile(ROOT / 'docs' / name, bundle / 'docs' / name)
        shutil.copytree(ROOT / 'forgeworth', bundle / 'forgeworth', ignore=shutil.ignore_patterns('__pycache__'))
        (bundle / 'tui').mkdir()
        for name in ('__init__.py', 'personality.py', 'process.py'):
            shutil.copyfile(ROOT / 'tui' / name, bundle / 'tui' / name)
        for name in ('python', 'codex') if with_codex else ('python',):
            print('Downloading verified ' + name + ' runtime...', flush=True)
            archive = workspace / (name + '.tar.gz')
            download(ASSETS[name], archive)
            with tarfile.open(archive) as source:
                if sum(m.size for m in source.getmembers()) > 1024**3:
                    raise ValueError('Expanded runtime exceeds limit')
                if name == 'python':
                    if any(not m.name.startswith('python/') and m.name != 'python' for m in source.getmembers()):
                        raise ValueError('Unexpected Python runtime archive layout')
                    source.extractall(bundle, filter='data')
                else:
                    candidates = [m for m in source.getmembers() if m.isfile() and m.name == 'codex-x86_64-unknown-linux-musl']
                    if len(candidates) != 1:
                        raise ValueError('Unexpected Codex archive layout')
                    (bundle / 'bin').mkdir()
                    with source.extractfile(candidates[0]) as stream, (bundle / 'bin/codex').open('xb') as target:
                        shutil.copyfileobj(stream, target)
                    (bundle / 'bin/codex').chmod(0o755)
        wheels = bundle / 'wheelhouse'
        wheels.mkdir()
        # Use the bundled interpreter so dependency selection matches the live CD.
        subprocess.run([str(bundle / 'python/bin/python3'), '-m', 'pip', 'download',
                        '--only-binary=:all:', '--dest', str(wheels), '-r', str(ROOT / 'tui/requirements.txt')], check=True)
        (bundle / 'requirements-live.lock').write_text(wheel_lock(wheels))
        (bundle / 'BUILD.json').write_text(json.dumps({
            'format': 1, 'architecture': 'linux-x86_64',
            'assets': {k: v for k, v in ASSETS.items() if k != 'codex' or with_codex},
            'credentials_included': False, 'installer_writes_enabled': False,
        }, indent=2) + '\n')
        (bundle / 'THIRD-PARTY.md').write_text(
            'Python runtime: https://github.com/astral-sh/python-build-standalone\n'
            'Python licensing files are included in python/.\n'
            'Codex (when included): https://github.com/openai/codex, Apache-2.0.\n'
            'Dependency licenses remain inside the original wheels and installed metadata.\n')
        if with_codex:
            # Retain the upstream license alongside the native executable.
            with urllib.request.urlopen('https://raw.githubusercontent.com/openai/codex/rust-v0.166.0/LICENSE', timeout=30) as response:
                license_text = response.read(100000)
            if b'Apache License' not in license_text:
                raise ValueError('Unexpected Codex license')
            (bundle / 'bin/CODEX-LICENSE').write_bytes(license_text)
        manifest(bundle)
        # Builder's private staging parent is removed after publication.
        bundle.chmod(0o755)
        bundle.rename(output)
    print(f'Portable bundle: {output}\nCopy the complete folder to USB; do not flash it over the live ISO.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/forgeworth-live')
    parser.add_argument('--no-codex', action='store_true', help='Build offline inspection UI only')
    args = parser.parse_args()
    build(args.output, with_codex=not args.no_codex)


if __name__ == '__main__':
    main()
