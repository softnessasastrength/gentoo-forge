"""Fetch the pinned, authenticated official Gentoo minimal ISO for remote VM tests."""
import hashlib
import json
from pathlib import Path
import tempfile

from installer.media import download, verify_metadata, checksum, KEYS
from tools.gentoo_vm import ISO_SHA256

NAME = 'install-amd64-minimal-20261101T164556Z.iso'
URL = 'https://distfiles.gentoo.org/releases/amd64/autobuilds/20261101T164556Z/' + NAME


def fetch(directory):
    directory = Path(directory).absolute()
    directory.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='.verify-', dir=directory) as temporary:
        root = Path(temporary)
        download(KEYS, root / 'keys.gpg', 1024**2)
        download(URL + '.sha256', root / 'iso.sha256.asc', 65536)
        text, primary = verify_metadata(root / 'iso.sha256.asc', root / 'keys.gpg', root)
        expected = checksum(text, NAME)
        if expected != ISO_SHA256:
            raise ValueError('Authenticated ISO checksum differs from pinned test fixture')
        size = download(URL, directory / NAME, 2 * 1024**3)
        with (directory / NAME).open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('ISO download checksum mismatch')
        (directory / 'VERIFIED.json').write_text(json.dumps({'sha256': actual, 'size': size,
                                                           'primary': primary, 'url': URL}, indent=2) + '\n')
    return directory / NAME


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(fetch(parser.parse_args().output))
