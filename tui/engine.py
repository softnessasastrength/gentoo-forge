"""Deterministic read-only workflow. Write stages deliberately have no executor."""
import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from .process import run

ROOT = Path(__file__).resolve().parent.parent
STAGES = ('preflight', 'plan', 'bootstrap', 'chroot', 'kernel', 'desktop', 'finalize')


@dataclass(frozen=True)
class Event:
    stage: str
    status: str
    detail: str = ''


class Engine:
    def __init__(self, checkpoint, emit):
        self.checkpoint = Path(checkpoint)
        self.emit = emit
        self.lock = asyncio.Lock()
        self.states = {stage: 'locked' if i > 1 else 'pending' for i, stage in enumerate(STAGES)}
        if self.checkpoint.exists():
            saved = json.loads(self.checkpoint.read_text())
            if saved.get('version') != 1:
                raise ValueError('Unsupported checkpoint version')
            # Inspection is always repeated after restart; never trust stale disk state.
            for stage in STAGES[:2]:
                if saved.get('states', {}).get(stage) in ('running', 'failed', 'cancelled'):
                    self.states[stage] = 'interrupted'

    def publish(self, event):
        self.states[event.stage] = event.status
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix='.checkpoint-', dir=self.checkpoint.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'states': self.states}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(self.checkpoint)
        finally:
            temp.unlink(missing_ok=True)
        self.emit(event)

    async def execute(self, stage, on_line):
        if stage not in STAGES[:2]:
            raise PermissionError('Installation writes are not implemented or authorized')
        if self.lock.locked():
            raise RuntimeError('An inspection is already running')
        async with self.lock:
            self.publish(Event(stage, 'running'))
            script = '00-preflight.sh' if stage == 'preflight' else '10-plan.sh'
            try:
                code, _ = await run(['bash', str(ROOT / 'scripts' / script)],
                                    cwd=ROOT, timeout=45, on_line=on_line)
                self.publish(Event(stage, 'completed' if code == 0 else 'failed', f'Exit {code}'))
            except asyncio.CancelledError:
                self.publish(Event(stage, 'cancelled'))
                raise
            except Exception as exc:
                self.publish(Event(stage, 'failed', type(exc).__name__))
                raise

