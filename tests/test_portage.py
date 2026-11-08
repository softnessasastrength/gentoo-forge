import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from installer.portage import CompilerSettings, configure_compiler, profile_path, select_profile


class PortageTests(unittest.TestCase):
    def test_profile_requires_exact_stable_openrc_multilib_entry(self):
        base = 'amd64 default/linux/amd64/23.0 stable\n'
        plasma = 'amd64 default/linux/amd64/23.0/desktop/plasma stable\n'
        self.assertTrue(profile_path(base + plasma, 'plasma').endswith('/plasma'))
        for data in ('', plasma.replace('stable', 'dev'), plasma * 2,
                     plasma.replace('amd64 ', 'arm64 '), plasma.replace('plasma ', 'plasma/systemd ')):
            with self.assertRaises(ValueError):
                profile_path(data, 'plasma')
        with self.assertRaises(ValueError):
            profile_path(base, '../escape')

    def test_selects_profile_using_fixed_argv_and_verifies_in_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Mock(root=Path(directory))
            profiles = target.root / 'var/db/repos/gentoo/profiles'
            (profiles / 'default/linux/amd64/23.0').mkdir(parents=True)
            (profiles / 'profiles.desc').write_text('amd64 default/linux/amd64/23.0 stable\n')
            self.assertEqual(select_profile(target), 'default/linux/amd64/23.0')
            self.assertEqual(target.chroot.call_args_list[0].args[0],
                             ['/usr/bin/eselect', 'profile', 'set', 'default/linux/amd64/23.0'])
            self.assertIn('MULTILIB_ABIS', target.chroot.call_args_list[1].args[0][-1])

    def test_known_ryzen_uses_znver2_unknown_cpu_keeps_portable_baseline(self):
        cpu = 'vendor_id : AuthenticAMD\nmodel name : AMD Ryzen 5 4500 6-Core Processor\n'
        self.assertEqual(CompilerSettings.for_cpu(cpu).march, 'znver2')
        for unknown in ('', cpu.replace('4500', '4500U'), cpu.replace('AuthenticAMD', 'GenuineIntel')):
            self.assertEqual(CompilerSettings.for_cpu(unknown).march, 'x86-64')

    def test_configuration_is_idempotent_and_rejects_shell_fragments(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Mock(root=Path(directory))
            (target.root / 'etc/portage').mkdir(parents=True)
            path = target.root / 'etc/portage/make.conf'
            path.write_text('# Existing working configuration\n')
            settings = CompilerSettings('znver2', 6, 6)
            configure_compiler(target, settings)
            first = path.read_text()
            configure_compiler(target, settings)
            self.assertEqual(path.read_text(), first)
            self.assertIn('Existing working configuration', first)
            self.assertIn('-march=znver2', (path.parent / 'forge-compiler.conf').read_text())
            for invalid in (CompilerSettings('native; reboot'), CompilerSettings(jobs=True), CompilerSettings(load=0)):
                with self.assertRaises(ValueError):
                    configure_compiler(target, invalid)
            target.chroot.assert_not_called()
