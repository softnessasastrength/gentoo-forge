"""Install/upgrade/remove owned butler files; never partitions, mounts or chroots."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
MARKER = 'FORGEWORTH_INSTALL_V1\n'


def public_directory(path):
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for item in reversed(missing):
        item.mkdir(mode=0o755)
        item.chmod(0o755)


def beneath(root, relative):
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Refusing target symlink traversal: ' + str(path))
    return path


def install(target, uninstall=False, source=SOURCE):
    target = Path(target).absolute()
    if target.is_symlink() or target.resolve() != target:
        raise ValueError('Target root must be a canonical directory without symlink ancestors')
    if not target.is_dir():
        raise ValueError('Target root must already exist')
    if target == Path('/') and os.geteuid() != 0:
        raise PermissionError('System installation needs root. Conversation never does.')
    base = beneath(target, 'usr/local/lib/gentoo-forge')
    launcher = beneath(target, 'usr/local/bin/butler')
    expected = (source / 'butler').read_bytes()
    if launcher.exists() and launcher.read_bytes() != expected:
        raise ValueError('Existing butler executable is not owned by this installer')
    if base.exists() and (not (base / '.installed').is_file() or (base / '.installed').read_text() != MARKER):
        raise ValueError('Existing installation directory is not owned by FORGEWORTH')
    if (base / '.installed').is_symlink() or (base / 'INSTALL.json').is_symlink():
        raise ValueError('Refusing installation metadata symlinks')
    if uninstall:
        if base.exists():
            shutil.rmtree(base)  # rmtree does not follow contained symlinks.
        launcher.unlink(missing_ok=True)
        return 'Removed owned system files. User conversations and credentials were preserved.'
    public_directory(base)
    (base / '.installed').write_text(MARKER)
    releases = beneath(base, 'releases')
    public_directory(releases)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=releases) as temporary:
        payload = Path(temporary) / 'payload'
        payload.mkdir(mode=0o755)
        for name in ('butler_cli.py',):
            shutil.copyfile(source / name, payload / name)
        (payload / 'docs').mkdir()
        shutil.copyfile(source / 'docs/BUTLER.md', payload / 'docs/BUTLER.md')
        for name in ('tui', 'forgeworth'):
            (payload / name).mkdir()
            for item in sorted((source / name).glob('*.py' if name == 'tui' else 'AGENTS.md')):
                if item.is_symlink():
                    raise ValueError('Unexpected source symlink')
                shutil.copyfile(item, payload / name / item.name)
        # A built live bundle carries its own Python/Codex through the transition.
        for name in ('python', 'bin'):
            if (source / name).is_symlink():
                raise ValueError('Refusing runtime source directory symlink')
            if (source / name).is_dir():
                shutil.copytree(source / name, payload / name, symlinks=True)
        fingerprint = hashlib.sha256()
        for item in sorted(payload.rglob('*')):
            if item.is_symlink() and not item.resolve().is_relative_to(payload.resolve()):
                raise ValueError('External payload symlink')
            if item.is_file():
                item.chmod(0o755 if item.stat().st_mode & 0o111 else 0o644)
                fingerprint.update(str(item.relative_to(payload)).encode())
                with item.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        fingerprint.update(chunk)
            elif item.is_dir():
                item.chmod(0o755)
        payload.chmod(0o755)
        version = fingerprint.hexdigest()[:24]
        destination = beneath(releases, version)
        if not destination.exists():
            payload.rename(destination)
        # Pointer update is atomic; keep old releases for inspection/recovery.
        current = base / 'current'
        if current.exists() and not current.is_symlink():
            raise ValueError('Unexpected current release path')
        temporary_link = base / '.current-new'
        if temporary_link.exists() or temporary_link.is_symlink():
            raise ValueError('Unexpected pending release pointer; inspect before retrying')
        temporary_link.symlink_to('releases/' + version)
        temporary_link.replace(current)
    public_directory(launcher.parent)
    fd, temporary = tempfile.mkstemp(prefix='.butler-', dir=launcher.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(expected)
        os.chmod(temporary, 0o755)
        os.replace(temporary, launcher)
    finally:
        Path(temporary).unlink(missing_ok=True)
    (base / 'INSTALL.json').write_text(json.dumps({'version': 1, 'release': version, 'credentials_copied': False}) + '\n')
    return 'Installed /usr/local/bin/butler. Authenticate as the target ordinary user with: butler login'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-root', type=Path, required=True, help='Explicit mounted Gentoo root, e.g. /mnt/gentoo; / means current system')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    try:
        print(install(args.target_root, args.uninstall))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
