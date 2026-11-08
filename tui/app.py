"""Forgeworth's non-destructive full-screen terminal interface.

Install: python -m pip install -r tui/requirements.txt
Run: python -m tui.app  (from repository root)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Input, Label, Log, ProgressBar, RichLog, Static

ROOT = Path(__file__).resolve().parent.parent

CSS = """
Screen { background: #0d1520; color: #dce7ee; }
Header { background: #12283a; color: #9fe8d4; }
#dashboard { height: 1fr; }
#left { width: 58%; padding: 1 2; }
#right { width: 42%; padding: 1 2; border-left: solid #365264; }
.panel { border: round #3b6570; padding: 1 2; margin-bottom: 1; }
.heading { color: #8ce2c5; text-style: bold; }
#progress { height: 5; }
#log { height: 1fr; background: #0a111a; }
#chat { height: 1fr; background: #101e2a; }
#prompt { dock: bottom; margin-top: 1; }
#controls { height: auto; margin: 1 0; }
Button { margin-right: 1; }
#status { color: #e5c98d; }
Footer { background: #12283a; }
"""

class Forgeworth(App):
    TITLE = "GENTOO FORGE  |  FORGEWORTH"
    SUB_TITLE = "A gentleman's guide to compiling one's own misery"
    CSS = CSS
    BINDINGS = [("f1", "help", "Help"), ("f2", "focus_chat", "Butler"),
                ("f3", "focus_logs", "Logs"), ("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="dashboard"):
            with Vertical(id="left"):
                with Vertical(classes="panel"):
                    yield Static("SYSTEM PROFILE", classes="heading")
                    yield Static("Target: not selected  |  OpenRC / Btrfs / Plasma")
                    yield Static("Installation: LOCKED  |  Read-only preview")
                with Vertical(classes="panel", id="progress"):
                    yield Static("STAGE PROGRESS", classes="heading")
                    yield ProgressBar(total=100, show_eta=False, id="bar")
                    yield Label("Idle: no installation running", id="status")
                with Horizontal(id="controls"):
                    yield Button("Preflight", id="preflight", variant="primary")
                    yield Button("Plan", id="plan")
                    yield Button("Demo", id="demo")
                yield Static("OPERATIONS LOG", classes="heading")
                yield RichLog(id="log", markup=True, wrap=True, highlight=True)
            with Vertical(id="right"):
                yield Static("FORGEWORTH  //  YOUR DIGITAL BUTLER", classes="heading")
                yield RichLog(id="chat", markup=True, wrap=True, highlight=True)
                yield Input(placeholder="Ask your butler a question...", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#chat", RichLog).write(
            "[bold #8ce2c5]FORGEWORTH:[/] Good evening, sir. I see you have chosen Gentoo. "
            "An unusual way to spend a perfectly serviceable weekend."
        )
        self.query_one("#log", RichLog).write(
            "[#e5c98d]SAFETY:[/] All installation and disk-writing operations are locked."
        )

    def action_help(self) -> None:
        self.say("F1 help, F2 chat, F3 logs. Preflight and Plan are read-only. "
                 "Demo is simulated. No disk writes, sir. We do have standards.")

    def action_focus_chat(self) -> None:
        self.query_one("#prompt", Input).focus()

    def action_focus_logs(self) -> None:
        self.query_one("#log", RichLog).focus()

    def say(self, message: str) -> None:
        self.query_one("#chat", RichLog).write("[bold #8ce2c5]FORGEWORTH:[/] " + message)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        event.input.value = ""
        if not question:
            return
        self.query_one("#chat", RichLog).write("[bold #d8c28b]YOU:[/] " + question)
        self.run_worker(self.answer(question), exclusive=False, group="chat")

    async def answer(self, question: str) -> None:
        # Explicit opt-in; never grant Codex access to the target system.
        if os.environ.get("FORGEWORTH_CODEX") != "1" or not shutil.which("codex"):
            self.say("A fascinating question, sir. Live Codex chat is not enabled. "
                     "Set FORGEWORTH_CODEX=1 with Codex installed to opt in. "
                     "Until then I remain an exquisitely polite offline placeholder.")
            return
        prompt = ("You are Forgeworth, a witty, dry British butler helping a user learn Gentoo. "
                  "Be accurate, concise, and gently sarcastic. Never suggest bypassing disk "
                  "confirmation or executing destructive commands. This is an educational "
                  "chat, not permission to operate on the computer.\nUser: " + question)
        # Do not run Codex inside the repository or with root privileges.
        # An empty temporary working directory prevents project-file access.
        import tempfile
        with tempfile.TemporaryDirectory(prefix="forgeworth-chat-") as directory:
            try:
                process = await asyncio.create_subprocess_exec(
                    "codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                    prompt, cwd=directory, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()
                    self.say("The model has exceeded its allotted audience, sir. Try again.")
                    return
                if process.returncode:
                    self.say("Codex could not respond, sir. Check authentication and CLI compatibility.")
                else:
                    self.say(stdout.decode(errors="replace")[-5000:].strip() or
                             "The model returned no answer, sir. Remarkably restrained.")
            except OSError:
                self.say("Codex could not be launched, sir.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.busy:
            self.say("One operation at a time, sir. Even I have standards.")
            return
        kind = event.button.id
        if kind == "demo":
            self.run_worker(self.demo_progress(), exclusive=True, group="operation")
        elif kind in ("preflight", "plan"):
            self.run_worker(self.readonly_stage(kind), exclusive=True, group="operation")

    async def demo_progress(self) -> None:
        self.busy = True
        try:
            bar = self.query_one("#bar", ProgressBar)
            log = self.query_one("#log", RichLog)
            bar.update(total=100, progress=0)
            self.query_one("#status", Label).update("SIMULATION ONLY: demonstration progress")
            for value in range(0, 101, 5):
                bar.update(progress=value)
                if value % 25 == 0:
                    log.write(f"[#8ce2c5]DEMO[/] simulated stage {value}% (no commands executed)")
                await asyncio.sleep(0.07)
            self.say("A lovely progress bar, sir. Entirely simulated. "
                     "I would never pretend that GCC finishes this quickly.")
        finally:
            self.busy = False

    async def readonly_stage(self, kind: str) -> None:
        self.busy = True
        try:
            script = ROOT / ("scripts/00-preflight.sh" if kind == "preflight"
                             else "scripts/10-plan.sh")
            status = self.query_one("#status", Label)
            status.update(f"Running read-only {kind}; duration unknown")
            self.query_one("#bar", ProgressBar).update(total=None)
            # Do not execute as root or permit arbitrary shell arguments.
            proc = await asyncio.create_subprocess_exec(
                "bash", str(script), cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            try:
                output, _ = await asyncio.wait_for(proc.communicate(), timeout=45)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                status.update(f"{kind} timed out")
                return
            for line in output.decode(errors="replace").splitlines():
                self.query_one("#log", RichLog).write(line)
            status.update(f"{kind}: {'completed' if proc.returncode == 0 else 'needs attention'} "
                          f"(exit {proc.returncode})")
            self.say("The inspection is complete, sir. No partitions were harmed.")
        except OSError as exc:
            self.query_one("#status", Label).update(f"{kind} unavailable: {exc}")
        finally:
            self.busy = False

if __name__ == "__main__":
    Forgeworth().run()
