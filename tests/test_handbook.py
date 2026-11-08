from pathlib import Path
import unittest
from installer.handbook import REQUIREMENTS, ALTERNATIVES, report


class HandbookTests(unittest.TestCase):
    def test_every_implemented_requirement_has_real_code_and_verification(self):
        root = Path(__file__).resolve().parents[1]
        keys = [r.key for r in REQUIREMENTS]
        self.assertEqual(len(keys), len(set(keys)))
        for item in REQUIREMENTS:
            self.assertTrue(item.verification)
            if item.status not in ('pending', 'manual-only'):
                self.assertTrue((root / item.implementation).is_file(), item.key)
            if item.tests:
                self.assertTrue((root / item.tests).is_file(), item.key)
        self.assertFalse(report()['definition_of_done_satisfied'])
        self.assertIn('BIOS/MBR', ALTERNATIVES)
        self.assertIn('systemd', ALTERNATIVES)
