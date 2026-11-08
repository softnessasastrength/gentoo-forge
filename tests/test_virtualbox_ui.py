import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from textual.widgets import Button, Collapsible, Input, Select, Static
from tui.app import Forgeworth
from tui.backend import BackendError
from tui.vbox_panel import VirtualBoxPanel
from test_virtualbox import fixture


class VirtualBoxUITests(unittest.IsolatedAsyncioTestCase):
    async def test_workflow_detection_record_export_and_safe_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_STATE_HOME': directory}), patch('tui.vbox_panel.collect', AsyncMock(return_value=fixture())):
            app = Forgeworth(virtualbox=True)
            async with app.run_test(size=(120, 50)) as pilot:
                panel = app.query_one(VirtualBoxPanel)
                self.assertFalse(app.query_one('#vbox-section', Collapsible).collapsed)
                await panel.inspect()
                await pilot.pause()
                self.assertEqual(panel.query_one('#vbox-disk', Select).value, Select.NULL)
                await panel.inspect(validate=True)
                self.assertIn('Select a guest disk explicitly', str(panel.query_one('#vbox-feedback', Static).render()))
                panel.query_one('#vbox-disk', Select).value = '/dev/sda'
                await pilot.pause()
                await panel.inspect(validate=True)
                self.assertEqual(panel.report.data['selected_disk']['serial'], 'VB-DISPOSABLE')
                self.assertFalse(panel.report.data['configuration']['writes_enabled'])
                panel.query_one('#vbox-step', Select).value = 'install'
                await pilot.pause()
                panel.query_one('#vbox-result', Select).value = 'skipped'
                panel.query_one('#vbox-evidence', Input).value = 'Write executor remains locked'
                panel.on_button_pressed(Button.Pressed(panel.query_one('#vbox-record', Button)))
                panel.on_button_pressed(Button.Pressed(panel.query_one('#vbox-export', Button)))
                saved = json.loads(panel.report_path.read_text())
                self.assertEqual(saved['steps']['install']['status'], 'skipped')
                self.assertEqual(saved['steps']['install']['source'], 'user-reported')
                self.assertEqual(saved['installation_smoke_test'], 'unverified')
                self.assertTrue(panel.report_path.with_suffix('.txt').exists())
                await pilot.resize_terminal(80, 30)
                await pilot.pause()
                self.assertLessEqual(panel.region.right, 80)
                await pilot.press('f4')
                self.assertFalse(app.vbox_active)

    async def test_concurrent_detection_offline_questions_and_serious_safety(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_STATE_HOME': directory}):
            app = Forgeworth(virtualbox=True)
            started, release = asyncio.Event(), asyncio.Event()
            async def delayed(*args):
                started.set()
                await release.wait()
                return fixture()
            app.backend.answer = AsyncMock(side_effect=BackendError('Offline'))
            messages = []
            app.say = messages.append
            with patch('tui.vbox_panel.collect', delayed):
                async with app.run_test(size=(120, 50)) as pilot:
                    panel = app.query_one(VirtualBoxPanel)
                    panel.on_button_pressed(Button.Pressed(panel.query_one('#vbox-detect', Button)))
                    await asyncio.wait_for(started.wait(), 1)
                    await pilot.press('f2')
                    app.query_one('#prompt', Input).value = 'How do I configure VirtualBox?'
                    await pilot.press('enter')
                    await pilot.pause(.1)
                    self.assertTrue(panel.collecting)
                    self.assertTrue(any('VMSVGA' in message for message in messages))
                    self.assertTrue(panel.query_one('#vbox-role').disabled)
                    release.set()
                    await pilot.pause(.1)
                    app.backend.answer.reset_mock()
                    await app.answer('Which disk is safe to select?')
                    app.backend.answer.assert_not_called()
                    self.assertIn('NO erase permission', messages[-1])
                    self.assertNotIn('sir', messages[-1])
