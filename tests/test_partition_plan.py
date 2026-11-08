import copy
import unittest
from installer.partition_plan import plan, commands, authorize_space
from installer.storage import Target


def existing_table():
    return {'partitiontable': {'label': 'gpt', 'id': '12345678-1234-4234-8234-123456789abc',
            'device': '/dev/sda', 'unit': 'sectors', 'firstlba': 34, 'lastlba': 3907029134,
            'sectorsize': 512, 'partitions': [{'node': '/dev/sda1', 'start': 2048,
            'size': 3395026944, 'type': 'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7',
            'uuid': '87654321-1234-4234-8234-123456789abc', 'name': 'Basic data partition'}]}}


class PreservationPlanTests(unittest.TestCase):
    def test_existing_ntfs_unchanged_and_only_trailing_space_allocated(self):
        table = existing_table()
        original = copy.deepcopy(table)
        value = plan(table, '/dev/sda', 2000398934016)
        self.assertEqual(table, original)
        self.assertEqual(value['existing'], table['partitiontable']['partitions'])
        self.assertEqual(value['selected_extent'], [3395028992, 3907028991])
        self.assertEqual([p['number'] for p in value['new']], [2, 3, 4])
        self.assertEqual([(p['end'] - p['start'] + 1) * 512 / 1024**3 for p in value['new']], [1, 20, 223.140625])
        for word in commands(value)[0]:
            self.assertNotIn('--clear', word)
            self.assertNotIn('--zap', word)
            self.assertNotIn('--delete', word)
            self.assertNotIn('--resize', word)
            self.assertFalse(word.startswith('--new=1:'))

    def test_mbr_overlap_insufficient_space_and_wrong_disk_fail_closed(self):
        cases = []
        value = existing_table(); value['partitiontable']['label'] = 'dos'; cases.append(value)
        value = existing_table(); value['partitiontable']['device'] = '/dev/sdb'; cases.append(value)
        value = existing_table(); value['partitiontable']['partitions'][0]['size'] = 3907027087; cases.append(value)
        value = existing_table(); value['partitiontable']['partitions'].append(value['partitiontable']['partitions'][0].copy()); cases.append(value)
        for value in cases:
            with self.assertRaises(ValueError):
                plan(value, '/dev/sda', 2000398934016)

    def test_exact_scope_authorization_and_changed_plan(self):
        value = plan(existing_table(), '/dev/sda', 2000398934016)
        disk = Target('/dev/sda', 'SYNTHETIC', 'Fixture', 2000398934016, '8:0')
        text = f'ALLOCATE /dev/sda SYNTHETIC 3395028992-3907028991 {value["fingerprint"]}'
        self.assertEqual(authorize_space(disk, disk, value, value, nuke_it=True, interactive=True, confirmation=text), text)
        for nuke, interactive, confirmation in [(False, True, text), (True, False, text), (True, True, 'yes')]:
            with self.assertRaises(PermissionError):
                authorize_space(disk, disk, value, value, nuke_it=nuke, interactive=interactive, confirmation=confirmation)
        changed = copy.deepcopy(value); changed['selected_extent'][0] += 2048
        with self.assertRaises(PermissionError):
            authorize_space(disk, disk, value, changed, nuke_it=True, interactive=True, confirmation=text)
