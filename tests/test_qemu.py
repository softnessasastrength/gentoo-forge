import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tui.qemu import QMP, command, smoke


class Stream:
    def __init__(self, messages):
        self.incoming = io.BytesIO(b''.join(json.dumps(m).encode() + b'\n' for m in messages))
        self.outgoing = bytearray()

    def readline(self, limit):
        return self.incoming.readline(limit)

    def write(self, data):
        self.outgoing.extend(data)

    def flush(self):
        pass


class QemuTests(unittest.TestCase):
    def test_fixed_isolation_and_explicit_acceleration(self):
        args = command('/tmp/forge-qemu-test', Path('/usr/share/OVMF/OVMF_CODE_4M.fd'), 'kvm')
        self.assertEqual(args[args.index('-nic') + 1], 'none')
        self.assertEqual(args[args.index('-m') + 1], '256')
        self.assertEqual(args[args.index('-accel') + 1], 'kvm')
        self.assertFalse(any('/dev/' in arg for arg in args))
        for forbidden in ('-virtfs', '-fsdev', '-enable-kvm', '-daemonize', '-netdev'):
            self.assertNotIn(forbidden, args)
        self.assertIn('qemu64', command('/tmp/test', Path('/firmware'), 'tcg'))
        with self.assertRaises(ValueError):
            command('/tmp/test', Path('/firmware'), 'arbitrary')

    def test_qmp_handles_events_and_rejects_errors(self):
        qmp = QMP.__new__(QMP)
        qmp.stream = Stream([{'event': 'RESET'}, {'return': {'enabled': True}}])
        self.assertTrue(qmp.execute('query-kvm')['enabled'])
        self.assertEqual(json.loads(qmp.stream.outgoing)['execute'], 'query-kvm')
        qmp.stream = Stream([{'error': {'desc': 'untrusted'}}])
        with self.assertRaisesRegex(RuntimeError, 'query-status'):
            qmp.execute('query-status')
        for messages in ([], [[]], ['not-an-object']):
            qmp.stream = Stream(messages)
            with self.assertRaises(RuntimeError):
                qmp.execute('query-status')

    def test_root_missing_tools_and_duration_fail_before_launch(self):
        with patch('tui.qemu.os.geteuid', return_value=0):
            with self.assertRaises(PermissionError):
                smoke()
        with patch('tui.qemu.os.geteuid', return_value=1000), patch('tui.qemu.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'QEMU missing'):
                smoke()
            with self.assertRaises(ValueError):
                smoke(seconds=100)
