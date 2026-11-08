"""Tests for read-only telemetry and absent sensor handling."""
import tempfile
import unittest
from pathlib import Path
from tui.telemetry import snapshot, format_snapshot


class TelemetryTests(unittest.TestCase):
    def test_snapshot_from_fake_proc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc"
            proc.mkdir()
            (proc / "meminfo").write_text("MemTotal: 16000 kB\nMemAvailable: 4000 kB\n")
            (proc / "loadavg").write_text("2.50 1.20 0.80 1/100 42\n")
            (proc / "uptime").write_text("100.5 10.2\n")
            thermal = root / "thermal"
            (thermal / "thermal_zone0").mkdir(parents=True)
            (thermal / "thermal_zone0" / "temp").write_text("42500\n")
            result = snapshot(proc, thermal)
            self.assertEqual(result.memory_used_percent, 75.0)
            self.assertEqual(result.load_1m, 2.5)
            self.assertEqual(result.cpu_temp_c, 42.5)
            self.assertIn("75.0%", format_snapshot(result))

    def test_missing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = snapshot(Path(tmp) / "none", Path(tmp) / "missing")
            self.assertIsNone(result.memory_used_percent)
            self.assertIsNone(result.cpu_temp_c)
            self.assertIn("unknown", format_snapshot(result))


if __name__ == "__main__":
    unittest.main()
