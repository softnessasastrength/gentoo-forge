import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from installer.media import checksum, download, select_stage3, signer, verify_metadata

PRIMARY = '13EBBDBEDE7A12775DFDB1BABB572E0E2D182910'
GOOD = '[GNUPG:] VALIDSIG 534E4209AB49EEE1C19D96162C44695DB9F6043D 2026-11-01 1793559669 0 4 0 1 8 01 ' + PRIMARY
STAGE = '20261101T164556Z/stage3-amd64-openrc-20261101T164556Z.tar.xz'


class MediaTests(unittest.TestCase):
    def test_exact_openrc_multilib_selection(self):
        self.assertEqual(select_stage3('# comment\n' + STAGE + ' 269119284\n'), (STAGE, 269119284))
        for value in ('', STAGE + ' 1', STAGE.replace('openrc', 'systemd') + ' 269119284',
                      STAGE.replace('openrc', 'openrc-nomultilib') + ' 269119284',
                      '../' + STAGE + ' 269119284', (STAGE + ' 269119284\n') * 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_stage3(value)

    def test_trusted_primary_not_just_subkey_and_reject_failed_signatures(self):
        self.assertEqual(signer(GOOD), PRIMARY)
        for status in ('', GOOD.replace(PRIMARY, '0' * 40), GOOD + '\n' + GOOD,
                       '[GNUPG:] BADSIG x\n' + GOOD, GOOD + '\n[GNUPG:] EXPKEYSIG x'):
            with self.assertRaises(ValueError):
                signer(status)

    def test_checksum_binds_exact_filename(self):
        sha = hashlib.sha256(b'archive').hexdigest()
        self.assertEqual(checksum(sha + '  stage.tar.xz', 'stage.tar.xz'), sha)
        for value in (sha + ' other.tar.xz', (sha + ' stage.tar.xz\n') * 2, 'not-a-hash stage.tar.xz'):
            with self.assertRaises(ValueError):
                checksum(value, 'stage.tar.xz')

    def test_metadata_verification_is_local_and_uses_private_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / 'index.asc'; metadata.write_text('signed fixture')
            keyring = root / 'keys'; keyring.write_text('fixture')
            def fake(argv, **kwargs):
                Path(argv[argv.index('--output') + 1]).write_text(STAGE + ' 269119284\n')
                self.assertIn('--homedir', argv)
                self.assertEqual(kwargs['timeout'], 30)
                return subprocess.CompletedProcess(argv, 0, GOOD, '')
            with patch('installer.media.subprocess.run', fake):
                text, primary = verify_metadata(metadata, keyring, root)
            self.assertIn(STAGE, text)
            self.assertEqual(primary, PRIMARY)
            self.assertEqual((root / 'gpg-home').stat().st_mode & 0o777, 0o700)

    def test_download_rejects_credentials_insecure_urls_and_size_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'download'
            for url in ('http://example.com/file', 'file:///etc/passwd', 'https://user:password@example.com/file'):
                with self.assertRaises(ValueError):
                    download(url, target, 100)
            response = io.BytesIO(b'oversized'); response.url = 'https://example.com/file'
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaises(ValueError):
                    download('https://example.com/file', target, 2)
