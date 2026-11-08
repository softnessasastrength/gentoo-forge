import tempfile
import unittest
from pathlib import Path

from installer.boot import install_boot_stack

ROOT_UUID = '12345678-1234-4234-8234-123456789abc'
SWAP_UUID = '87654321-1234-4234-8234-123456789abc'
STORAGE = {'filesystems': {'root': {'UUID': ROOT_UUID}, 'swap': {'UUID': SWAP_UUID}}}


class FakeTarget:
    def __init__(self, root, fail=False):
        self.root = root
        self.calls = []
        self.fail = fail
        (root / 'etc/portage').mkdir(parents=True)
        (root / 'etc/portage/make.conf').write_text('COMMON_FLAGS="-O2 -pipe"\n')

    def chroot(self, argv, timeout=300):
        self.calls.append(argv)
        if self.fail:
            raise RuntimeError('injected package failure')
        if 'grub-probe' in argv:
            return ROOT_UUID + '\n'
        if 'lsinitrd' in argv:
            return 'dracut modules:\nbtrfs\nresume\n'
        if 'grub-install' in argv:
            efi = self.root / 'efi/EFI/BOOT/BOOTX64.EFI'
            efi.parent.mkdir(parents=True)
            efi.write_bytes(b'fixture')
            (self.root / 'boot').mkdir(exist_ok=True)
            (self.root / 'boot/vmlinuz-fixture').write_bytes(b'fixture')
            (self.root / 'boot/initramfs-fixture.img').write_bytes(b'fixture')


class BootTests(unittest.TestCase):
    def test_source_default_and_human_boot_menu(self):
        with tempfile.TemporaryDirectory() as directory:
            target = FakeTarget(Path(directory))
            result = install_boot_stack(target, STORAGE)
            emerge = [a for a in target.calls if a[0] == '/usr/bin/emerge']
            self.assertEqual(len(emerge), 2)
            self.assertIn('--pretend', emerge[0])
            self.assertIn('--getbinpkg=n', emerge[1])
            self.assertIn('--usepkg=n', emerge[1])
            self.assertIn('sys-kernel/gentoo-kernel', emerge[1])
            self.assertFalse(result['binary_fallback'])
            grub = (target.root / 'etc/default/grub').read_text()
            self.assertIn('GRUB_TIMEOUT=5', grub)
            self.assertNotIn('ttyS0', grub)
            self.assertIn('resume=UUID=' + SWAP_UUID, grub)
            self.assertIn('-j6 -l6', (target.root / 'etc/portage/forge-boot.conf').read_text())

    def test_explicit_vm_binary_exception_preserves_signature_check(self):
        with tempfile.TemporaryDirectory() as directory:
            target = FakeTarget(Path(directory))
            install_boot_stack(target, STORAGE, binary_fallback=True, serial_console=True, jobs=2, load=2)
            call = [a for a in target.calls if a[0] == '/usr/bin/emerge'][-1]
            self.assertIn('--getbinpkg=y', call)
            self.assertIn('sys-kernel/gentoo-kernel-bin', call)
            self.assertIn('binpkg-request-signature', (target.root / 'etc/portage/forge-boot.conf').read_text())
            self.assertIn('ttyS0', (target.root / 'etc/kernel/cmdline').read_text())

    def test_failure_never_installs_grub(self):
        with tempfile.TemporaryDirectory() as directory:
            target = FakeTarget(Path(directory), fail=True)
            with self.assertRaises(RuntimeError):
                install_boot_stack(target, STORAGE)
            self.assertFalse(any('grub-install' in a for a in target.calls))

    def test_invalid_inputs_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = FakeTarget(Path(directory))
            for options in ({'jobs': 0}, {'load': True}, {'binary_fallback': 'yes'}):
                with self.assertRaises(ValueError):
                    install_boot_stack(target, STORAGE, **options)
            with self.assertRaises(ValueError):
                install_boot_stack(target, {'filesystems': {'root': {'UUID': '"; reboot'}, 'swap': {'UUID': SWAP_UUID}}})
            self.assertFalse(target.calls)
            self.assertFalse((target.root / 'etc/kernel/cmdline').exists())

    def test_boot_verification_rejects_wrong_uuid_or_missing_resume(self):
        for broken in ('uuid', 'resume'):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as directory:
                class BrokenTarget(FakeTarget):
                    def chroot(self, argv, timeout=300):
                        result = super().chroot(argv, timeout)
                        if broken == 'uuid' and 'grub-probe' in argv:
                            return SWAP_UUID
                        if broken == 'resume' and 'lsinitrd' in argv:
                            return 'btrfs\n'
                        return result
                with self.assertRaises(RuntimeError):
                    install_boot_stack(BrokenTarget(Path(directory)), STORAGE)
