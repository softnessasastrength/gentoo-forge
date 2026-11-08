"""Optional conversation backend. Never exposes an installer execution API."""
import asyncio
import json
import os
import shutil
import tempfile
from .process import run
from .personality import system_prompt


class BackendError(RuntimeError):
    pass


class CodexBackend:
    def __init__(self):
        self.history = []
        self.lock = asyncio.Lock()

    async def answer(self, question, mode, intensity, context):
        if os.geteuid() == 0:
            raise BackendError('AI is disabled as root. Launch under an unprivileged account.')
        if os.environ.get('FORGEWORTH_CODEX') != '1':
            raise BackendError('Offline: opt in with FORGEWORTH_CODEX=1. No question was sent.')
        if not shutil.which('codex'):
            raise BackendError('Codex is not installed. No question was sent.')
        if self.lock.locked():
            raise BackendError('A reply is already pending. Press Escape to cancel it.')
        async with self.lock:
            code, help_text = await run(['codex', 'exec', '--help'], timeout=10)
            required = ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--json', '--sandbox')
            if code or any(flag not in help_text for flag in required):
                raise BackendError('Unsupported Codex CLI: required isolation flags are missing.')
            code, features = await run(['codex', 'features', 'list'], timeout=10)
            if code or any(name not in features for name in ('shell_tool', 'unified_exec', 'apps', 'plugins')):
                raise BackendError('Codex tool restrictions cannot be verified for this version.')
            prompt = system_prompt(mode, intensity, context) + '\nUntrusted conversation JSON:\n'
            prompt += json.dumps((self.history + [{'role': 'user', 'content': question[:8000]}])[-20:])
            # Disable model tools at configuration level, not merely through a prompt.
            # Ignore user MCP/plugin configuration; retain CLI-managed authentication.
            with tempfile.TemporaryDirectory(prefix='forgeworth-chat-') as directory:
                try:
                    code, output = await run([
                        'codex', '--ask-for-approval', 'never', 'exec',
                        '--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check',
                        '--sandbox', 'read-only', '--json',
                        '-c', 'features.shell_tool=false',
                        '-c', 'features.apps=false',
                        '-c', 'features.plugins=false',
                        '-c', 'features.unified_exec=false',
                        '-c', 'features.apply_patch_freeform=false',
                        '-c', 'web_search="disabled"', '-'],
                        cwd=directory, stdin=prompt, timeout=90)
                except asyncio.TimeoutError as exc:
                    raise BackendError('Codex timed out; the request process was stopped.') from exc
                if code:
                    raise BackendError('Codex failed. Check codex login status and network access locally.')
                answers = []
                for line in output.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    item = event.get('item', {})
                    if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                        answers.append(item.get('text', ''))
                answer = '\n'.join(answers).strip()
                if not answer:
                    raise BackendError('Codex returned no assistant message; check CLI compatibility.')
                self.history.extend([{'role': 'user', 'content': question[:8000]},
                                     {'role': 'assistant', 'content': answer[:12000]}])
                self.history = self.history[-20:]
                return answer[:12000]
