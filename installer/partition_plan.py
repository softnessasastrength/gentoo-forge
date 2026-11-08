"""Pure GPT free-space planning. Existing partitions are never resized or cleared."""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import uuid

GIB = 1024**3
GUIDS = {'efi': 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b',
         'swap': '0657fd6d-a4ab-43c4-84e5-0933c84b4f4f',
         'root': '0fc63daf-8483-4772-8e79-3d69d8477de4'}


def valid_uuid(value):
    if not isinstance(value, str):
        raise ValueError('Missing GPT identity')
    return uuid.UUID(value)


@dataclass(frozen=True)
class NewPartition:
    number: int
    purpose: str
    start: int
    end: int  # Inclusive sector.


def parse_table(value, path, disk_bytes):
    if not re.fullmatch(r'/dev/[A-Za-z0-9_-]+', path) or type(disk_bytes) is not int or disk_bytes <= 0:
        raise ValueError('Explicit canonical device identity and positive size are required')
    if not isinstance(value, dict) or not isinstance(value.get('partitiontable'), dict):
        raise ValueError('Partition table is missing')
    table = value['partitiontable']
    if table.get('label') != 'gpt' or table.get('device') != path or table.get('unit') != 'sectors':
        raise ValueError('Only an existing GPT table on the exact selected device is supported; no automatic conversion')
    valid_uuid(table.get('id'))
    sector = table.get('sectorsize')
    if sector not in (512, 4096) or type(sector) is not int:
        raise ValueError('Unsupported or unknown logical sector size')
    first, last = table.get('firstlba'), table.get('lastlba')
    if type(first) is not int or type(last) is not int or not 2 <= first <= last < disk_bytes // sector:
        raise ValueError('GPT usable bounds are invalid')
    partitions = table.get('partitions')
    if not isinstance(partitions, list) or len(partitions) > 125:
        raise ValueError('Invalid partition list or no room for three GPT entries')
    ranges, numbers = [], set()
    for part in partitions:
        if not isinstance(part, dict):
            raise ValueError('Malformed partition entry')
        start, size = part.get('start'), part.get('size')
        if type(start) is not int or type(size) is not int or size <= 0 or not first <= start <= start + size - 1 <= last:
            raise ValueError('Invalid existing partition extent')
        match = re.fullmatch(re.escape(path) + (r'p' if path[-1].isdigit() else '') + r'([1-9][0-9]*)', str(part.get('node')))
        if not match or not 1 <= int(match[1]) <= 128 or int(match[1]) in numbers:
            raise ValueError('Unresolved or duplicate partition number')
        numbers.add(int(match[1]))
        valid_uuid(part.get('type'))
        valid_uuid(part.get('uuid'))
        ranges.append((start, start + size - 1))
    ranges.sort()
    if any(a[1] >= b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('Existing partitions overlap')
    free, cursor = [], first
    for start, end in ranges:
        if cursor < start:
            free.append((cursor, start - 1))
        cursor = end + 1
    if cursor <= last:
        free.append((cursor, last))
    return table, free, numbers


def plan(value, path, disk_bytes):
    table, free, used = parse_table(value, path, disk_bytes)
    sector = table['sectorsize']
    alignment = 1024**2 // sector
    aligned = [(((start + alignment - 1) // alignment) * alignment,
                ((end + 1) // alignment) * alignment - 1) for start, end in free]
    usable = [(start, end) for start, end in aligned if (end - start + 1) * sector >= 37 * GIB]
    if not usable:
        raise ValueError('No contiguous unallocated extent fits 1 GiB EFI + 20 GiB swap + at least 16 GiB root; NTFS will not be resized')
    start, end = max(usable, key=lambda pair: pair[1] - pair[0])
    numbers = [n for n in range(1, 129) if n not in used][:3]
    if len(numbers) != 3:
        raise ValueError('Three unused GPT partition entries are required')
    efi_end = start + GIB // sector - 1
    swap_end = efi_end + 20 * GIB // sector
    parts = [NewPartition(numbers[0], 'efi', start, efi_end),
             NewPartition(numbers[1], 'swap', efi_end + 1, swap_end),
             NewPartition(numbers[2], 'root', swap_end + 1, end)]
    result = {'version': 1, 'device': path, 'disk_bytes': disk_bytes,
              'table_id': table['id'], 'sector_size': sector,
              'existing': table['partitions'], 'free_sectors': free,
              'selected_extent': [start, end], 'new': [asdict(p) for p in parts],
              'existing_partitions_preserved': True, 'writes_authorized': False}
    result['fingerprint'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def commands(proposal):
    argv = ['sgdisk']
    for part in proposal['new']:
        n, purpose = part['number'], part['purpose']
        argv += [f'--new={n}:{part["start"]}:{part["end"]}',
                 f'--typecode={n}:{GUIDS[purpose]}', f'--change-name={n}:FORGE_{purpose.upper()}']
    return [argv + [proposal['device']]]


def authorize_space(original_target, fresh_target, original_plan, fresh_plan,
                    *, nuke_it, interactive, confirmation):
    if not nuke_it or not interactive or original_target != fresh_target or original_plan != fresh_plan:
        raise PermissionError('Fresh unchanged identity/partition plan and explicit interactive --nuke-it are required')
    start, end = fresh_plan['selected_extent']
    expected = f'ALLOCATE {fresh_target.path} {fresh_target.serial} {start}-{end} {fresh_plan["fingerprint"]}'
    if confirmation != expected:
        raise PermissionError('Exact disk/extent/plan confirmation required; existing partitions remain protected')
    return expected
