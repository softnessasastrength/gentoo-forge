"""Observe an explicitly supplied emerge log. Never starts a build or infers an ETA."""
from __future__ import annotations

import codecs
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class Compilation:
    current: str | None = None
    completed: int = 0
    total: int | None = None
    failure: bool = False

    def describe(self):
        count = f'{self.completed}/{self.total}' if self.total is not None else 'unknown'
        state = 'failure recorded' if self.failure else 'observing'
        return (f'External emerge log · {state}\n'
                f'Packages completed: {count} · current: {self.current or "unknown"}\n'
                'Package counts are not elapsed-time progress; installation remains locked.')


class EmergeParser:
    """Parse only explicit start/completion records in emerge.log or console output.

    Mid-build attachment cannot establish the already completed package count.
    Counts are published only after observing package 1; concurrent/interleaved
    build streams invalidate the count rather than creating fictitious progress.
    """
    start = re.compile(r'(?:>>> emerge|>>> Emerging) \((\d{1,6}) of (\d{1,6})\) (\S+)')
    done = re.compile(r'::: completed emerge \((\d{1,6}) of (\d{1,6})\) (\S+)')

    def __init__(self):
        self.state = Compilation()
        self.pending = ''
        self.active = None
        self.finished = set()

    def feed(self, text):
        self.pending += text
        lines = self.pending.split('\n')
        self.pending = lines.pop()[-16384:]
        for line in lines:
            self._line(line)
        return self.state

    def _line(self, line):
        match = self.start.search(line)
        if match:
            number, total = map(int, match.group(1, 2))
            package = match.group(3)[:200]
            if not 1 <= number <= total:
                return
            if number == 1 and self.active is None:
                self.finished.clear()
                self.state = Compilation(total=total)
            elif self.active is not None or total != self.state.total:
                self.state = Compilation()
            self.active = (number, total, package)
            self.state = Compilation(package, self.state.completed, self.state.total)
        match = self.done.search(line)
        if match:
            key = (*map(int, match.group(1, 2)), match.group(3)[:200])
            if key == self.active:
                if self.state.total is not None:
                    self.finished.add(key[0])
                self.state = Compilation(None, len(self.finished), self.state.total)
                self.active = None
        if '*** Failed to emerge ' in line:
            self.state = Compilation(self.state.current, self.state.completed, self.state.total, True)


class LogObserver:
    """Bounded regular-file reads, safe against FIFO substitution and rotation.

    Call poll in a worker thread. A rotated/truncated log resets all observations.
    Starting at the end avoids treating old builds as current activity.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.identity = None
        self.offset = 0
        self.parser = EmergeParser()
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def poll(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('Compilation log must be a regular file')
            identity = (info.st_dev, info.st_ino)
            if identity != self.identity or info.st_size < self.offset:
                initial = self.identity is None
                self.identity = identity
                self.offset = info.st_size if initial else 0
                self.parser = EmergeParser()
                self.decoder.reset()
            os.lseek(fd, self.offset, os.SEEK_SET)
            data = os.read(fd, 65536)
            self.offset += len(data)
            return self.parser.feed(self.decoder.decode(data))
        finally:
            os.close(fd)
