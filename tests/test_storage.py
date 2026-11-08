import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from installer.storage import (Audit, Target, active_devices, main, nodes,
                               prepare)
from installer.partition_plan import plan, commands


def proposal():
    return plan({'partitiontable': {'label': 'gpt', 'id': '12345678-1234-4234-8234-123456789abc',
                 'device': '/dev/sda', 'unit': 'sectors', 'firstlba': 34, 'lastlba': 536870878,
                 'sectorsize': 512, 'partitions': []}}, '/dev/sda', 256 * 1024**3)


def devices():
    return {'blockdevices': [
        {'path': '/dev/sda', 'maj:min': '8:0', 'children': [
            {'path': '/dev/sda1', 'maj:min': '8:1'}]},
        {'path': '/dev/sdb', 'maj:min': '8:16', 'children': [
            {'path': '/dev/sdb1', 'maj:min': '8:17'}]},
        {'path': '/dev/sr0', 'maj:min': '11:0'}]}


class StoragePolicyTests(unittest.TestCase):
    def test_ram_live_root_protects_optical_media(self):
        mounts = '1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 11:0 / /run/livecd ro - iso9660 /dev/sr0 ro\n'
        active = active_devices(devices(), mounts, 'Filename Type Size Used Priority\n', lambda _: None)
        self.assertEqual(active, ['/dev/sr0'])

    def test_btrfs_alias_and_active_swap_resolve_kernel_identity(self):
        mounts = '1 0 0:57 /@ / rw - btrfs /dev/root rw\n'
        swap = 'Filename Type Size Used Priority\n/dev/disk/by-uuid/SWAP partition 100 0 -2\n'
        active = active_devices(devices(), mounts, swap,
                                lambda p: {'/dev/root': '8:1', '/dev/disk/by-uuid/SWAP': '8:17'}[p])
        self.assertEqual(set(active), {'/dev/sda1', '/dev/sdb1'})

    def test_unknown_root_overlay_missing_swap_and_swapfile_fail_closed(self):
        for mounts, swaps in [
            ('1 0 0:1 / / rw - overlay overlay rw', 'Filename Type Size Used Priority\n'),
            ('1 0 8:99 / / rw - ext4 /dev/missing rw', 'Filename Type Size Used Priority\n'),
            ('1 0 0:1 / / rw - tmpfs tmpfs rw', ''),
            ('1 0 0:1 / / rw - tmpfs tmpfs rw', 'Filename Type Size Used Priority\n/swapfile file 1 0 -1'),
            ('', 'Filename Type Size Used Priority\n'),
        ]:
            with self.subTest(mounts=mounts, swaps=swaps), self.assertRaises(ValueError):
                active_devices(devices(), mounts, swaps, lambda _: '8:99')

    def test_plan_uses_fixed_argument_vectors(self):
        argv = commands(proposal())[0]
        self.assertNotIn('--zap-all', argv)
        self.assertNotIn('--clear', argv)
        self.assertEqual(argv[-1], '/dev/sda')
        self.assertIn('--new=1:2048:2099199', argv)

    def test_every_authorization_gate_precedes_device_open(self):
        target = Target('/dev/sda', 'SERIAL', 'MODEL', 256 * 1024**3, '8:0')
        with tempfile.TemporaryDirectory() as directory:
            audit = Audit(Path(directory) / 'audit.jsonl')
            cases = [(False, True, 'ERASE /dev/sda SERIAL 274877906944'),
                     (True, False, 'ERASE /dev/sda SERIAL 274877906944'),
                     (True, True, 'yes')]
            for nuke, interactive, confirmation in cases:
                with patch('os.geteuid', return_value=0), patch('shutil.which', return_value='/tool'), patch('installer.storage.inspect', return_value=target), patch('installer.storage.read_plan', return_value=proposal()), patch('installer.storage.open_target') as opened:
                    with self.assertRaises(PermissionError):
                        prepare(target, proposal(), nuke_it=nuke, interactive=interactive,
                                confirmation=confirmation, audit=audit)
                    opened.assert_not_called()
            events = [json.loads(line)['action'] for line in audit.path.read_text().splitlines()]
            self.assertNotIn('approved', events)

    def test_missing_tools_and_nonroot_fail_before_authorization(self):
        target = Target('/dev/sda', 'SERIAL', 'MODEL', 256 * 1024**3, '8:0')
        with patch('os.geteuid', return_value=1000):
            with self.assertRaises(PermissionError):
                prepare(target, proposal(), nuke_it=True, confirmation='', interactive=True, audit=None)
        with patch('os.geteuid', return_value=0), patch('shutil.which', return_value=None):
            with self.assertRaises(RuntimeError):
                prepare(target, proposal(), nuke_it=True, confirmation='', interactive=True, audit=None)

    def test_cli_cannot_enable_unqualified_physical_writes(self):
        target = Target('/dev/sda', 'SERIAL', 'MODEL', 256 * 1024**3, '8:0')
        with patch('sys.argv', ['forge-install', 'storage', '--disk', '/dev/sda', '--nuke-it']), patch('installer.storage.inspect', return_value=target), patch('installer.storage.read_plan', return_value=proposal()), patch('installer.storage.prepare') as executor:
            self.assertEqual(main(), 1)
            executor.assert_not_called()

    def test_gentoo_overlay_backing_is_resolved(self):
        mounts = ('1 0 0:1 / /run rw - tmpfs tmpfs rw\n'
                  '2 1 11:0 / /run/rootfsbase ro - squashfs /dev/sr0 ro\n'
                  '3 0 0:27 / / rw - overlay LiveOS_rootfs rw,lowerdir=/run/rootfsbase,upperdir=/run/overlayfs,workdir=/run/ovlwork\n')
        self.assertEqual(active_devices(devices(), mounts, 'Filename Type Size Used Priority\n', lambda _: None), ['/dev/sr0'])

    def test_audit_is_private_and_refuses_symlink_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'audit'
            audit = Audit(target)
            audit.write('proposed', target={'path': '/dev/sda'})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            target.unlink()
            victim = Path(directory) / 'victim'
            victim.write_text('preserve')
            target.symlink_to(victim)
            with self.assertRaises(OSError):
                audit.write('approved')
            self.assertEqual(victim.read_text(), 'preserve')

    def test_malformed_kernel_identity_rejected(self):
        with self.assertRaises(ValueError):
            list(nodes({'blockdevices': [{'path': '/dev/sda'}]}))
