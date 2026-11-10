"""Bounded authenticated payload copying inside the disposable guest fixture."""
import hashlib
from pathlib import Path
import re


def copy_payload(device, destination, size, sha256):
    if type(size) is not int or not 4096 <= size <= 512 * 1024**2 or not re.fullmatch(r'[a-f0-9]{64}', sha256):
        raise ValueError('Invalid guest payload identity')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(device, 'rb', buffering=0) as source, destination.open('xb') as output:
            digest = hashlib.sha256()
            remaining = size
            while remaining:
                data = source.read(min(1024 * 1024, remaining))
                if not data:
                    raise ValueError('Truncated guest payload')
                digest.update(data); output.write(data); remaining -= len(data)
        if digest.hexdigest() != sha256:
            raise ValueError('Guest payload checksum mismatch')
    except BaseException:
        # Remove only a file created by this invocation, never an existing file.
        if 'output' in locals():
            destination.unlink(missing_ok=True)
        raise
    destination.chmod(0o755)
