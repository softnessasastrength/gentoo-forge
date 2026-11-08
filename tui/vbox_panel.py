"""Textual controls for the read-only VirtualBox test assistant."""
import asyncio
from dataclasses import asdict
import os
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, Select, Static

from .virtualbox import SmokeReport, STEPS, STEP_MAP, STATUSES, collect, validate_selection


class VirtualBoxPanel(VerticalScroll):
    DEFAULT_CSS = '''
    VirtualBoxPanel { height: 22; padding: 0 1; }
    VirtualBoxPanel Static { height: auto; }
    VirtualBoxPanel Horizontal { height: auto; }
    VirtualBoxPanel Button { min-width: 10; width: 1fr; }
    #vbox-warning { color: #e5c98d; margin: 1 0; }
    #vbox-feedback { color: #8ce2c5; margin: 1 0; }
    '''

    def __init__(self):
        super().__init__(id='vbox-panel')
        state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
        self.report_path = Path(os.environ.get('FORGEWORTH_VBOX_REPORT', str(state / 'gentoo-forge/virtualbox-smoke.json')))
        self.load_error = ''
        try:
            self.report = SmokeReport(self.report_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.report = None
            self.load_error = f'Report could not be loaded ({type(exc).__name__}). Preserve it and choose another FORGEWORTH_VBOX_REPORT path.'
        self.facts = None
        self.collecting = False

    def compose(self) -> ComposeResult:
        yield Static('VIRTUALBOX TEST MODE · GUIDED / READ-ONLY', classes='heading')
        yield Static('Disk writes remain LOCKED. A VM snapshot does not verify the target disk. '
                     'Completed manual steps are user-reported, not verified.', id='vbox-warning')
        yield Select([(f'{i+1}. {s.title} · {self.report.data["steps"][s.key]["status"] if self.report else "pending"}', s.key) for i, s in enumerate(STEPS)],
                     value=STEPS[0].key, allow_blank=False, id='vbox-step')
        yield Static('', id='vbox-guide', markup=False)
        yield Select([(status.title(), status) for status in STATUSES], value='pending', allow_blank=False, id='vbox-result')
        yield Input(placeholder='Evidence/reason (no secrets); required for non-pending results', id='vbox-evidence')
        with Horizontal():
            yield Button('Record result', id='vbox-record')
            yield Button('Export report', id='vbox-export')
        yield Select([('Inside guest — host capacity unknown', 'guest'), ('On actual Linux host — measure local capacity', 'host')],
                     value='guest', allow_blank=False, id='vbox-role')
        yield Static('Host VDI storage directory (measure it on the actual host):', markup=False)
        yield Input(value='.', placeholder='Host directory that will hold the VDI', id='vbox-storage')
        yield Button('Detect (read-only)', id='vbox-detect')
        yield Static('VirtualBox: cannot be determined · Detect has not run.', id='vbox-diagnostics', markup=False)
        yield Select([], prompt='Explicitly select guest disk', id='vbox-disk')
        yield Static('No target selected.', id='vbox-disk-details', markup=False)
        yield Button('Validate selection (no authorization)', id='vbox-validate')
        yield Static(self.load_error or 'Ask questions in the chat pane at any time. Detection executes only listed read-only probes.',
                     id='vbox-feedback', markup=False)
        yield Static('', id='vbox-summary', markup=False)

    def on_mount(self):
        self.show_step()

    def feedback(self, message):
        self.query_one('#vbox-feedback', Static).update(Text(message))

    def show_step(self):
        if not self.report:
            return
        key = self.query_one('#vbox-step', Select).value
        if key not in STEP_MAP:
            return
        step = STEP_MAP[key]
        self.query_one('#vbox-guide', Static).update(Text(f'{step.purpose}\n\n{step.guidance}'))
        result = self.report.data['steps'][key]
        self.query_one('#vbox-result', Select).value = result['status']
        self.query_one('#vbox-evidence', Input).value = result['evidence']
        self.query_one('#vbox-summary', Static).update(self.report.summary())

    def on_select_changed(self, event: Select.Changed):
        event.stop()
        if event.select.id == 'vbox-step':
            self.show_step()
        elif event.select.id == 'vbox-disk' and self.report:
            # Picking a different disk invalidates any previous validation.
            self.report.data['selected_disk'] = None
            self.report.data['disk_validation'] = 'pending: selection changed'
            disks = ((self.facts or {}).get('inventory') or {}).get('blockdevices', [])
            disk = next((d for d in disks if d.get('path') == event.value), None)
            self.report.data['proposed_disk'] = ({key: disk.get(key) for key in ('path', 'size', 'model', 'serial', 'wwn', 'uuid')}
                                                 if disk else None)
            details = ('Proposed target (NOT authorized):\n' + '\n'.join(
                f'{key}: {disk.get(key) if disk.get(key) is not None else "unknown"}'
                for key in ('path', 'size', 'model', 'serial', 'wwn', 'uuid'))
                if disk else 'No target selected.')
            self.query_one('#vbox-disk-details', Static).update(Text(details))
            try:
                self.report.save()
            except OSError:
                self.feedback('Could not persist proposed selection. No disk is authorized.')
        elif event.select.id == 'vbox-role':
            self.facts = None
            self.query_one('#vbox-disk', Select).set_options([])
            if self.report:
                self.report.data['disk_validation'] = 'pending: role changed'

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        kind = event.button.id
        if not self.report:
            self.feedback(self.load_error)
            return
        if kind in ('vbox-detect', 'vbox-validate'):
            if self.collecting:
                self.feedback('Read-only detection is already running.')
                return
            self.collecting = True
            for selector in ('#vbox-role', '#vbox-disk', '#vbox-storage'):
                self.query_one(selector).disabled = True
            self.run_worker(self.inspect(validate=kind == 'vbox-validate'), group='vbox', exclusive=True)
            return
        try:
            if kind == 'vbox-record':
                self.report.record(self.query_one('#vbox-step', Select).value,
                                   self.query_one('#vbox-result', Select).value,
                                   self.query_one('#vbox-evidence', Input).value)
                self.feedback('Result saved as USER-REPORTED. No command was executed.')
                step_select = self.query_one('#vbox-step', Select)
                selected = step_select.value
                step_select.set_options([(f'{i+1}. {step.title} · {self.report.data["steps"][step.key]["status"]}', step.key) for i, step in enumerate(STEPS)])
                step_select.value = selected
                self.show_step()
            elif kind == 'vbox-export':
                paths = self.report.export()
                self.feedback('Reports saved: ' + ', '.join(map(str, paths)) + '. Review for private identifiers before attaching to a PR.')
        except (OSError, ValueError) as exc:
            self.feedback(str(exc))

    async def inspect(self, validate=False):
        selected = self.query_one('#vbox-disk', Select).value
        role = self.query_one('#vbox-role', Select).value
        proposed = self.report.data.get('proposed_disk')
        try:
            if validate and not isinstance(selected, str):
                raise ValueError('Select a guest disk explicitly first. No disk was validated.')
            self.feedback('Collecting read-only diagnostics; no commands will write to a device.')
            facts = await collect(role, self.query_one('#vbox-storage', Input).value)
            self.facts = facts
            self.report.observe(facts)
            disks = (facts.get('inventory') or {}).get('blockdevices', [])
            options = [(f'{d.get("path")} · {d.get("size", 0)/1024**3:.1f} GiB · {d.get("model") or "unknown model"} '
                        f'· serial={d.get("serial") or "MISSING"} · WWN={d.get("wwn") or "unknown"} · UUID={d.get("uuid") or "none"}', d['path'])
                       for d in disks if d.get('type') == 'disk' and d.get('path')]
            # Avoid selecting anything on behalf of the user, including the first disk.
            if not validate:
                self.query_one('#vbox-disk', Select).set_options(options if role == 'guest' else [])
            summary = (f'VirtualBox: {facts["virtualization"]}\nScope: {role} (user selected) · '
                       f'Local EFI: {facts.get("efi", "unknown")}\n'
                       f'Graphics observed: {facts.get("graphics") or "unknown / lspci unavailable"}\n'
                       f'Host allocation check: {facts["recommendation"]}\n'
                       f'Diagnostic errors: {facts["errors"] or "none"}\n'
                       'VM display plan: VMSVGA; verify vmwgfx/Mesa in guest, no physical AMDGPU/RADV override.')
            self.query_one('#vbox-diagnostics', Static).update(Text(summary))
            if validate:
                if proposed is None:
                    raise ValueError('Selected disk identity is unavailable. Detect and explicitly select again.')
                disk = validate_selection(facts, selected, expected=proposed)
                self.report.data['selected_disk'] = asdict(disk)
                self.report.data['disk_validation'] = 'read-only checks passed; NOT erase authorization'
                self.report.save()
                self.feedback(f'Identity observed: {disk.path}, {disk.model}, serial {disk.serial}, {disk.size} bytes. '
                              'Read-only checks passed. Disposability is NOT established. Writes remain LOCKED; '
                              'future writes require fresh checks, --nuke-it and separate exact interactive confirmation.')
            else:
                self.feedback('Detection complete. No target was selected or authorized. Commands and results are in the report.')
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, asyncio.TimeoutError) as exc:
            if self.report:
                self.report.data['disk_validation'] = 'blocked' if validate else 'pending'
                self.report.data['errors'] = (self.report.data['errors'] + [{'at': 'target-validation' if validate else 'detection',
                                                                          'error': str(exc)[:1000]}])[-50:]
                try:
                    self.report.save()
                except OSError:
                    pass
            self.feedback(f'Blocked: {exc}. No disk authorization granted.')
        finally:
            self.collecting = False
            for selector in ('#vbox-role', '#vbox-disk', '#vbox-storage'):
                self.query_one(selector).disabled = False
            if self.report:
                self.query_one('#vbox-summary', Static).update(self.report.summary())
