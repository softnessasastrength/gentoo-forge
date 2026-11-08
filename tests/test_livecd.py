import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.build_livecd import ROOT, copy_app, download, manifest, wheel_lock


class LiveBundleTests(unittest.TestCase):
    def test_allowlist_excludes_local_state(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / 'app'
            copy_app(app)
            files = [p.relative_to(app).as_posix() for p in app.rglob('*') if p.is_file()]
            self.assertIn('AGENTS.md', files)
            self.assertIn('tui/personality.py', files)
            self.assertIn('config/hardware.env.example', files)
            for forbidden in ('.git', '.codex', '.venv', 'auth.json', 'hardware.env', 'checkpoint.json'):
                self.assertFalse(any(forbidden in Path(f).parts for f in files))

    def test_download_digest_mismatch_and_success(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'asset'
            with patch('urllib.request.urlopen', return_value=io.BytesIO(b'payload')):
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    download({'url': 'https://example.com/asset', 'sha256': 'bad'}, target)
            self.assertFalse(target.exists())
            with patch('urllib.request.urlopen', return_value=io.BytesIO(b'payload')):
                download({'url': 'https://example.com/asset', 'sha256': hashlib.sha256(b'payload').hexdigest()}, target)
            self.assertEqual(target.read_bytes(), b'payload')

    def test_manifest_hashes_symlinks_and_rejects_external_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'regular').write_text('hello')
            (root / 'link').symlink_to('regular')
            manifest(root)
            self.assertIn('  link', (root / 'SHA256SUMS').read_text())
            result = subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0)
            (root / 'regular').write_text('corrupt')
            result = subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=root, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            (root / 'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                manifest(root)

    def test_dependency_lock_requires_exact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                wheel_lock(root)
            with zipfile.ZipFile(root / 'fixture.whl', 'w') as wheel:
                wheel.writestr('fixture.dist-info/METADATA', 'Name: fixture\nVersion: 1.2.3\n')
            lock = wheel_lock(root)
            self.assertTrue(lock.startswith('fixture==1.2.3 --hash=sha256:'))

    def test_launcher_rejects_unbuilt_and_unexpected_actions(self):
        for action, code in [('not-a-command', 2), ('verify', 1)]:
            result = subprocess.run(['bash', str(ROOT / 'livecd.sh'), action], capture_output=True)
            self.assertEqual(result.returncode, code)
