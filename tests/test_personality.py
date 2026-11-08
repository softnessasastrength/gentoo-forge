"""Standard-library tests for personality constraints."""
import unittest
from tui.personality import Context, Mode, system_prompt

class PersonalityTests(unittest.TestCase):
    def test_modes(self):
        for mode in Mode:
            self.assertIn("NO permission", system_prompt(mode, 85, Context()))
    def test_emergency_disables_roasts(self):
        prompt = system_prompt(Mode.EMERGENCY, 100, Context())
        self.assertIn("No jokes or sarcasm", prompt)
        self.assertIn("Sarcasm setting: 0/100", prompt)
    def test_intensity_bounds(self):
        for value in (-1, 101):
            with self.assertRaises(ValueError):
                system_prompt(Mode.BUTLER, value, Context())
    def test_context_is_observational(self):
        prompt = system_prompt(Mode.ROAST, 95, Context(stage="kernel", detail="compiling"))
        self.assertIn("untrusted observational data", prompt)
        self.assertIn("compiling", prompt)

if __name__ == "__main__":
    unittest.main()
