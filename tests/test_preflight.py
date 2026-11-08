from pathlib import Path
import tempfile
import unittest

from installer.preflight import check_environment, parse_memory
from installer.storage import Target


class PreflightTests(unittest.TestCase):
    def test_complete_readonly_environment_does_not_authorize_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'firmware/efi/efivars').mkdir(parents=True)
            (root / 'firmware/efi/efivars/SecureBoot-fixture').write_bytes(b'\x07\x00\x00\x00\x00')
            (root / 'meminfo').write_text('MemTotal: 16000000 kB\nMemAvailable: 12000000 kB\n')
            result = check_environment('/dev/sdz', proc=root, sysfs=root, machine='x86_64', which=lambda _: '/tool',
                                       network=lambda: {'https': True, 'clock_acceptable': True, 'clock_skew_seconds': 0},
                                       inspect_disk=lambda _: Target('/dev/sdz', 'SYNTHETIC', 'Fixture', 64 * 1024**3, '8:240'))
            self.assertTrue(result['environment_ready'])
            self.assertFalse(result['writes_authorized'])
            self.assertFalse(result['installation_verified'])

    def test_missing_architecture_firmware_memory_tools_and_network_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def unavailable(): raise OSError('offline')
            result = check_environment(proc=root, sysfs=root, machine='aarch64', which=lambda _: None, network=unavailable)
            self.assertFalse(result['environment_ready'])
            failed = {c['name'] for c in result['checks'] if c['state'] == 'fail'}
            self.assertTrue({'architecture', 'uefi', 'memory', 'prerequisites', 'network_clock'} <= failed)

    def test_memory_validation(self):
        self.assertEqual(parse_memory('MemTotal: 100 kB\nMemAvailable: 50 kB')['MemAvailable'], 51200)
        for text in ('', 'MemTotal: 1 kB\nMemAvailable: 2 kB', 'MemTotal: -1 kB\nMemAvailable: 0 kB'):
            with self.assertRaises(ValueError):
                parse_memory(text)
