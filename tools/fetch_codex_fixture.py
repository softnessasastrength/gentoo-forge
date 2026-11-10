"""Fetch/extract the same pinned credential-free Codex runtime as the live bundle."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tarfile

from tools.build_livecd import ASSETS, download, digest


def extract_codex(archive, destination):
    archive, destination = Path(archive), Path(destination)
    if archive.is_symlink() or not archive.is_file() or digest(archive) != ASSETS['codex']['sha256']:
        raise ValueError('Codex fixture archive does not match the pinned runtime')
    with tarfile.open(archive) as source:
        candidates = [m for m in source.getmembers() if m.isfile() and m.name == 'codex-x86_64-unknown-linux-musl']
        if len(candidates) != 1 or not 4096 <= candidates[0].size <= 512 * 1024**2:
            raise ValueError('Unexpected Codex fixture layout/size')
        with source.extractfile(candidates[0]) as data, destination.open('xb') as output:
            shutil.copyfileobj(data, output, length=1024 * 1024)
    with destination.open('rb') as stream:
        if stream.read(4) != b'\x7fELF':
            destination.unlink()
            raise ValueError('Codex runtime is not an ELF executable')
    destination.chmod(0o755)
    with destination.open('rb') as stream:
        return {'size': destination.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def fetch(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / 'codex.tar.gz'
    download(ASSETS['codex'], archive)
    extract_codex(archive, directory / 'codex')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(fetch(parser.parse_args().output))
