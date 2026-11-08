"""Authenticated Gentoo OpenRC multilib Stage3 retrieval. No extraction or execution."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request

BASE = 'https://distfiles.gentoo.org/releases/amd64/autobuilds/'
KEYS = 'https://qa-reports.gentoo.org/output/service-keys.gpg'
# Gentoo publishes these release primary fingerprints on its signatures page.
TRUSTED = {'13EBBDBEDE7A12775DFDB1BABB572E0E2D182910',
           'D99EAC7379A850BCE47DA5F29E6438C817072058'}


def download(url, path, maximum):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Media downloads require credential-free HTTPS URLs')
    with urllib.request.urlopen(url, timeout=60) as response, Path(path).open('xb') as stream:
        if urllib.parse.urlsplit(response.url).scheme != 'https':
            raise ValueError('Refusing HTTPS downgrade')
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > maximum:
                raise ValueError('Media exceeds expected size bound')
            stream.write(chunk)
    return total


def signer(status):
    bad = ('BADSIG', 'ERRSIG', 'EXPSIG', 'EXPKEYSIG', 'REVKEYSIG', 'FAILURE')
    records = []
    for line in status.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == '[GNUPG:]':
            if fields[1] in bad:
                raise ValueError('Gentoo metadata signature failed or expired')
            if fields[1] == 'VALIDSIG':
                if len(fields) < 12 or fields[-1] not in TRUSTED:
                    raise ValueError('Signature is not from a trusted Gentoo release primary key')
                records.append(fields[-1])
    if len(records) != 1:
        raise ValueError('Exactly one valid trusted release signature is required')
    return records[0]


def verify_metadata(path, keyring, directory):
    output = Path(directory) / (Path(path).name + '.verified')
    home = Path(directory) / 'gpg-home'
    home.mkdir(exist_ok=True, mode=0o700)
    result = subprocess.run(['gpgv', '--homedir', str(home), '--keyring', str(Path(keyring).absolute()),
                             '--status-fd', '1', '--output', str(output), str(path)],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('Gentoo signed metadata verification failed; check clock and current release keys')
    primary = signer(result.stdout)
    if output.stat().st_size > 65536:
        raise ValueError('Unexpectedly large signed metadata')
    return output.read_text(encoding='utf-8'), primary


def select_stage3(text):
    entries = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split()
        if len(fields) != 2 or not fields[1].isdigit():
            raise ValueError('Malformed authenticated Stage3 index')
        path = fields[0]
        if not re.fullmatch(r'(\d{8}T\d{6}Z)/stage3-amd64-openrc-\1\.tar\.xz', path):
            raise ValueError('Index does not select standard amd64 OpenRC multilib Stage3')
        if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
            raise ValueError('Invalid release path')
        size = int(fields[1])
        if not 1_000_000 <= size <= 1024**3:
            raise ValueError('Unexpected Stage3 size')
        entries.append((path, size))
    if len(entries) != 1:
        raise ValueError('Stage3 index must identify exactly one release')
    return entries[0]


def checksum(text, filename):
    matches = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and re.fullmatch(r'[a-fA-F0-9]{64}', fields[0]) and fields[1].lstrip('*') == filename:
            matches.append(fields[0].lower())
    if len(matches) != 1:
        raise ValueError('Expected exactly one authenticated SHA256 for this release')
    return matches[0]


def fetch_stage3(destination):
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError('Refusing to overwrite an existing media directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.forge-media-', dir=destination.parent) as temporary:
        root = Path(temporary)
        download(KEYS, root / 'keys.gpg', 1024**2)
        download(BASE + 'latest-stage3-amd64-openrc.txt', root / 'index.asc', 65536)
        index, index_key = verify_metadata(root / 'index.asc', root / 'keys.gpg', root)
        relative, size = select_stage3(index)
        filename = PurePosixPath(relative).name
        download(BASE + relative + '.sha256', root / 'sha256.asc', 65536)
        sums, sums_key = verify_metadata(root / 'sha256.asc', root / 'keys.gpg', root)
        expected = checksum(sums, filename)
        print('Authenticated official OpenRC multilib Stage3; downloading archive...', flush=True)
        actual_size = download(BASE + relative, root / filename, size)
        with (root / filename).open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual_size != size or actual != expected:
            raise ValueError('Stage3 byte count or authenticated SHA256 mismatch')
        report = {'version': 1, 'url': BASE + relative, 'filename': filename,
                  'size': size, 'sha256': actual, 'index_primary': index_key,
                  'checksum_primary': sums_key, 'authenticated': True,
                  'extracted': False, 'installed': False}
        (root / 'VERIFIED.json').write_text(json.dumps(report, indent=2) + '\n')
        (root / 'gpg-home').rmdir()
        Path(temporary).rename(destination)
    return report


def load_verified_stage3(directory):
    """Re-authenticate cached inputs; a mutable VERIFIED.json is not authority."""
    directory = Path(directory).resolve()
    with tempfile.TemporaryDirectory(prefix='forge-reverify-') as temporary:
        root = Path(temporary)
        index, index_key = verify_metadata(directory / 'index.asc', directory / 'keys.gpg', root)
        relative, size = select_stage3(index)
        filename = PurePosixPath(relative).name
        sums, sums_key = verify_metadata(directory / 'sha256.asc', directory / 'keys.gpg', root)
        expected = checksum(sums, filename)
    archive = directory / filename
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size != size:
        raise ValueError('Cached Stage3 type or size changed')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise ValueError('Cached Stage3 differs from authenticated checksum')
    return {'filename': filename, 'size': size, 'sha256': expected,
            'index_primary': index_key, 'checksum_primary': sums_key, 'authenticated': True}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(fetch_stage3(parser.parse_args().output), indent=2))
