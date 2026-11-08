"""Forgeworth's non-destructive full-screen terminal interface.

Install: python -m pip install -r tui/requirements.txt
Run: python -m tui.app  (from repository root)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from rich.text import Text
from textual.widgets import Collapsible
from tui.backend import CodexBackend, BackendError
from tui.engine import Engine, STAGES

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, ProgressBar, RichLog, Static, Select
from tui.personality import Context, Mode
from tui.telemetry import async_snapshot, format_snapshot

CSS = """
Screen { background: #0d1520; color: #dce7ee; }
Header { background: #12283a; color: #9fe8d4; }
#dashboard { height: 1fr; }
#left { width: 55%; padding: 1 2; }
Screen.narrow #dashboard { layout: vertical; overflow-y: auto; }
Screen.narrow #left { width: 100%; height: 32; }
Screen.narrow #right { width: 100%; height: 28; border-left: none; }
.panel { height: auto; }
Collapsible { height: auto; }
#ai-status { color: #e5c98d; height: auto; }
#right { width: 45%; padding: 1 2; border-left: solid #365264; }
.panel { border: round #3b6570; padding: 1 2; margin-bottom: 1; }
.heading { color: #8ce2c5; text-style: bold; }
#progress { height: auto; }
#log { height: 1fr; background: #0a111a; }
#chat { height: 1fr; background: #101e2a; }
#prompt { dock: bottom; margin-top: 1; }
#controls { height: auto; margin: 1 0; }
Button { margin-right: 1; }
Button.-primary { background: #17675e; color: #dce7ee; }
SelectCurrent { background: #12283a; }
#status { color: #e5c98d; }
Footer { background: #12283a; }
"""

class Forgeworth(App):
    TITLE = "GENTOO FORGE  |  FORGEWORTH"
    SUB_TITLE = "A gentleman's guide to compiling one's own misery"
    CSS = CSS
    BINDINGS = [("f1", "help", "Help"), ("f2", "focus_chat", "Butler"),
                ("f3", "focus_logs", "Logs"), ("ctrl+q", "quit", "Quit"), ("escape", "cancel_chat", "Cancel AI")]

    def __init__(self) -> None:
        super().__init__()
        self.busy = False
        self.mode = Mode.BUTLER
        self.intensity = 85
        self.context = Context()
        self.backend = CodexBackend()
        self.chat_worker = None
        self.engine = Engine(Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "gentoo-forge/checkpoint.json", self.stage_event)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="dashboard"):
            with Vertical(id="left"):
                with Vertical(classes="panel"):
                    yield Static("SYSTEM PROFILE", classes="heading")
                    yield Static("Target: not selected  |  OpenRC / Btrfs / Plasma")
                    yield Static("Telemetry: collecting...", id="telemetry")
                    yield Static("Installation: LOCKED  |  Read-only preview")
                with Vertical(classes="panel", id="progress"):
                    yield Static("STAGE PROGRESS", classes="heading")
                    yield ProgressBar(total=1, show_eta=False, id="bar")
                    yield Label("Idle: no installation running", id="status")
                with Horizontal(id="controls"):
                    yield Button("Preflight", id="preflight", variant="primary")
                    yield Button("Plan", id="plan")
                    yield Button("Demo", id="demo")
                with Collapsible(title="Installation workflow — write stages locked", collapsed=True):
                    yield Static("\n".join(f"{stage.upper()}  ·  {self.engine.states[stage]}" for stage in STAGES), id="workflow")
                yield Static("OPERATIONS LOG", classes="heading")
                yield RichLog(id="log", markup=False, wrap=True, min_width=1, max_lines=2000)
            with Vertical(id="right"):
                yield Static("FORGEWORTH  //  YOUR DIGITAL BUTLER", classes="heading")
                yield Select([(m.value.title(), m.value) for m in Mode], value=Mode.BUTLER.value, id="mode", allow_blank=False)
                yield Select([(f"Sarcasm {n}%", n) for n in range(101)], value=85, id="intensity", allow_blank=False)
                yield Static("AI offline · no data shared", id="ai-status")
                yield RichLog(id="chat", markup=False, wrap=True, min_width=1, max_lines=1000)
                yield Input(placeholder="Ask your butler a question...", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#chat", RichLog).write(
            "FORGEWORTH: Good evening, sir. I see you have chosen Gentoo. "
            "An unusual way to spend a perfectly serviceable weekend."
        )
        self.query_one("#log", RichLog).write(
            "SAFETY: All installation and disk-writing operations are locked."
        )
        self.set_interval(3.0, self.refresh_telemetry)
        self.run_worker(self.refresh_telemetry(), group="telemetry", exclusive=True)

    async def refresh_telemetry(self) -> None:
        try:
            data = await async_snapshot()
        except (OSError, ValueError, asyncio.TimeoutError):
            self.query_one("#telemetry", Static).update("Host telemetry unavailable")
            return
        self.query_one('#telemetry', Static).update(format_snapshot(data))
        self.telemetry_context = format_snapshot(data)

    def action_help(self) -> None:
        self.say("F1 help, F2 chat, F3 logs. Preflight and Plan are read-only. "
                 "Demo is simulated. No disk writes, sir. We do have standards.")

    def action_focus_chat(self) -> None:
        self.query_one("#prompt", Input).focus()

    def action_focus_logs(self) -> None:
        self.query_one("#log", RichLog).focus()

    def say(self, message: str) -> None:
        self.query_one("#chat", RichLog).write(Text("FORGEWORTH: " + message))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == 'intensity' and isinstance(event.value, int):
            self.intensity = event.value
        if event.select.id == 'mode' and isinstance(event.value, str):
            self.mode = Mode(event.value)
            self.say(f'{self.mode.value.title()} mode selected, sir.')

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        event.input.value = ""
        if not question:
            return
        self.query_one("#chat", RichLog).write(Text("YOU: " + question))
        if self.chat_worker and not self.chat_worker.is_finished:
            self.say("A reply is pending. Escape cancels it.")
            return
        self.chat_worker = self.run_worker(self.answer(question), exclusive=True, group="chat")

    def action_cancel_chat(self) -> None:
        if self.chat_worker and not self.chat_worker.is_finished:
            self.chat_worker.cancel()

    async def answer(self, question: str) -> None:
        status = self.query_one("#ai-status", Static)
        status.update("AI request · sharing question, recent chat and stage metadata")
        try:
            self.say(await self.backend.answer(question, self.mode, self.intensity, self.context))
        except asyncio.CancelledError:
            self.say("Request cancelled.")
            raise
        except (BackendError, OSError, RuntimeError, asyncio.TimeoutError) as exc:
            self.say(str(exc))
        finally:
            status.update("AI idle · Escape cancels a pending reply")

    def stage_event(self, event) -> None:
        self.context = Context(stage=event.stage, status=event.status, detail=event.detail)
        self.query_one("#status", Label).update(f"{event.stage}: {event.status} {event.detail}")
        self.query_one("#workflow", Static).update("\n".join(
            f"{stage.upper()}  ·  {self.engine.states[stage]}" for stage in STAGES))
        bar = self.query_one("#bar", ProgressBar)
        bar.update(total=None if event.status == "running" else 1,
                   progress=1 if event.status == "completed" else 0)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if self.busy:
            self.say("One operation at a time, sir. Even I have standards.")
            return
        kind = event.button.id
        if kind in ("demo", "preflight", "plan"):
            self.busy = True
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
                    log.write(f"DEMO simulated stage {value}% (no commands executed)")
                await asyncio.sleep(0.07)
            self.say("A lovely progress bar, sir. Entirely simulated. "
                     "I would never pretend that GCC finishes this quickly.")
        finally:
            self.busy = False

    async def readonly_stage(self, kind: str) -> None:
        self.busy = True
        try:
            await self.engine.execute(kind, lambda line: self.query_one("#log", RichLog).write(Text(line)))
        except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
            self.query_one("#status", Label).update(f"Inspection failed: {type(exc).__name__}")
        finally:
            self.busy = False

    def on_resize(self, event) -> None:
        self.set_class(event.size.width < 100, "narrow")

if __name__ == "__main__":
    Forgeworth().run()
