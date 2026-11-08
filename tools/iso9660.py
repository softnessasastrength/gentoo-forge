"""Bounded read-only ISO9660 extraction for trusted Gentoo VM fixture media.

No mount, block device, external archive utility or archive-selected output path.
Only caller-selected regular ISO files are read; this is not a general extractor.
"""
from pathlib import Path
import stat


class ISO:
    def __init__(self, path):
        self.path = Path(path)
        if not stat.S_ISREG(self.path.stat().st_mode):
            raise ValueError('Fixture ISO must be a regular file')
        self.size = self.path.stat().st_size
        pvd = self.read(16 * 2048, 2048)
        if pvd[:7] != b'\x01CD001\x01':
            raise ValueError('Unsupported ISO9660 primary volume')
        self.root = self.record(pvd[156:])

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self.size or size > 256 * 1024**2:
            raise ValueError('ISO extent outside safety bounds')
        with self.path.open('rb') as stream:
            stream.seek(offset)
            result = stream.read(size)
        if len(result) != size:
            raise ValueError('Truncated ISO')
        return result

    def record(self, data):
        if len(data) < 34 or data[0] < 34 or len(data) < data[0]:
            raise ValueError('Invalid ISO directory record')
        name = data[33:33 + data[32]].decode('ascii').split(';')[0].rstrip('.').lower()
        return {'name': name, 'offset': int.from_bytes(data[2:6], 'little') * 2048,
                'size': int.from_bytes(data[10:14], 'little'), 'directory': bool(data[25] & 2)}

    def children(self, directory):
        if not directory['directory'] or directory['size'] > 16 * 1024**2:
            raise ValueError('Invalid ISO directory extent')
        data = self.read(directory['offset'], directory['size'])
        position = 0
        while position < len(data):
            length = data[position]
            if length == 0:
                position = (position // 2048 + 1) * 2048
                continue
            item = self.record(data[position:position + length])
            position += length
            if item['name'] not in ('\x00', '\x01'):
                yield item

    def find(self, path):
        current = self.root
        for part in path.strip('/').lower().split('/'):
            if part in ('', '.', '..'):
                raise ValueError('Invalid ISO path')
            matches = [item for item in self.children(current) if item['name'] == part]
            if len(matches) != 1:
                raise FileNotFoundError(path)
            current = matches[0]
        return current

    def file(self, path):
        item = self.find(path)
        if item['directory']:
            raise ValueError('Expected an ISO file')
        return self.read(item['offset'], item['size'])
