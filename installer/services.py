"""Install the selected Handbook system tools without starting live-CD services."""

BASE_PACKAGES = ('app-admin/sysklogd', 'sys-process/cronie', 'net-misc/chrony',
                 'net-misc/networkmanager', 'app-admin/sudo')
SERVICES = ('sysklogd', 'cronie', 'chronyd', 'dbus', 'NetworkManager')


def install_base_services(target, *, binary_fallback=True, replace_dhcpcd=False):
    """Requires an authenticated/synced target and the installer's mount context.

    Registers target OpenRC services only. Never calls rc-service/start inside a
    chroot, which could interfere with the live environment's bound /run state.
    Root/user authentication and desktop session setup are separate stages.
    """
    if type(binary_fallback) is not bool or type(replace_dhcpcd) is not bool:
        raise ValueError('Binary fallback must be an explicit boolean')
    default = target.root / 'etc/runlevels/default'
    if not default.resolve().is_relative_to(target.root.resolve()):
        raise ValueError('Runlevel path escapes target')
    remove_dhcpcd = False
    if default.is_dir():
        conflicts = [p.name for p in default.iterdir()
                     if p.name in ('dhcpcd', 'netifrc', 'connman')
                     or p.name.startswith('net.') and p.name != 'net.lo']
        remove_dhcpcd = replace_dhcpcd and 'dhcpcd' in conflicts
        if remove_dhcpcd:
            conflicts.remove('dhcpcd')
        if conflicts:
            raise ValueError('Existing network services require review before NetworkManager: ' + ', '.join(sorted(conflicts)))
    options = ['/usr/bin/emerge', '--getbinpkg=y' if binary_fallback else '--getbinpkg=n',
               '--usepkg=y' if binary_fallback else '--usepkg=n', '--binpkg-respect-use=y',
               '--autounmask=n', '--verbose']
    target.chroot([*options, '--pretend', *BASE_PACKAGES], timeout=300)
    target.chroot([*options, *BASE_PACKAGES], timeout=2400)
    for service in SERVICES:
        target.chroot(['/usr/bin/test', '-x', '/etc/init.d/' + service], timeout=30)
    for service in SERVICES:
        target.chroot(['/usr/bin/env', 'rc-update', 'add', service, 'default'], timeout=30)
        if not (default / service).is_symlink():
            raise RuntimeError('OpenRC service registration did not persist: ' + service)
    if remove_dhcpcd:
        target.chroot(['/usr/bin/env', 'rc-update', 'del', 'dhcpcd', 'default'], timeout=30)
        if (default / 'dhcpcd').is_symlink():
            raise RuntimeError('Conflicting target dhcpcd registration remains')
    return {'packages': list(BASE_PACKAGES), 'services': list(SERVICES),
            'binary_fallback': binary_fallback, 'running_services': 'requires verification after boot'}
