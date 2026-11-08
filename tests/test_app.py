import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch
from textual.widgets import Input, Select, Static
from tui.app import Forgeworth


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_and_concurrent_chat(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_STATE_HOME': directory}):
            app = Forgeworth()
            async with app.run_test(size=(120, 45)) as pilot:
                await pilot.press('f2')
                self.assertEqual(app.focused.id, 'prompt')
                app.query_one('#mode', Select).value = 'emergency'
                await pilot.pause()
                self.assertEqual(app.mode.value, 'emergency')
                async def reply(*args):
                    await asyncio.sleep(.15)
                    return 'An observed answer.'
                app.backend.answer = reply
                inspection_started = asyncio.Event()
                finish_inspection = asyncio.Event()
                async def inspect(*args):
                    inspection_started.set()
                    await finish_inspection.wait()
                app.engine.execute = inspect
                operation = asyncio.create_task(app.readonly_stage('preflight'))
                await inspection_started.wait()
                app.query_one('#prompt', Input).value = 'hello'
                await pilot.press('enter')
                await pilot.pause(.25)
                self.assertTrue(app.busy)
                finish_inspection.set()
                await operation
                self.assertTrue(app.chat_worker.is_finished)
                await pilot.press('f3')
                self.assertEqual(app.focused.id, 'log')
                await pilot.resize_terminal(80, 30)
                await pilot.pause()
                self.assertTrue(app.has_class('narrow'))
                self.assertLessEqual(app.query_one('#prompt').region.right, 80)
                app.save_screenshot(path=directory, filename='forgeworth.svg')

    async def test_chat_cancellation_and_literal_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_STATE_HOME': directory}):
            app = Forgeworth()
            stopped = asyncio.Event()
            async def reply(*args):
                try:
                    await asyncio.sleep(30)
                finally:
                    stopped.set()
            app.backend.answer = reply
            async with app.run_test(size=(100, 35)) as pilot:
                await pilot.press('f2')
                app.query_one('#prompt', Input).value = '[red]literal[/red]'
                await pilot.press('enter')
                await pilot.pause(.05)
                await pilot.press('escape')
                await asyncio.wait_for(stopped.wait(), 1)
                await pilot.pause()
                self.assertTrue(app.chat_worker.is_finished)
                self.assertFalse(app.query_one('#chat').markup)
