import hashlib
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from tools.fetch_codex_fixture import extract_codex
from tools.guest_payload import copy_payload


class CodexFixtureTests(unittest.TestCase):
    def test_archive_hash_and_exact_member_verified_before_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / 'runtime.tar.gz'
            data = b'\x7fELF' + b'x' * 5000
            with tarfile.open(archive, 'w:gz') as output:
                entry = tarfile.TarInfo('codex-x86_64-unknown-linux-musl'); entry.size = len(data)
                output.addfile(entry, io.BytesIO(data))
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.dict('tools.fetch_codex_fixture.ASSETS', {'codex': {'sha256': expected}}):
                metadata = extract_codex(archive, root / 'codex')
            self.assertEqual(metadata['sha256'], hashlib.sha256(data).hexdigest())
            with self.assertRaises(ValueError): extract_codex(archive, root / 'untrusted')
            self.assertFalse((root / 'untrusted').exists())

    def test_readonly_device_copy_is_bounded_and_checksum_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; data = b'a' * 5000
            source.write_bytes(data + b'padding not part of payload')
            digest = hashlib.sha256(data).hexdigest()
            copy_payload(source, root / 'codex', len(data), digest)
            self.assertEqual((root / 'codex').read_bytes(), data)
            with self.assertRaises(ValueError): copy_payload(source, root / 'bad', len(data), '0' * 64)
            self.assertFalse((root / 'bad').exists())
            existing = root / 'keep'; existing.write_text('preserve')
            with self.assertRaises(FileExistsError): copy_payload(source, existing, len(data), digest)
            self.assertEqual(existing.read_text(), 'preserve')
