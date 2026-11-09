"""AMDGPU + Mesa RADV installation for the requested Radeon workstation."""
import re
from .bootstrap import write_target
from .portage import validate_use_flags

PACKAGES = ('sys-kernel/linux-firmware', 'media-libs/mesa', 'x11-drivers/xf86-video-amdgpu')
FLAGS = {'media-libs/mesa': ['X', 'vulkan', 'wayland', 'video_cards_radeonsi'],
         'sys-kernel/linux-firmware': ['redistributable', 'initramfs']}


def install_amd_graphics(target, *, binary_fallback=True):
    """Requires the synced boot-stack target and its signature-enforcing policy.

    Package installation/module presence are verified here. A VM without AMD
    passthrough cannot prove RX 6600 XT rendering or hardware firmware loading.
    """
    if type(binary_fallback) is not bool:
        raise ValueError('Binary preference must be an explicit boolean')
    validate_use_flags(target, FLAGS)
    make_conf = target.root / 'etc/portage/make.conf'
    original = make_conf.read_text()
    include = 'source /etc/portage/forge-graphics.conf'
    if include not in original.splitlines():
        write_target(target.root, 'etc/portage/make.conf', original + '\n' + include + '\n')
    write_target(target.root, 'etc/portage/forge-graphics.conf', 'VIDEO_CARDS="amdgpu radeonsi"\n')
    write_target(target.root, 'etc/portage/package.use/forge-graphics',
                 'media-libs/mesa X vulkan wayland\n'
                 'sys-kernel/linux-firmware redistributable initramfs\n')
    # Limit the extra license acceptance to redistributable firmware only.
    write_target(target.root, 'etc/portage/package.license/forge-firmware',
                 'sys-kernel/linux-firmware linux-fw-redistributable\n')
    options = ['/usr/bin/emerge', '--getbinpkg=y' if binary_fallback else '--getbinpkg=n',
               '--usepkg=y' if binary_fallback else '--usepkg=n', '--binpkg-respect-use=y',
               '--autounmask=n', '--verbose']
    target.chroot([*options, '--pretend', *PACKAGES], timeout=300)
    target.chroot([*options, *PACKAGES], timeout=3600)
    versions = [p.name for p in (target.root / 'usr/lib/modules').iterdir() if p.is_dir() and not p.is_symlink()]
    if not versions or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}', version) for version in versions):
        raise RuntimeError('No valid installed kernel module tree')
    for version in versions:
        target.chroot(['/usr/bin/env', 'modinfo', '-k', version, 'amdgpu'], timeout=60)
    firmware = target.root / 'usr/lib/firmware/amdgpu'
    if not firmware.is_dir() or not any(firmware.iterdir()):
        raise RuntimeError('AMDGPU firmware payload is missing')
    write_target(target.root, 'etc/dracut.conf.d/forge-amdgpu.conf',
                 'add_drivers+=" amdgpu "\nearly_microcode="yes"\n')
    target.chroot(['/usr/bin/env', 'dracut', '--regenerate-all', '--force'], timeout=600)
    return {'driver': 'amdgpu', 'mesa_driver': 'radeonsi', 'vulkan': 'RADV',
            'packages': list(PACKAGES), 'binary_fallback': binary_fallback,
            'hardware_rendering': 'not verified', 'microcode_application': 'requires hardware verification'}
