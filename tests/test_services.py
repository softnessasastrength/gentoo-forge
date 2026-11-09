import tempfile
import unittest
from pathlib import Path

from installer.services import install_base_services, SERVICES


class Target:
    def __init__(self, root, fail=False):
        self.root = root
        self.calls = []
        self.fail = fail

    def chroot(self, argv, timeout=300):
        self.calls.append(argv)
        if self.fail:
            raise RuntimeError('package resolution failed')
        if 'rc-update' in argv:
            default = self.root / 'etc/runlevels/default'
            default.mkdir(parents=True, exist_ok=True)
            path = default / argv[-2]
            if 'del' in argv:
                path.unlink(missing_ok=True)
            elif not path.is_symlink():
                path.symlink_to('/etc/init.d/' + argv[-2])


class ServiceTests(unittest.TestCase):
    def test_source_first_solver_then_install_then_persistent_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory))
            result = install_base_services(target, binary_fallback=False)
            self.assertIn('--pretend', target.calls[0])
            self.assertIn('--getbinpkg=n', target.calls[1])
            self.assertIn('--usepkg=n', target.calls[1])
            self.assertEqual(result['services'], list(SERVICES))
            self.assertFalse(any('rc-service' in call or 'start' in call for call in target.calls))

    def test_no_services_enabled_after_dependency_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory), fail=True)
            with self.assertRaises(RuntimeError):
                install_base_services(target)
            self.assertEqual(len(target.calls), 1)

    def test_conflicting_network_service_requires_review_before_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory))
            default = target.root / 'etc/runlevels/default'
            default.mkdir(parents=True)
            (default / 'net.eth0').symlink_to('/etc/init.d/net.lo')
            with self.assertRaisesRegex(ValueError, 'network services require review'):
                install_base_services(target)
            self.assertFalse(target.calls)

    def test_explicit_binary_exception_and_typed_options(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory))
            with self.assertRaises(ValueError):
                install_base_services(target, binary_fallback='yes')
            self.assertFalse(target.calls)
            install_base_services(target, binary_fallback=True)
            self.assertIn('--getbinpkg=y', target.calls[1])
            self.assertIn('--binpkg-respect-use=y', target.calls[1])

    def test_fresh_stage3_dhcpcd_replacement_is_explicit_and_only_changes_target_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Target(Path(directory))
            default = target.root / 'etc/runlevels/default'
            default.mkdir(parents=True)
            (default / 'dhcpcd').symlink_to('/etc/init.d/dhcpcd')
            with self.assertRaises(ValueError):
                install_base_services(target)
            self.assertFalse(target.calls)
            install_base_services(target, replace_dhcpcd=True)
            self.assertFalse((default / 'dhcpcd').is_symlink())
            self.assertTrue((default / 'NetworkManager').is_symlink())
            self.assertFalse(any('stop' in call or 'rc-service' in call for call in target.calls))
