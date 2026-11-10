"""Target account setup with a fixed secret-input channel; no AI authorization."""
import os
import re
import signal
import subprocess

from .bootstrap import write_target


def _password(target, username, password):
    # Never put passwords in argv, environment, files, diagnostics or model data.
    process = subprocess.Popen(['chroot', str(target.root), '/usr/bin/env', 'chpasswd'],
                               stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True,
                               env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    try:
        process.communicate((username + ':' + password + '\n').encode(), timeout=30)
        if process.returncode:
            raise RuntimeError('Target password setup failed; authentication is not configured')
    except subprocess.TimeoutExpired:
        raise TimeoutError('Target password setup timed out; authentication is not verified') from None
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
        process.wait(timeout=10)


def configure_account(target, *, username='branden', password=None, allow_locked=False):
    """Ordinary-user password + password-required sudo, or an explicit locked fixture.

    Production callers must obtain the password from a local secret prompt, never
    chat/model output. A successful return checks password status and sudo policy;
    it does not claim a successful interactive login.
    """
    if not isinstance(username, str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', username) or username in ('root', 'portage', 'sddm'):
        raise ValueError('Invalid ordinary username')
    if type(allow_locked) is not bool:
        raise ValueError('Locked-account permission must be explicit')
    if password is None:
        if not allow_locked:
            raise ValueError('A locally supplied password is required for an installed user')
    elif not isinstance(password, str) or len(password) < 12 or len(password.encode()) > 1024 or any(c in password for c in '\n\r\x00'):
        raise ValueError('Password must be 12+ characters without line breaks or NUL')
    passwd = target.root / 'etc/passwd'
    if not passwd.resolve().is_relative_to(target.root.resolve()):
        raise ValueError('Account database escapes target')
    entries = [line.split(':') for line in passwd.read_text().splitlines()
               if line and not line.startswith('#')]
    if any(len(fields) != 7 for fields in entries):
        raise ValueError('Target account database is incomplete')
    existing = [fields for fields in entries if fields[0] == username]
    if len(existing) > 1:
        raise ValueError('Target account identity is ambiguous')
    if existing:
        fields = existing[0]
        if not fields[2].isdigit() or int(fields[2]) < 1000 or fields[5:] != ['/home/' + username, '/bin/bash']:
            raise ValueError('Existing account is not the expected ordinary login user')
    else:
        target.chroot(['/usr/bin/env', 'useradd', '-m', '-s', '/bin/bash', username])
    target.chroot(['/usr/bin/env', 'usermod', '-a', '-G', 'wheel', username])
    write_target(target.root, 'etc/sudoers.d/forgeworth', '%wheel ALL=(ALL:ALL) ALL\n', 0o440)
    target.chroot(['/usr/bin/env', 'visudo', '-c'], timeout=30)
    policy = target.chroot(['/usr/bin/env', 'sudo', '-l', '-U', username], timeout=30)
    if not re.search(r'\(ALL\s*:\s*ALL\)\s+ALL', policy) or 'NOPASSWD' in policy:
        raise RuntimeError('Expected password-required wheel sudo policy is not effective')
    if password is None:
        target.chroot(['/usr/bin/env', 'passwd', '-l', username])
    else:
        _password(target, username, password)
    target.chroot(['/usr/bin/env', 'passwd', '-l', 'root'])
    for name, expected in ((username, 'L' if password is None else 'P'), ('root', 'L')):
        status = target.chroot(['/usr/bin/env', 'passwd', '-S', name], timeout=30).split()
        if len(status) < 2 or status[0] != name or status[1] != expected:
            raise RuntimeError('Target authentication status did not verify')
    return {'username': username, 'authentication': 'locked' if password is None else 'password configured',
            'root_locked': True, 'sudo_requires_password': True, 'interactive_login': 'not verified'}
