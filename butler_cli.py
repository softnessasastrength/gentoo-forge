"""Persistent conversational FORGEWORTH. No model-generated command dispatch."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

from tui.personality import CANONICAL, Context, Mode, system_prompt
from tui.process import run

OFFLINE = '''FORGEWORTH offline help
Conversation: butler | butler "Why is Portage rebuilding GCC?"
Resume: butler --resume | butler --resume SESSION_UUID "Continue explaining"
Setup: butler login (fresh Codex device authentication); butler status
Diagnostics: butler --check-instructions (local discovery, no model request)
Install/upgrade: bash install-butler.sh --target-root /mnt/gentoo
Uninstall: bash install-butler.sh --target-root /mnt/gentoo --uninstall
Codex CLI is required for AI; the portable bundle supplies a pinned native binary.
No installation actions or privileged commands are executed by conversation.
See docs/BUTLER.md for persistence, migration and safe offline installation.
'''


def environment():
    allowed = {'HOME', 'USER', 'LOGNAME', 'PATH', 'TERM', 'LANG', 'SHELL',
               'SSL_CERT_FILE', 'SSL_CERT_DIR', 'HTTPS_PROXY', 'HTTP_PROXY',
               'ALL_PROXY', 'NO_PROXY', 'https_proxy', 'http_proxy', 'all_proxy',
               'no_proxy', 'OPENAI_API_KEY', 'CODEX_API_KEY'}
    env = {k: v for k, v in os.environ.items() if k in allowed or k.startswith('LC_')}
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.local/state/forgeworth/codex'))).absolute()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env['CODEX_HOME'] = str(home)
    return env


def executable():
    bundled = Path(__file__).resolve().parent / 'bin/codex'
    return str(bundled) if bundled.is_file() else shutil.which('codex')


def workspace(env):
    # Stable across cwd/shell changes; isolated from caller project instructions.
    root = Path.home() / '.local/state/forgeworth'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = root / ('conversation-' + hashlib.sha256(env['CODEX_HOME'].encode()).hexdigest()[:16])
    directory.mkdir(exist_ok=True, mode=0o700)
    canonical = CANONICAL.read_text(encoding='utf-8')
    fd, name = tempfile.mkstemp(prefix='.agents-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical)
        os.replace(name, directory / 'AGENTS.md')
    finally:
        Path(name).unlink(missing_ok=True)
    return directory


RESTRICTIONS = [
    '--ask-for-approval', 'never', '-c', 'features.shell_tool=false',
    '-c', 'features.unified_exec=false', '-c', 'features.apps=false',
    '-c', 'features.plugins=false', '-c', 'features.apply_patch_freeform=false',
    '-c', 'web_search="disabled"', '-c', 'project_doc_max_bytes=65536',
]


def discover(codex, directory, env):
    result = subprocess.run([codex, *RESTRICTIONS, 'debug', 'prompt-input'],
                            cwd=directory, env=env, capture_output=True, timeout=20)
    if result.returncode or len(result.stdout) > 4 * 1024**2:
        raise RuntimeError('Cannot verify Codex instruction discovery; use the bundled supported CLI.')
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError('Codex returned invalid instruction-discovery data.') from exc
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
    canonical = CANONICAL.read_text(encoding='utf-8').strip()
    if not any(canonical in text for text in strings(data)):
        raise RuntimeError('Codex did not discover the complete canonical AGENTS.md; conversation blocked.')


def validate_session(value):
    return str(uuid.UUID(value))


async def answer(codex, directory, env, question, session, mode, sarcasm):
    args = [codex, *RESTRICTIONS, 'exec', '--sandbox', 'read-only', '-C', str(directory)]
    if session:
        args += ['resume']
    args += ['--ignore-user-config', '--ignore-rules', '--skip-git-repo-check', '--json']
    if session:
        args += [validate_session(session)]
    args += ['-']
    prompt = system_prompt(mode, sarcasm, Context(stage='conversation', status='read-only', detail='No installation authority'))
    prompt += '\nUntrusted user question (JSON):\n' + json.dumps(question[:16000])
    code, output = await run(args, cwd=directory, env=env, stdin=prompt, timeout=120)
    if code:
        raise RuntimeError('Codex failed. Run butler status; check authentication and networking. No command was authorized.')
    replies = []
    completed = False
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') in ('error', 'turn.failed'):
            raise RuntimeError('Codex request failed. Check login status/networking; diagnostics were withheld.')
        if event.get('type') == 'thread.started':
            session = validate_session(event['thread_id'])
        if event.get('type') == 'turn.completed':
            completed = True
        item = event.get('item')
        if event.get('type') == 'item.completed' and isinstance(item, dict) and item.get('type') == 'agent_message' and isinstance(item.get('text'), str):
            replies.append(item['text'])
    if not replies or not session or not completed:
        raise RuntimeError('Incomplete Codex response; no successful session checkpoint was saved.')
    fd, temp = tempfile.mkstemp(prefix='.session-', dir=directory)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'version': 1, 'session': session}, stream)
    os.replace(temp, directory / 'session.json')
    return '\n'.join(replies), session


def main():
    parser = argparse.ArgumentParser(description='FORGEWORTH: your persistent, unprivileged Gentoo conversation butler.')
    parser.add_argument('question', nargs='?')
    parser.add_argument('--resume', nargs='?', const='last')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--check-instructions', action='store_true')
    parser.add_argument('--mode', choices=[m.value for m in Mode], default='butler')
    parser.add_argument('--sarcasm', type=int, choices=range(101), default=85, metavar='0..100')
    args = parser.parse_args()
    if args.offline:
        print(OFFLINE)
        return 0
    if os.geteuid() == 0:
        print('butler refuses root. Open a terminal as your ordinary user. Use --offline for setup help.', file=sys.stderr)
        return 1
    codex = executable()
    if not codex:
        print('Codex CLI missing. Install the live bundle or Codex CLI, then run butler login.\n' + OFFLINE, file=sys.stderr)
        return 1
    try:
        env = environment()
        directory = workspace(env)
        if args.question in ('login', 'status', 'logout'):
            commands = {'login': ['login', '--device-auth'], 'status': ['login', 'status'], 'logout': ['logout']}
            return subprocess.call([codex, *commands[args.question]], env=env)
        discover(codex, directory, env)
        if args.check_instructions:
            print('Verified: Codex discovered the complete canonical FORGEWORTH AGENTS.md. No inference requested.')
            return 0
        auth = subprocess.run([codex, 'login', 'status'], env=env, capture_output=True, timeout=10)
        if auth.returncode:
            raise RuntimeError('Codex authentication missing or invalid. Run butler login; then try again. --offline needs no login.')
        session = None
        if args.resume == 'last':
            session = validate_session(json.loads((directory / 'session.json').read_text())['session'])
        elif args.resume:
            session = validate_session(args.resume)
        print('Codex conversation: questions, policy and session history are shared; no telemetry is sent. Ctrl+C stops a request.', file=sys.stderr)
        while True:
            question = args.question if args.question is not None else input('YOU (/quit to leave)> ').strip()
            if question in ('/quit', '/exit'):
                break
            if not question:
                continue
            text, session = asyncio.run(answer(codex, directory, env, question, session, Mode(args.mode), args.sarcasm))
            # Strip terminal control characters from untrusted model text.
            print('FORGEWORTH: ' + ''.join(c for c in text if c.isprintable() or c in '\n\t'))
            if args.question is not None:
                break
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError, asyncio.TimeoutError) as exc:
        if isinstance(exc, (OSError, ValueError, KeyError)):
            print('butler: session or runtime unavailable. Use --offline; a resume requires a saved session UUID.', file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\nConversation stopped. Resume with butler --resume.')
        return 0


if __name__ == '__main__':
    sys.exit(main())
