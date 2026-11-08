import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tui.backend import BackendError, CodexBackend
from tui.engine import Engine
from tui.personality import Context, Mode
from tui.process import run
from tui.safety import validate_target, authorize


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.node = dict(path='/dev/sdz', serial='SERIAL', model='Disposable',
                         size=64 * 1024**3, type='disk', ro=False, mountpoints=[None])

    def disk(self):
        return validate_target({'blockdevices': [self.node]}, '/dev/sdz', [], [])

    def test_identity_and_separate_confirmation(self):
        disk = self.disk()
        for nuke, interactive, text in [(False, True, ''), (True, False, ''), (True, True, 'yes')]:
            with self.assertRaises(PermissionError):
                authorize(disk, disk, nuke_it=nuke, interactive=interactive, confirmation=text)
        text = f'ERASE {disk.path} {disk.serial} {disk.size}'
        self.assertEqual(authorize(disk, disk, nuke_it=True, interactive=True, confirmation=text), text)

    def test_fail_closed(self):
        for field, value in [('serial', ''), ('type', 'part'), ('ro', True), ('mountpoints', ['/'])]:
            with self.subTest(field=field):
                original = self.node[field]
                self.node[field] = value
                with self.assertRaises(ValueError):
                    self.disk()
                self.node[field] = original
        self.node['children'] = [dict(path='/dev/sdz1', mountpoints=['/home'])]
        with self.assertRaises(ValueError):
            self.disk()

    def test_active_swap_and_ancestry(self):
        for active, swap in [(['/dev/sdz'], []), ([], ['/dev/sdz']), (None, [])]:
            with self.assertRaises(ValueError):
                validate_target({'blockdevices': [self.node]}, '/dev/sdz', active, swap)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_arguments_not_shell(self):
        value = '$(touch NEVER); echo wrong'
        code, output = await run([sys.executable, '-c', 'import sys; print(sys.argv[1])', value])
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), value)

    async def test_timeout_and_exit(self):
        with self.assertRaises(asyncio.TimeoutError):
            await run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.05)
        code, _ = await run([sys.executable, '-c', 'raise SystemExit(7)'])
        self.assertEqual(code, 7)

    async def test_output_bound(self):
        with self.assertRaises(RuntimeError):
            await run([sys.executable, '-c', 'print("a"*10000)'], limit=100)

    async def test_cancel(self):
        task = asyncio.create_task(run([sys.executable, '-c', 'import time; time.sleep(30)']))
        await asyncio.sleep(.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_stages_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / 'state.json'
            events = []
            engine = Engine(checkpoint, events.append)
            with self.assertRaises(PermissionError):
                await engine.execute('bootstrap', print)
            async def fake_run(*args, **kwargs):
                kwargs['on_line']('observed log')
                return 0, ''
            logs = []
            with patch('tui.engine.run', fake_run):
                await engine.execute('preflight', logs.append)
            self.assertEqual([e.status for e in events], ['running', 'completed'])
            self.assertEqual(logs, ['observed log'])
            self.assertEqual(Engine(checkpoint, events.append).states['preflight'], 'pending')
            saved = json.loads(checkpoint.read_text())
            saved['states']['preflight'] = 'running'
            checkpoint.write_text(json.dumps(saved))
            self.assertEqual(Engine(checkpoint, events.append).states['preflight'], 'interrupted')

    async def test_backend_offline_and_root(self):
        backend = CodexBackend()
        with patch.dict(os.environ, {'FORGEWORTH_CODEX': '0'}):
            with self.assertRaises(BackendError):
                await backend.answer('hello', Mode.BUTLER, 85, Context())
        self.assertEqual(backend.history, [])

    async def test_backend_json_history_and_timeout(self):
        backend = CodexBackend()
        calls = []
        async def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if '--help' in argv:
                return 0, '--ignore-user-config --ignore-rules --ephemeral --json --sandbox'
            if 'features' in argv:
                return 0, 'shell_tool unified_exec apps plugins'
            return 0, json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Hello'}})
        with patch.dict(os.environ, {'FORGEWORTH_CODEX': '1'}), patch('os.geteuid', return_value=1000), patch('shutil.which', return_value='/bin/codex'), patch('tui.backend.run', fake_run):
            self.assertEqual(await backend.answer('hello', Mode.BUTLER, 85, Context()), 'Hello')
            await backend.answer('again', Mode.EMERGENCY, 100, Context())
        self.assertIn('Hello', calls[-1][1]['stdin'])
        self.assertIn('features.shell_tool=false', calls[-1][0])
        async def timeout_run(argv, **kwargs):
            if '--help' in argv:
                return 0, '--ignore-user-config --ignore-rules --ephemeral --json --sandbox'
            if 'features' in argv:
                return 0, 'shell_tool unified_exec apps plugins'
            raise asyncio.TimeoutError()
        with patch.dict(os.environ, {'FORGEWORTH_CODEX': '1'}), patch('os.geteuid', return_value=1000), patch('shutil.which', return_value='/bin/codex'), patch('tui.backend.run', timeout_run):
            with self.assertRaisesRegex(BackendError, 'timed out'):
                await backend.answer('hello', Mode.BUTLER, 85, Context())

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_failure_and_cancellation_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            events = []
            engine = Engine(path, events.append)
            async def fail(*args, **kwargs):
                return 9, 'failed'
            with patch('tui.engine.run', fail):
                await engine.execute('plan', lambda _: None)
            self.assertEqual(engine.states['plan'], 'failed')
            async def wait(*args, **kwargs):
                await asyncio.sleep(30)
            with patch('tui.engine.run', wait):
                task = asyncio.create_task(engine.execute('preflight', lambda _: None))
                await asyncio.sleep(.01)
                with self.assertRaises(RuntimeError):
                    await engine.execute('plan', lambda _: None)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertEqual(engine.states['preflight'], 'cancelled')
            self.assertEqual(Engine(path, events.append).states['preflight'], 'interrupted')

    async def test_backend_failure_and_unsupported_cli(self):
        for supported in (False, True):
            async def fake(argv, **kwargs):
                if '--help' in argv:
                    return 0, '--ignore-user-config --ignore-rules --ephemeral --json --sandbox' if supported else 'old cli'
                if 'features' in argv:
                    return 0, 'shell_tool unified_exec apps plugins'
                return 1, 'SECRET diagnostic must not reach user'
            with patch.dict(os.environ, {'FORGEWORTH_CODEX': '1'}), patch('os.geteuid', return_value=1000), patch('shutil.which', return_value='/bin/codex'), patch('tui.backend.run', fake):
                backend = CodexBackend()
                with self.assertRaises(BackendError) as caught:
                    await backend.answer('question', Mode.BUTLER, 85, Context())
                self.assertNotIn('SECRET', str(caught.exception))
                self.assertEqual(backend.history, [])
