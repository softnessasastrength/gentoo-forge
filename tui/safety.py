"""Pure fail-closed disk validation. Does not open devices or execute writes."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Disk:
    path: str
    serial: str
    model: str
    size: int


def validate_target(inventory, path, active_paths, swap_paths):
    if active_paths is None or swap_paths is None:
        raise ValueError('System ancestry and active swap must be known')
    if not isinstance(inventory, dict) or not isinstance(inventory.get('blockdevices'), list):
        raise ValueError('Disk inventory is malformed')
    if any(not isinstance(items, (list, tuple)) or any(not isinstance(p, str) or not p.startswith('/dev/') for p in items)
           for items in (active_paths, swap_paths)):
        raise ValueError('Device ancestry must contain canonical device paths')
    if any(not isinstance(d, dict) for d in inventory['blockdevices']):
        raise ValueError('Disk inventory is malformed')
    candidates = [d for d in inventory['blockdevices'] if d.get('path') == path]
    if len(candidates) != 1:
        raise ValueError('Select an explicit whole disk')
    disk = candidates[0]
    if disk.get('type') != 'disk' or not re.fullmatch(r'/dev/[a-zA-Z0-9_-]+', path):
        raise ValueError('Target must be a canonical whole disk')
    if disk.get('ro') not in (False, 0):
        raise ValueError('Target is read-only or state is unknown')
    serial = disk.get('serial')
    model = disk.get('model')
    if (not isinstance(serial, str) or not serial.strip() or
            not isinstance(model, str) or not model.strip() or
            type(disk.get('size')) is not int):
        raise ValueError('Physical identity is incomplete')
    serial = serial.strip()
    pending = [disk]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict) or not isinstance(node.get('path'), str):
            raise ValueError('Device tree is incomplete')
        if not isinstance(node.get('mountpoints'), list) or any(
                p is not None and not isinstance(p, str) for p in node['mountpoints']):
            raise ValueError('Mount state is unknown')
        if any(node['mountpoints'] or []) or node.get('path') in set(active_paths) | set(swap_paths):
            raise ValueError('Target is mounted, active swap, or system ancestry')
        children = node.get('children', [])
        if not isinstance(children, list):
            raise ValueError('Device tree is incomplete')
        pending.extend(children)
    if disk['size'] < 22 * 1024**3:
        raise ValueError('Disk cannot fit EFI, swap and root')
    return Disk(path, serial, disk['model'].strip(), disk['size'])


def authorize(original, fresh, *, nuke_it, interactive, confirmation):
    # Caller must collect a NEW inventory and ancestry immediately before use.
    if not nuke_it or not interactive or original != fresh:
        raise PermissionError('Explicit interactive authorization and unchanged identity required')
    expected = f'ERASE {fresh.path} {fresh.serial} {fresh.size}'
    if confirmation != expected:
        raise PermissionError('Exact disk identity confirmation required')
    # No execution token is returned. The installer remains locked.
    return expected

