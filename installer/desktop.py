"""Plasma/OpenRC desktop stage; login/rendering verification remains separate."""
import re

from .bootstrap import write_target
from .portage import select_profile, validate_use_flags

PACKAGES = ('kde-plasma/plasma-meta', 'kde-apps/konsole', 'kde-apps/dolphin',
            'gui-apps/sddm', 'gui-libs/display-manager-init', 'x11-base/xwayland',
            'media-video/pipewire', 'media-video/wireplumber', 'sys-auth/elogind')
FLAGS = {
    'kde-plasma/plasma-meta': ['elogind', 'sddm', 'xwayland', 'networkmanager', 'pulseaudio', 'systemd'],
    'gui-apps/sddm': ['elogind', 'systemd'],
    'media-video/pipewire': ['sound-server', 'pulseaudio', 'pipewire-alsa', 'elogind', 'X', 'systemd', 'system-service'],
    'media-video/wireplumber': ['elogind', 'systemd', 'system-service'],
}


def install_desktop(target, *, username='branden', binary_fallback=True):
    """Requires verified Stage3/boot/base-services stages and an existing user.

    Uses the synced repository, validates available flags, and asks Portage to
    resolve the profile's world update with the desktop additions. Does not start
    daemons in the chroot, install a password, or enable automatic login.
    """
    if type(binary_fallback) is not bool or not isinstance(username, str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', username):
        raise ValueError('Invalid desktop options')
    default = target.root / 'etc/runlevels/default'
    if not default.resolve().is_relative_to(target.root.resolve()):
        raise ValueError('Runlevel path escapes target')
    for service in ('xdm', 'lightdm', 'gdm', 'greetd'):
        if (default / service).is_symlink():
            raise ValueError('Existing display manager requires review: ' + service)
    profile = select_profile(target, 'plasma')
    validate_use_flags(target, FLAGS)
    write_target(target.root, 'etc/portage/package.use/forge-desktop',
                 'kde-plasma/plasma-meta elogind sddm xwayland networkmanager pulseaudio -systemd\n'
                 'gui-apps/sddm elogind -systemd\n'
                 'media-video/pipewire sound-server pulseaudio pipewire-alsa elogind X -systemd -system-service\n'
                 'media-video/wireplumber elogind -systemd -system-service\n')
    options = ['/usr/bin/emerge', '--getbinpkg=y' if binary_fallback else '--getbinpkg=n',
               '--usepkg=y' if binary_fallback else '--usepkg=n', '--binpkg-respect-use=y',
               '--autounmask=n', '--verbose', '--update', '--deep', '--newuse']
    target.chroot([*options, '--pretend', '@world', *PACKAGES], timeout=600)
    target.chroot([*options, '@world', *PACKAGES], timeout=14400)
    sessions = sorted(p for p in (target.root / 'usr/share/wayland-sessions').glob('plasma*.desktop')
                      if p.is_file() and not p.is_symlink())
    if not sessions:
        raise RuntimeError('Installed Plasma Wayland session is missing')
    for path in ('/usr/bin/startplasma-wayland', '/usr/bin/Xwayland', '/usr/bin/gentoo-pipewire-launcher',
                 '/usr/bin/pipewire', '/usr/bin/wireplumber', '/etc/init.d/elogind', '/etc/init.d/display-manager'):
        target.chroot(['/usr/bin/test', '-x', path], timeout=30)
    if not (target.root / 'etc/xdg/autostart/pipewire.desktop').is_file():
        raise RuntimeError('Gentoo PipeWire user-session startup is missing')
    write_target(target.root, 'etc/conf.d/display-manager', 'DISPLAYMANAGER="sddm"\n')
    # The greeter may use X11 while the selected user session uses Wayland.
    write_target(target.root, 'etc/sddm.conf.d/forgeworth.conf',
                 '[General]\nDisplayServer=x11\n[Users]\nRememberLastSession=true\n')
    write_target(target.root, 'var/lib/sddm/state.conf',
                 '[Last]\nUser=' + username + '\nSession=/usr/share/wayland-sessions/' + sessions[0].name + '\n')
    target.chroot(['/usr/bin/env', 'chown', 'sddm:sddm', '/var/lib/sddm/state.conf'], timeout=30)
    for service, level in (('elogind', 'boot'), ('dbus', 'default'), ('display-manager', 'default')):
        target.chroot(['/usr/bin/env', 'rc-update', 'add', service, level], timeout=30)
        if not (target.root / 'etc/runlevels' / level / service).is_symlink():
            raise RuntimeError('Desktop service registration did not persist: ' + service)
    return {'profile': profile, 'packages': list(PACKAGES), 'session': sessions[0].name,
            'automatic_login': False, 'binary_fallback': binary_fallback,
            'desktop_login': 'not verified', 'audio_devices': 'requires session/hardware verification'}
