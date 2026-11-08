"""Integration checks on a trusted built bundle; no login, model request or real disk."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from tools.install_butler import install


def check(bundle):
    bundle = Path(bundle).resolve()
    with tempfile.TemporaryDirectory(prefix='forge-live-test-') as directory:
        env = dict(os.environ, HOME=directory)
        for action in ('doctor', 'verify', 'setup'):
            subprocess.run(['bash', str(bundle / 'livecd.sh'), action], env=env, check=True)
        subprocess.run([str(bundle / 'butler'), '--check-instructions'], env=env, check=True)
        target = Path(directory) / 'gentoo-target'
        target.mkdir()
        install(target, source=bundle)
        command = target / 'usr/local/bin/butler'
        subprocess.run([str(command), '--offline'], cwd='/', env=env, check=True)
        subprocess.run([str(command), '--check-instructions'], cwd='/', env=env, check=True)
        install(target, uninstall=True, source=bundle)
        if command.exists():
            raise RuntimeError('Uninstall left the executable behind')
    print('PASS: offline setup, native AGENTS discovery, portable target staging and uninstall')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    check(parser.parse_args().bundle)
