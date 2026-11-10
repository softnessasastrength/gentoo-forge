import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from installer.accounts import configure_account


class AccountTests(unittest.TestCase):
    def target(self, directory):
        target = Mock(root=Path(directory))
        (target.root / 'etc').mkdir()
        (target.root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\n')
        def call(argv, **kwargs):
            if 'sudo' in argv: return '(ALL : ALL) ALL\n'
            if '-S' in argv: return argv[-1] + ' L 2026-01-01 0 99999 7 -1\n'
            return ''
        target.chroot.side_effect = call
        return target

    def test_no_implicit_locked_install_or_model_style_username(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            for options in ({}, {'username': 'root', 'allow_locked': True},
                            {'username': 'name; command', 'allow_locked': True},
                            {'password': 'long-password\nroot:injection'}):
                with self.assertRaises(ValueError): configure_account(target, **options)
            target.chroot.assert_not_called()

    def test_explicit_locked_fixture_and_password_required_sudo(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            result = configure_account(target, allow_locked=True)
            self.assertEqual(result['authentication'], 'locked')
            self.assertEqual((target.root / 'etc/sudoers.d/forgeworth').stat().st_mode & 0o777, 0o440)
            self.assertNotIn('NOPASSWD', (target.root / 'etc/sudoers.d/forgeworth').read_text())

    def test_password_only_travels_over_stdin_and_is_never_in_child_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            original = target.chroot.side_effect
            target.chroot.side_effect = lambda argv, **kw: ('branden P 2026-01-01\n' if '-S' in argv and argv[-1] == 'branden' else original(argv, **kw))
            process = Mock(pid=987654, returncode=0)
            secret = 'A-unique-test-password-123'
            with patch('installer.accounts.subprocess.Popen', return_value=process) as spawn, patch('installer.accounts.os.killpg'):
                configure_account(target, password=secret)
            self.assertNotIn(secret, repr(spawn.call_args))
            self.assertEqual(process.communicate.call_args.args[0], ('branden:' + secret + '\n').encode())
            self.assertNotIn(secret, repr(target.chroot.call_args_list))

    def test_refuses_to_repurpose_system_account(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            (target.root / 'etc/passwd').write_text('branden:x:200:200:service:/var/empty:/sbin/nologin\n')
            with self.assertRaises(ValueError): configure_account(target, allow_locked=True)
            target.chroot.assert_not_called()

    def test_password_failure_does_not_disclose_secret_or_program_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            target = self.target(directory)
            secret = 'Private-test-secret-123'
            process = Mock(pid=987654, returncode=1)
            with patch('installer.accounts.subprocess.Popen', return_value=process), patch('installer.accounts.os.killpg'):
                with self.assertRaisesRegex(RuntimeError, 'password setup failed') as failure:
                    configure_account(target, password=secret)
            self.assertNotIn(secret, str(failure.exception))
