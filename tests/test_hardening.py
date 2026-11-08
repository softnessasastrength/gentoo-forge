import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tui.compilation import EmergeParser, LogObserver
from tui.engine import Engine, Event
from tui.process import run
from tui.safety import validate_target
from tui.telemetry import snapshot
from tui.virtualbox import validate_selection
from test_virtualbox import fixture
from tui.backend import BackendError, CodexBackend
from tui.personality import Context, Mode


class DiskEvidenceTests(unittest.TestCase):
    def test_unresolved_root_and_swap_fail_closed(self):
        facts = fixture()
        for source in ('/dev/mapper/missing', '/dev/disk/by-uuid/unresolved'):
            with self.subTest(source=source):
                broken = copy.deepcopy(facts)
                broken['diagnostics']['root_mount']['output'] = json.dumps(
                    {'filesystems': [{'target': '/', 'source': source}]})
                with self.assertRaisesRegex(ValueError, 'unresolved'):
                    validate_selection(broken, '/dev/sda')
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            validate_selection(facts | {'swaps': ['/dev/sdb1']}, '/dev/sda')

    def test_btrfs_root_suffix_and_shared_mapper_descendant(self):
        facts = fixture()
        root = dict(path='/dev/sda1', mountpoints=[None])
        facts['inventory']['blockdevices'][0]['children'] = [root]
        facts['diagnostics']['root_mount']['output'] = json.dumps(
            {'filesystems': [{'target': '/', 'source': '/dev/sda1[/@]'}]})
        with self.assertRaisesRegex(ValueError, 'ancestry'):
            validate_selection(facts, '/dev/sda')
        root['path'] = '/dev/mapper/root'
        facts['diagnostics']['root_mount']['output'] = json.dumps(
            {'filesystems': [{'target': '/', 'source': '/dev/mapper/root'}]})
        with self.assertRaises(ValueError):
            validate_selection(facts, '/dev/sda')

    def test_malformed_nodes_and_identity_fail_closed(self):
        for key, value in [('serial', None), ('model', ' '), ('size', True),
                           ('mountpoints', None), ('mountpoints', [7]), ('children', None)]:
            facts = fixture()
            facts['inventory']['blockdevices'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_target(facts['inventory'], '/dev/sda', [], [])


class ObservationTests(unittest.TestCase):
    def test_package_counts_only_from_explicit_records(self):
        parser = EmergeParser()
        parser.feed('100% imaginary\n>>> emerge (1 of 2) sys-devel/gcc-15 to /\n')
        self.assertEqual(parser.state.total, 2)
        self.assertEqual(parser.state.completed, 0)
        parser.feed('::: completed emerge (1 of 2) sys-devel/gcc-15 to /\n' * 2)
        self.assertEqual(parser.state.completed, 1)
        parser.feed('>>> emerge (2 of 2) kde-plasma/plasma-meta to /\n')
        parser.feed('*** Failed to emerge kde-plasma/plasma-meta\n')
        self.assertTrue(parser.state.failure)
        self.assertEqual(parser.state.completed, 1)
        self.assertNotIn('%', parser.state.describe())

    def test_mid_build_interleaving_and_partial_lines(self):
        parser = EmergeParser()
        parser.feed('>>> emerge (4 of 10) cat/pkg to /\n')
        self.assertIsNone(parser.state.total)
        parser = EmergeParser()
        parser.feed('>>> emerge (1 of 2) cat/a')
        self.assertIsNone(parser.state.current)
        parser.feed(' to /\n>>> emerge (2 of 2) cat/b to /\n')
        self.assertIsNone(parser.state.total)
        parser.feed('x' * 100000)
        self.assertLessEqual(len(parser.pending), 16384)

    def test_observer_attachment_rotation_and_nonregular_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'emerge.log'
            path.write_text('>>> emerge (1 of 9) old/package\n')
            observer = LogObserver(path)
            self.assertIsNone(observer.poll().total)
            with path.open('a') as stream:
                stream.write('>>> emerge (1 of 2) new/package\n')
            self.assertEqual(observer.poll().total, 2)
            path.unlink()
            path.write_text('new log\n')
            self.assertIsNone(observer.poll().total)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                observer.poll()
            path.unlink()
            path.symlink_to(Path(directory) / 'target')
            with self.assertRaises(OSError):
                observer.poll()

    def test_identified_ryzen_hwmon_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sensor = root / 'hwmon0'
            sensor.mkdir()
            (sensor / 'name').write_text('amdgpu')
            (sensor / 'temp1_label').write_text('Tctl')
            (sensor / 'temp1_input').write_text('53000')
            self.assertIsNone(snapshot(root, root, root).cpu_temp_c)
            (sensor / 'name').write_text('k10temp')
            self.assertEqual(snapshot(root, root, root).cpu_temp_c, 53.0)

    def test_checkpoint_does_not_follow_predictable_temp_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.json'
            victim = Path(directory) / 'victim'
            victim.write_text('preserve')
            path.with_suffix('.tmp').symlink_to(victim)
            Engine(path, lambda _: None).publish(Event('preflight', 'running'))
            self.assertEqual(victim.read_text(), 'preserve')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class SupervisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_untrusted_json_and_zero_exit_error(self):
        for fail in (False, True):
            async def fake(argv, **kwargs):
                if '--help' in argv:
                    return 0, '--ignore-user-config --ignore-rules --ephemeral --json --sandbox'
                if 'features' in argv:
                    return 0, 'shell_tool unified_exec apps plugins'
                events = [None, [], 'unexpected', {'item': None},
                          {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 42}},
                          {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'observed'}}]
                if fail:
                    events.append({'type': 'turn.failed', 'error': {'message': 'SECRET'}})
                return 0, '\n'.join(map(json.dumps, events))
            backend = CodexBackend()
            with patch.dict(os.environ, {'FORGEWORTH_CODEX': '1'}), patch('os.geteuid', return_value=1000), patch('shutil.which', return_value='/bin/codex'), patch('tui.backend.run', fake):
                if fail:
                    with self.assertRaises(BackendError) as error:
                        await backend.answer('hello', Mode.BUTLER, 85, Context())
                    self.assertNotIn('SECRET', str(error.exception))
                    self.assertEqual(backend.history, [])
                else:
                    self.assertEqual(await backend.answer('hello', Mode.BUTLER, 85, Context()), 'observed')

    async def test_simultaneous_large_stdin_and_stdout(self):
        program = 'import sys; sys.stdout.write("x"*200000); sys.stdout.flush(); print(len(sys.stdin.read()))'
        code, text = await run([sys.executable, '-c', program], stdin='y' * 200000, timeout=3)
        self.assertEqual(code, 0)
        self.assertTrue(text.endswith('200000\n'))

    async def test_utf8_split_across_process_reads(self):
        chunks = []
        program = 'import os,time; os.write(1,b"\\xe2"); time.sleep(.05); os.write(1,b"\\x82\\xac")'
        code, text = await run([sys.executable, '-c', program], on_line=chunks.append)
        self.assertEqual(code, 0)
        self.assertEqual(''.join(chunks), text)
        self.assertEqual(text, '€')

    async def test_early_exit_with_large_stdin(self):
        code, _ = await run([sys.executable, '-c', 'raise SystemExit(7)'], stdin='x' * 200000)
        self.assertEqual(code, 7)
