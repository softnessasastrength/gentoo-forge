#!/usr/bin/env python3
"""Standard-library tests for the read-only mission-control TUI."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "tui" / "forge.py"
spec = importlib.util.spec_from_file_location("forge_tui", path)
forge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forge)

class PlannerTests(unittest.TestCase):
    def test_layout(self):
        plan = forge.plan_for_bytes(100 * forge.GIB)
        self.assertEqual([p.get("size_gib") for p in plan["partitions"][:2]], [1, 20])
        self.assertEqual(plan["partitions"][2]["size_gib_at_least"], 78)
        self.assertEqual(plan["mode"], "READ_ONLY")

    def test_reject_small_and_invalid(self):
        for size in [0, 29 * forge.GIB, -1, 2.5]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                forge.plan_for_bytes(size)

    def test_config_not_executed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "danger"
            config = Path(tmp) / "hardware.env"
            config.write_text('HOSTNAME="$(touch ' + str(marker) + ')"\nHOSTNAME="forge"\n')
            parsed = forge.parse_config(config)
            self.assertEqual(parsed["HOSTNAME"], "forge")
            self.assertFalse(marker.exists())

    def test_commentary_modes(self):
        self.assertEqual(forge.commentary("off", 0), "")
        self.assertIn("Gentoo", forge.commentary("mild", 0))
        self.assertTrue(forge.commentary("spicy", 1))

    def test_sections(self):
        for i in range(len(forge.SECTIONS)):
            self.assertTrue(forge.section_lines(i, forge.DEFAULTS))

if __name__ == "__main__":
    unittest.main()
