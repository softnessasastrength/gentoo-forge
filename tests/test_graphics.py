import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from installer.graphics import install_amd_graphics


class GraphicsTests(unittest.TestCase):
    def target(self, directory):
        target = Mock(root=Path(directory))
        (target.root / 'etc/portage').mkdir(parents=True)
        (target.root / 'etc/portage/make.conf').write_text('# Preserve existing flags\n')
        (target.root / 'usr/lib/modules/6.18-gentoo-dist-bin').mkdir(parents=True)
        fw = target.root / 'usr/lib/firmware/amdgpu'
        fw.mkdir(parents=True); (fw / 'fixture.bin').write_bytes(b'fixture')
        return target

    def test_amdgpu_radv_binary_preference_and_scoped_firmware_license(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            result = install_amd_graphics(target)
            self.assertIn('amdgpu radeonsi', (target.root / 'etc/portage/forge-graphics.conf').read_text())
            self.assertIn('vulkan', (target.root / 'etc/portage/package.use/forge-graphics').read_text())
            self.assertEqual((target.root / 'etc/portage/package.license/forge-firmware').read_text(),
                             'sys-kernel/linux-firmware linux-fw-redistributable\n')
            calls = [c.args[0] for c in target.chroot.call_args_list]
            emerge = [c for c in calls if c[0] == '/usr/bin/emerge']
            self.assertIn('--pretend', emerge[0])
            self.assertIn('--getbinpkg=y', emerge[1])
            self.assertIn('--binpkg-respect-use=y', emerge[1])
            self.assertTrue(any('modinfo' in c and 'amdgpu' in c for c in calls))
            self.assertEqual(result['hardware_rendering'], 'not verified')

    def test_failure_stops_before_initramfs_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            target.chroot.side_effect = RuntimeError('unsupported flags')
            with self.assertRaises(RuntimeError):
                install_amd_graphics(target)
            self.assertFalse((target.root / 'etc/dracut.conf.d/forge-amdgpu.conf').exists())
            self.assertFalse((target.root / 'etc/portage/forge-graphics.conf').exists())
