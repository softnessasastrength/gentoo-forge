import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tui.virtualbox import (GIB, PROBES, SmokeReport, collect, graphics_adapter,
                            offline_answer, recommend, validate_selection, virtualization)


def fixture():
    return {'role': 'guest', 'virtualization': 'detected', 'efi': True,
            'observed_at': 'fixture', 'resources': {}, 'recommendation': {'status': 'unverified'},
            'graphics': 'VMSVGA [15ad:0405]\n Kernel driver in use: vmwgfx', 'errors': [], 'swaps': [],
            'diagnostics': {'root_mount': {'exit_code': 0, 'output': json.dumps({'filesystems': [
                {'source': '/dev/sr0', 'target': '/', 'fstype': 'iso9660'}]})}},
            'inventory': {'blockdevices': [dict(path='/dev/sda', name='/dev/sda', type='disk',
                size=100 * GIB, serial='VB-DISPOSABLE', model='VBOX HARDDISK', wwn=None,
                uuid=None, ro=False, mountpoints=[None])]}}


class VirtualBoxTests(unittest.TestCase):
    def test_detection_tristate(self):
        self.assertEqual(virtualization({'product_name': 'VirtualBox'}), 'detected')
        self.assertEqual(virtualization({'sys_vendor': 'innotek GmbH'}), 'detected')
        self.assertEqual(virtualization({'sys_vendor': 'Dell'}), 'not detected')
        self.assertEqual(virtualization({'product_name': None}), 'cannot be determined')

    def test_resources_guest_unknown_insufficient_and_host(self):
        resources = dict(cpus=10, load_1m=1, available_bytes=16 * GIB, storage_free_bytes=140 * GIB)
        self.assertEqual(recommend(resources, 'guest', 'detected')['status'], 'unverified')
        self.assertEqual(recommend(resources, 'host', 'detected')['status'], 'unverified')
        self.assertEqual(recommend({}, 'host', 'not detected')['status'], 'unverified')
        result = recommend(resources, 'host', 'not detected')
        self.assertEqual((result['vcpus'], result['ram_gib'], result['disk_gib']), (6, 12, 120))
        for key, value in [('cpus', 4), ('available_bytes', 10 * GIB), ('storage_free_bytes', 85 * GIB), ('load_1m', 8)]:
            self.assertEqual(recommend(resources | {key: value}, 'host', 'not detected')['status'], 'insufficient')

    def test_graphics_drivers_attached_to_adapter(self):
        pci = ('00:01.0 Ethernet controller: Intel\n\tKernel driver in use: e1000\n'
               '00:02.0 VGA compatible controller: VMware SVGA II Adapter [15ad:0405]\n'
               '\tKernel driver in use: vmwgfx\n00:03.0 SATA controller: Intel\n\tKernel driver in use: ahci\n')
        result = graphics_adapter(pci)
        self.assertIn('vmwgfx', result)
        self.assertNotIn('e1000', result)
        self.assertNotIn('ahci', result)
        self.assertNotIn('amdgpu', result)
        self.assertEqual(graphics_adapter(''), '')

    def test_disk_validation_shared_no_vm_exemption(self):
        facts = fixture()
        disk = validate_selection(facts, '/dev/sda')
        self.assertEqual(disk.serial, 'VB-DISPOSABLE')
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            validate_selection(facts, '/dev/sda', expected={'path': '/dev/sda', 'size': 100 * GIB, 'model': 'VBOX HARDDISK', 'serial': 'OLD-DISK'})
        for change in ('serial', 'mounted', 'swap', 'root', 'host', 'unknown'):
            broken = copy.deepcopy(facts)
            if change == 'serial':
                broken['inventory']['blockdevices'][0]['serial'] = ''
            elif change == 'mounted':
                broken['inventory']['blockdevices'][0]['children'] = [dict(path='/dev/sda1', mountpoints=['/mnt'])]
            elif change == 'swap':
                broken['swaps'] = ['/dev/sda']
            elif change == 'root':
                broken['diagnostics']['root_mount']['exit_code'] = 1
            elif change == 'host':
                broken['role'] = 'host'
            elif change == 'unknown':
                broken['swaps'] = None
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_selection(broken, '/dev/sda')
        with self.assertRaises(ValueError):
            validate_selection(facts | {'swaps': ['/swapfile']}, '/dev/sda')
        with self.assertRaises(ValueError):
            validate_selection(facts, '/dev/sdb')

    def test_report_roundtrip_truthful_results_redaction_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'smoke.json'
            report = SmokeReport(path)
            report.observe(fixture())
            for status in ('completed', 'failed', 'skipped', 'pending'):
                report.record('vm', status, 'password=secret test evidence')
                self.assertEqual(report.data['steps']['vm']['status'], status)
            report.record('inspect', 'completed', 'Exit 0', source='observed')
            report.record('install', 'skipped', 'Executor locked')
            with self.assertRaises(ValueError):
                report.record('grub', 'completed', '', source='user-reported')
            with self.assertRaises(ValueError):
                report.record('grub', 'completed', 'claim', source='observed')
            report.data['disk_validation'] = 'read-only checks passed'
            paths = report.export()
            saved = json.loads(path.read_text())
            self.assertEqual(saved['installation_smoke_test'], 'unverified')
            self.assertFalse(saved['configuration']['writes_enabled'])
            self.assertEqual(saved['steps']['inspect']['source'], 'observed')
            self.assertNotIn('password=secret', path.read_text())
            for output in paths:
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertIn('revalidate', SmokeReport(path).data['disk_validation'])
            self.assertIn('UNVERIFIED', paths[1].read_text())
            path.write_text('{"schema_version": 99}')
            with self.assertRaises(ValueError):
                SmokeReport(path)

    def test_guidance_uses_state_and_serious_disk_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            report = SmokeReport(Path(directory) / 'smoke.json')
            report.observe(fixture())
            for question in ('How do I configure VirtualBox?', "Why isn't the VM booting?", 'Why did GRUB fail?',
                             'How do I recover from this error?', 'What is the installer doing?'):
                answer = offline_answer(question, report)
                self.assertIn('UNVERIFIED', answer)
                self.assertIn('fixture', answer)
            answer = offline_answer('Which disk is safe to select?', report)
            self.assertIn('NO erase permission', answer)
            self.assertNotIn('sir', answer)
            self.assertNotIn('furniture', offline_answer('Why did GRUB fail?', report, serious=True))


class CollectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_allowlisted_probes_and_missing_tools(self):
        calls = []
        async def fake(argv, **kwargs):
            calls.append((argv, kwargs))
            if '--facts' in argv:
                return 0, json.dumps({'dmi': {}, 'virtualization': 'cannot be determined', 'resources': {}, 'swaps': []})
            if argv[0] == 'lsblk':
                return 0, json.dumps(fixture()['inventory'])
            if argv[0] == 'lspci':
                raise FileNotFoundError()
            if argv[0] == 'ip':
                raise asyncio.TimeoutError()
            return 0, '{}'
        with patch('tui.virtualbox.run', fake):
            result = await collect('guest', '/tmp/space with spaces;NOT-A-COMMAND')
        self.assertEqual(len(calls), len(PROBES) + 1)
        self.assertEqual(calls[0][0][-1], '/tmp/space with spaces;NOT-A-COMMAND')
        self.assertEqual(result['recommendation']['status'], 'unverified')
        self.assertTrue(any('FileNotFoundError' in error for error in result['errors']))
        self.assertTrue(any('TimeoutError' in error for error in result['errors']))
        self.assertEqual(result['graphics'], '')
        for argv, kwargs in calls:
            self.assertLessEqual(kwargs['timeout'], 8)
            self.assertNotIn('shell', kwargs)

    async def test_malformed_inventory_and_failed_collector(self):
        async def fake(argv, **kwargs):
            if '--facts' in argv:
                return 1, 'collector failed'
            return 0, 'not JSON'
        with patch('tui.virtualbox.run', fake):
            result = await collect()
        self.assertEqual(result['virtualization'], 'cannot be determined')
        self.assertIsNone(result['inventory'])
        self.assertTrue(result['errors'])
        with self.assertRaises(ValueError):
            validate_selection(result, '/dev/sda')
