import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from installer.bootstrap import TargetMounts, base_configuration, validate_archive, write_target, create_subvolumes
from installer.storage import Target
from tools.gentoo_vm import check_resources


def archive(path, entries):
    with tarfile.open(path, 'w:xz') as output:
        for name, kind, link in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.linkname = link
            output.addfile(item)


class BootstrapTests(unittest.TestCase):
    def test_legitimate_absolute_service_link_without_following_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stage.xz'
            archive(path, [('etc/init.d/service', tarfile.REGTYPE, ''),
                           ('etc/runlevels/default/service', tarfile.SYMTYPE, '/etc/init.d/service')])
            self.assertEqual(validate_archive(path), 2)

    def test_traversal_special_devices_and_symlink_ancestor_rejected(self):
        cases = [[('../escape', tarfile.REGTYPE, '')], [('/absolute', tarfile.REGTYPE, '')],
                 [('etc/link', tarfile.SYMTYPE, '../../outside')], [('dev/disk', tarfile.BLKTYPE, '')],
                 [('etc/link', tarfile.SYMTYPE, '/etc'), ('etc/link/escape', tarfile.REGTYPE, '')],
                 [('file', tarfile.LNKTYPE, '/etc/shadow')]]
        with tempfile.TemporaryDirectory() as directory:
            for index, entries in enumerate(cases):
                path = Path(directory) / f'{index}.xz'
                archive(path, entries)
                with self.subTest(entries=entries), self.assertRaises(ValueError):
                    validate_archive(path)

    def test_target_writes_replace_leaf_symlink_but_reject_parent_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'root'; root.mkdir()
            outside = parent / 'outside'; outside.mkdir()
            victim = outside / 'keep'; victim.write_text('preserve')
            (root / 'leaf').symlink_to(victim)
            write_target(root, 'leaf', 'configuration', 0o600)
            self.assertEqual(victim.read_text(), 'preserve')
            self.assertFalse((root / 'leaf').is_symlink())
            self.assertEqual((root / 'leaf').stat().st_mode & 0o777, 0o600)
            (root / 'escape').symlink_to(outside)
            for relative in ('escape/keep', '../outside/keep', '/etc/passwd'):
                with self.assertRaises(ValueError):
                    write_target(root, relative, 'bad')

    def test_mount_cleanup_on_intermediate_failure_and_private_propagation(self):
        target = Target('/dev/sdz', 'SYNTHETIC', 'Disposable', 64 * 1024**3, '8:240')
        storage = {'target': target.__dict__, 'partitions': {p: '/dev/sdz' + str(i) for i, p in enumerate(('root', 'efi', 'swap'), 1)},
                   'filesystems': {p: {'UUID': p, 'TYPE': p} for p in ('root', 'efi', 'swap')}}
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def fake(argv, **kwargs):
                calls.append(argv)
                if argv[0] == 'mount' and any('subvol=@home' in a for a in argv):
                    raise RuntimeError('injected mount failure')
                return ''
            with patch('os.geteuid', return_value=0), patch('installer.bootstrap.inspect', return_value=target), patch('installer.bootstrap.filesystem', side_effect=lambda path: storage['filesystems'][next(p for p, v in storage['partitions'].items() if v == path)]), patch('installer.bootstrap.tempfile.mkdtemp', return_value=directory), patch('installer.bootstrap.os.rmdir'), patch('installer.bootstrap.command', side_effect=fake):
                with self.assertRaises(RuntimeError):
                    with TargetMounts(storage):
                        self.fail('must not reach mounted state')
            self.assertIn(['umount', directory], calls)
            self.assertFalse(any(argv == ['umount', '/'] for argv in calls))

    def test_fstab_separates_root_home_and_snapshots_by_uuid(self):
        with tempfile.TemporaryDirectory() as directory:
            fs = {p: {'UUID': p + '-uuid'} for p in ('root', 'efi', 'swap')}
            base_configuration(Path(directory), {'filesystems': fs})
            text = (Path(directory) / 'etc/fstab').read_text()
            self.assertIn('subvol=@home,', text)
            self.assertIn('subvol=@home_snapshots,', text)
            self.assertIn('UUID=swap-uuid none swap', text)
            self.assertNotIn('/dev/sd', text)

    def test_low_memory_guard_prevents_repeating_chromebook_oom(self):
        with self.assertRaises(RuntimeError):
            check_resources(2048, 'MemAvailable: 1800000 kB\n')
        check_resources(2048, 'MemAvailable: 5000000 kB\n')
        for memory in (256, 1024, 16384, True):
            with self.assertRaises(ValueError):
                check_resources(memory, 'MemAvailable: 50000000 kB\n')

    def test_offline_dns_is_explicit_and_never_fabricates_a_resolver(self):
        for required in (True, False):
            with tempfile.TemporaryDirectory() as directory:
                context = TargetMounts({})
                context.root = Path(directory)
                with patch('installer.bootstrap.command', return_value=''), patch('installer.bootstrap.Path.read_text', side_effect=FileNotFoundError):
                    if required:
                        with self.assertRaisesRegex(RuntimeError, 'DNS configuration is missing'):
                            context.pseudo()
                    else:
                        context.pseudo(require_dns=False)
                if not required:
                    text = (Path(directory) / 'etc/resolv.conf').read_text()
                    self.assertIn('offline fixture', text)
                    self.assertNotIn('nameserver', text)

    def test_chroot_supervision_preserves_arguments_and_reports_bounded_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'var/tmp').mkdir(parents=True)
            context = TargetMounts({})
            context.root = root
            from unittest.mock import Mock
            process = Mock(pid=987654)
            process.wait.return_value = 2
            def spawn(argv, **kwargs):
                self.assertEqual(argv[-1], 'argument with spaces; $(false)')
                self.assertTrue(kwargs['start_new_session'])
                kwargs['stdout'].write(b'x' * 20000 + b'\x1bFailure detail')
                return process
            with patch('installer.bootstrap.subprocess.Popen', side_effect=spawn), patch('installer.bootstrap.os.killpg') as kill:
                with self.assertRaisesRegex(RuntimeError, 'Failure detail') as failure:
                    context.chroot(['/usr/bin/false', 'argument with spaces; $(false)'])
                self.assertLess(len(str(failure.exception)), 17000)
                self.assertNotIn('\x1b', str(failure.exception))
                self.assertEqual(kill.call_count, 2)

    def test_chroot_timeout_stops_entire_process_group(self):
        import subprocess
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'var/tmp').mkdir(parents=True)
            context = TargetMounts({}); context.root = root
            process = Mock(pid=987654)
            process.wait.side_effect = [subprocess.TimeoutExpired('chroot', .01), 0, 0]
            with patch('installer.bootstrap.subprocess.Popen', return_value=process), patch('installer.bootstrap.os.killpg') as kill:
                with self.assertRaises(subprocess.TimeoutExpired):
                    context.chroot(['/usr/bin/sleep', '999'], timeout=.01)
                self.assertEqual(kill.call_count, 2)

    def test_swap_activation_checks_uuid_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            context = TargetMounts({'partitions': {'swap': '/dev/mock-swap'},
                                    'filesystems': {'swap': {'UUID': 'EXPECTED'}}})
            context.mounts = [(Path(directory), False)]
            with patch('installer.bootstrap.filesystem', return_value={'TYPE': 'swap', 'UUID': 'OTHER'}), patch('installer.bootstrap.command') as command:
                with self.assertRaisesRegex(ValueError, 'identity changed'):
                    context.activate_swap()
                command.assert_not_called()
            with patch('installer.bootstrap.filesystem', return_value={'TYPE': 'swap', 'UUID': 'EXPECTED'}), patch('installer.bootstrap.command') as command:
                context.activate_swap()
                with self.assertRaises(ValueError):
                    context.activate_swap()
                context.__exit__(None, None, None)
                self.assertIn(unittest.mock.call(['swapon', '--priority', '10', '/dev/mock-swap']), command.call_args_list)
                self.assertIn(unittest.mock.call(['swapoff', '/dev/mock-swap'], timeout=120), command.call_args_list)
                self.assertFalse(context.swap_active)

    def test_auto_accelerator_uses_actual_api_and_falls_back_without_permission_changes(self):
        from tools.gentoo_vm import resolve_accelerator
        with patch('tools.gentoo_vm.os.open', return_value=123) as opened, patch('tools.gentoo_vm.os.close') as closed, patch('tools.gentoo_vm.fcntl.ioctl', return_value=12):
            self.assertEqual(resolve_accelerator('auto'), 'kvm')
            self.assertEqual(opened.call_args.args[0], '/dev/kvm')
            closed.assert_called_once_with(123)
        with patch('tools.gentoo_vm.os.open', side_effect=PermissionError):
            self.assertEqual(resolve_accelerator('auto'), 'tcg')
        with patch('tools.gentoo_vm.os.open') as opened:
            self.assertEqual(resolve_accelerator('tcg'), 'tcg')
            opened.assert_not_called()
        with self.assertRaises(ValueError):
            resolve_accelerator('arbitrary')

    def test_serial_reports_fragmented_stage_without_claiming_completion(self):
        from contextlib import redirect_stdout
        from tools.gentoo_vm import Serial
        from unittest.mock import Mock
        connection = Mock()
        connection.recv.side_effect = [b'FORGE_PHA', b'SE: extracting archive\r\n', b'FORGE_TEST_EXIT:0']
        log = io.BytesIO(); displayed = io.StringIO()
        with redirect_stdout(displayed):
            result = Serial(connection, log).wait(rb'FORGE_TEST_EXIT:0', 1)
        self.assertIn(b'FORGE_TEST_EXIT:0', result)
        self.assertEqual(displayed.getvalue(), 'Guest stage:  extracting archive\n')
        self.assertNotIn('%', displayed.getvalue())

    def test_failed_unmount_never_removes_target_tree_or_loses_mount_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keep = root / 'valuable-target-file'; keep.write_text('preserve')
            context = TargetMounts({})
            context.root = root; context.temporary = directory
            context.mounts = [(root, False)]
            with patch('installer.bootstrap.command', side_effect=RuntimeError('busy mount')), patch('installer.bootstrap.os.rmdir') as remove:
                with self.assertRaisesRegex(RuntimeError, 'cleanup incomplete'):
                    context.__exit__(None, None, None)
                remove.assert_not_called()
            self.assertEqual(context.mounts, [(root, False)])
            del context
            import gc
            gc.collect()
            self.assertEqual(keep.read_text(), 'preserve')

    def test_subvolumes_are_created_at_top_level_and_unmounted(self):
        target = Target('/dev/mock', 'SERIAL', 'MODEL', 64 * 1024**3, '8:0')
        storage = {'target': target.__dict__, 'partitions': {'root': '/dev/mock3'},
                   'filesystems': {'root': {'UUID': 'UUID'}}}
        with tempfile.TemporaryDirectory() as directory:
            with patch('installer.bootstrap.os.geteuid', return_value=0), patch('installer.bootstrap.inspect', return_value=target), patch('installer.bootstrap.filesystem', return_value={'TYPE': 'btrfs', 'UUID': 'UUID'}), patch('installer.bootstrap.tempfile.mkdtemp', return_value=directory), patch('installer.bootstrap.os.rmdir') as remove, patch('installer.bootstrap.command') as command:
                result = create_subvolumes(storage)
                calls = [call.args[0] for call in command.call_args_list]
                self.assertEqual(calls[0], ['mount', '-t', 'btrfs', '-o', 'subvolid=5,nodev,nosuid', '/dev/mock3', directory])
                self.assertEqual(calls[-1], ['umount', directory])
                self.assertEqual([c[-1] for c in calls if c[:3] == ['btrfs', 'subvolume', 'create']],
                                 [directory + '/' + name for name in ('@', '@home', '@snapshots', '@home_snapshots')])
                self.assertEqual(result['filesystem_uuid'], 'UUID')
                remove.assert_called_once_with(directory)

    def test_subvolume_setup_rejects_changed_filesystem_before_mount(self):
        target = Target('/dev/mock', 'SERIAL', 'MODEL', 64 * 1024**3, '8:0')
        storage = {'target': target.__dict__, 'partitions': {'root': '/dev/mock3'},
                   'filesystems': {'root': {'UUID': 'EXPECTED'}}}
        with patch('installer.bootstrap.os.geteuid', return_value=0), patch('installer.bootstrap.inspect', return_value=target), patch('installer.bootstrap.filesystem', return_value={'TYPE': 'btrfs', 'UUID': 'OTHER'}), patch('installer.bootstrap.command') as command:
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                create_subvolumes(storage)
            command.assert_not_called()
