import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from installer.desktop import install_desktop


class Target:
    def __init__(self, root, fail=False):
        self.root = root; self.calls = []; self.fail = fail
        session = root / 'usr/share/wayland-sessions/plasma.desktop'
        session.parent.mkdir(parents=True); session.write_text('[Desktop Entry]\n')
        autostart = root / 'etc/xdg/autostart/pipewire.desktop'
        autostart.parent.mkdir(parents=True); autostart.write_text('[Desktop Entry]\n')

    def chroot(self, argv, timeout=300):
        self.calls.append(argv)
        if self.fail:
            raise RuntimeError('dependency failure')
        if 'rc-update' in argv:
            path = self.root / 'etc/runlevels' / argv[-1] / argv[-2]
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_symlink():
                path.symlink_to('/etc/init.d/' + argv[-2])


class DesktopTests(unittest.TestCase):
    def test_wayland_pipewire_openrc_without_autologin_or_live_daemon_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory))
            with patch('installer.desktop.select_profile', return_value='plasma'), patch('installer.desktop.validate_use_flags') as validate:
                result = install_desktop(target)
            validate.assert_called_once()
            self.assertEqual(result['session'], 'plasma.desktop')
            self.assertFalse(result['automatic_login'])
            self.assertEqual(result['desktop_login'], 'not verified')
            emerge = [a for a in target.calls if a[0] == '/usr/bin/emerge']
            self.assertIn('--pretend', emerge[0]); self.assertIn('@world', emerge[1])
            self.assertIn('gui-apps/sddm', emerge[1]); self.assertIn('--usepkg=y', emerge[1])
            self.assertFalse(any('rc-service' in a or 'start' in a for a in target.calls))
            config = (target.root / 'etc/sddm.conf.d/forgeworth.conf').read_text()
            self.assertNotIn('Autologin', config)
            self.assertIn('wayland-sessions/plasma.desktop', (target.root / 'var/lib/sddm/state.conf').read_text())

    def test_failed_package_resolution_never_enables_display_manager(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory), fail=True)
            with patch('installer.desktop.select_profile'), patch('installer.desktop.validate_use_flags'), self.assertRaises(RuntimeError):
                install_desktop(target)
            self.assertFalse(any('rc-update' in a for a in target.calls))

    def test_conflicting_display_manager_or_invalid_user_rejected_before_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory))
            with self.assertRaises(ValueError):
                install_desktop(target, username='branden; reboot')
            default = target.root / 'etc/runlevels/default'; default.mkdir(parents=True)
            (default / 'gdm').symlink_to('/etc/init.d/gdm')
            with self.assertRaisesRegex(ValueError, 'requires review'):
                install_desktop(target)
            self.assertFalse(target.calls)
