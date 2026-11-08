"""Bounded streaming subprocess supervision. No shell, escalation, or detached children."""
import asyncio
import os
import signal
import codecs


async def run(argv, *, cwd=None, timeout=90, stdin=None, on_line=None, limit=1_000_000):
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd, start_new_session=True,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        limit=limit + 1)
    output = bytearray()

    async def collect():
        async def feed():
            if stdin is not None:
                try:
                    proc.stdin.write(stdin.encode())
                    await proc.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # An early exit is reported by its exit status.
                finally:
                    proc.stdin.close()
        feeder = asyncio.create_task(feed())
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        try:
            while chunk := await proc.stdout.read(4096):
                output.extend(chunk)
                if len(output) > limit:
                    raise RuntimeError('Process output exceeded safety limit')
                if on_line:
                    on_line(decoder.decode(chunk))
            if on_line:
                tail = decoder.decode(b'', final=True)
                if tail:
                    on_line(tail)
            await feeder
        finally:
            feeder.cancel()
            await asyncio.gather(feeder, return_exceptions=True)
        await proc.wait()
        return proc.returncode, output.decode(errors='replace')

    try:
        return await asyncio.wait_for(collect(), timeout)
    finally:
        # Kill the entire session even if its leader exited leaving descendants.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.communicate()

