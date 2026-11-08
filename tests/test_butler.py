import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import butler_cli as cli
from tools.install_butler import install
from tui.personality import CANONICAL, Context, Mode, system_prompt

SESSION = '12345678-1234-4234-8234-123456789abc'


class ButlerTests(unittest.TestCase):
    def test_shared_canonical_policy(self):
        self.assertIn(CANONICAL.read_text().strip(), system_prompt(Mode.BUTLER, 85, Context()))

    def test_install_upgrade_uninstall_and_shell_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            install(target)
            launcher = target / 'usr/local/bin/butler'
            self.assertTrue(os.access(launcher, os.X_OK))
            policy = target / 'usr/local/lib/gentoo-forge/current/forgeworth/AGENTS.md'
            self.assertEqual(policy.read_text(), CANONICAL.read_text())
            initial = policy.resolve()
            install(target)
            self.assertEqual(policy.resolve(), initial)
            for shell in ('sh', 'bash', 'zsh'):
                if shutil.which(shell):
                    env = dict(os.environ, PATH=str(launcher.parent) + os.pathsep + os.environ['PATH'])
                    result = subprocess.run([shell, '-c', 'butler --offline'], cwd='/', env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('FORGEWORTH offline help', result.stdout)
            user_state = target / 'home/branden/.local/state/forgeworth'
            user_state.mkdir(parents=True)
            (user_state / 'keep').write_text('conversation')
            install(target, uninstall=True)
            self.assertFalse(launcher.exists())
            self.assertEqual((user_state / 'keep').read_text(), 'conversation')

    def test_target_symlinks_and_foreign_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'usr').symlink_to('/usr')
            with self.assertRaises(ValueError):
                install(root)
            (root / 'usr').unlink()
            (root / 'usr/local/bin').mkdir(parents=True)
            (root / 'usr/local/bin/butler').write_text('unrelated')
            with self.assertRaises(ValueError):
                install(root)

    def test_install_permissions_survive_private_live_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            old = os.umask(0o077)
            try:
                install(Path(directory))
            finally:
                os.umask(old)
            for name in ('usr/local', 'usr/local/lib/gentoo-forge/releases',
                         'usr/local/lib/gentoo-forge/current/forgeworth'):
                self.assertEqual((Path(directory) / name).stat().st_mode & 0o777, 0o755)

    def test_discovery_fails_closed_without_complete_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            for output, passed in [([{'text': CANONICAL.read_text()}], True), ([{'text': 'FORGEWORTH'}], False)]:
                result = subprocess.CompletedProcess([], 0, json.dumps(output).encode(), b'')
                with patch('subprocess.run', return_value=result):
                    if passed:
                        cli.discover('codex', Path(directory), {})
                    else:
                        with self.assertRaises(RuntimeError):
                            cli.discover('codex', Path(directory), {})

    def test_actual_codex_instruction_discovery(self):
        # Explicitly exercise the real CLI when available; CI reports absence.
        codex = shutil.which('codex')
        if not codex:
            self.skipTest('Codex CLI unavailable; run the live bundle integration check')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / 'conversation'
            work.mkdir()
            (work / 'AGENTS.md').write_text(CANONICAL.read_text())
            home = root / 'codex'
            home.mkdir()
            env = {'HOME': str(root), 'PATH': os.environ['PATH'], 'CODEX_HOME': str(home)}
            cli.discover(codex, work, env)

    def test_missing_cli_root_and_missing_auth(self):
        with patch('sys.argv', ['butler']), patch('os.geteuid', return_value=0):
            self.assertEqual(cli.main(), 1)
        with patch('sys.argv', ['butler', 'hello']), patch('os.geteuid', return_value=1000), patch('butler_cli.executable', return_value=None):
            self.assertEqual(cli.main(), 1)
        with tempfile.TemporaryDirectory() as directory, patch('sys.argv', ['butler', 'hello']), patch('os.geteuid', return_value=1000), patch('butler_cli.executable', return_value='codex'), patch('butler_cli.environment', return_value={}), patch('butler_cli.workspace', return_value=Path(directory)), patch('butler_cli.discover'), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(cli.main(), 1)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_shot_resume_exact_arguments_and_persistence(self):
        calls = []
        async def fake(argv, **kwargs):
            calls.append((argv, kwargs))
            return 0, '\n'.join(map(json.dumps, [
                {'type': 'thread.started', 'thread_id': SESSION},
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Observed reply'}},
                {'type': 'turn.completed'}]))
        with tempfile.TemporaryDirectory() as directory, patch('butler_cli.run', fake):
            root = Path(directory)
            question = '$(touch NEVER); --dangerously-bypass-approvals-and-sandbox'
            text, session = await cli.answer('codex', root, {}, question, None, Mode.BUTLER, 85)
            self.assertEqual(text, 'Observed reply')
            self.assertEqual(json.loads((root / 'session.json').read_text())['session'], SESSION)
            self.assertEqual((root / 'session.json').stat().st_mode & 0o777, 0o600)
            await cli.answer('codex', root, {}, 'again', session, Mode.EMERGENCY, 100)
            self.assertIn('resume', calls[-1][0])
            self.assertIn(SESSION, calls[-1][0])
            self.assertNotIn('--ephemeral', calls[-1][0])
            self.assertIn('read-only', calls[-1][0])
            self.assertNotIn(question, calls[0][0])
            self.assertIn(question, calls[0][1]['stdin'])
            self.assertIn('features.shell_tool=false', calls[0][0])

    async def test_failed_request_does_not_save_success(self):
        async def fail(*args, **kwargs):
            return 0, json.dumps({'type': 'turn.failed', 'error': 'SECRET'})
        with tempfile.TemporaryDirectory() as directory, patch('butler_cli.run', fail):
            with self.assertRaises(RuntimeError) as error:
                await cli.answer('codex', Path(directory), {}, 'hello', None, Mode.BUTLER, 85)
            self.assertNotIn('SECRET', str(error.exception))
            self.assertFalse((Path(directory) / 'session.json').exists())
