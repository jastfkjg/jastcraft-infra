"""Verify PostgreSQL archive validation and upload/prune failure boundaries."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PostgresBackupTest(unittest.TestCase):
    def run_backup(self, mode='', upload=False, container='a' * 12):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        (base / 'opt/realquest').mkdir(parents=True)
        (base / 'bin').mkdir()
        (base / 'lib').mkdir()
        shutil.copyfile(ROOT / 'host/backup-postgres.sh', base / 'lib/backup-postgres.sh')
        wrapper = (ROOT / 'host/backup.sh').read_text().replace('/opt/', str(base / 'opt') + '/')
        (base / 'backup.sh').write_text(wrapper.replace('/usr/local/lib/jastcraft/', str(base / 'lib') + '/'))
        stub = base / 'bin/stub'
        stub.write_text('#!' + sys.executable + '\n' + r'''
import json, os, sys
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps([name] + args) + '\n')
mode = os.environ['FAIL_MODE']
if name == 'docker':
    if args[:2] == ['ps', '-q']: print(os.environ['CONTAINER'])
    if 'pg_dump' in args:
        print('PGDMP synthetic archive')
        if mode == 'dump': sys.exit(42)
    if 'pg_restore' in args and mode == 'archive': sys.exit(42)
if name == 'coscli' and mode == 'upload': sys.exit(42)
''')
        stub.chmod(0o755)
        for name in ['docker', 'coscli', 'flock', 'find']:
            (base / 'bin' / name).symlink_to(stub)
        env = dict(os.environ, PATH=str(base / 'bin') + os.pathsep + os.environ['PATH'],
                   CALLS=str(base / 'calls'), FAIL_MODE=mode, CONTAINER=container,
                   BACKUP_SERVICE='realquest', BACKUP_CLOUD='tencent',
                   BACKUP_DESTINATION='cos://backups-1250000000/realquest/prod',
                   BACKUP_COS_ENDPOINT='cos.ap-shanghai.myqcloud.com')
        command = ['bash', str(base / 'backup.sh')] if upload else ['bash', str(base / 'lib/backup-postgres.sh'), str(base / 'opt/realquest')]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        calls = [json.loads(line) for line in (base / 'calls').read_text().splitlines()]
        return result, calls, base

    def test_archive_is_private_and_validated_before_returning(self):
        result, calls, _ = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = Path(result.stdout.strip())
        self.assertTrue(snapshot.name.endswith('.dump'))
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
        self.assertTrue(any('pg_restore' in call and '--list' in call for call in calls))

    def test_failed_dump_or_archive_check_removes_partial_snapshot(self):
        for mode in ['dump', 'archive']:
            with self.subTest(mode=mode):
                result, _, base = self.run_backup(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertEqual(list((base / 'opt/realquest/backups').iterdir()), [])

    def test_multiple_or_missing_database_containers_are_rejected(self):
        for container in ['', 'a' * 12 + '\n' + 'b' * 12]:
            result, calls, base = self.run_backup(container=container)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(any('pg_dump' in call for call in calls))
            self.assertFalse((base / 'opt/realquest/backups').exists())

    def test_upload_uses_dump_extension_and_only_then_prunes(self):
        result, calls, _ = self.run_backup(upload=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        upload = next(call for call in calls if call[0] == 'coscli')
        self.assertTrue(upload[2].endswith('.dump'))
        self.assertTrue(upload[3].startswith('cos://backups-1250000000/realquest/prod/'))
        self.assertEqual(calls[-1][0], 'find')
        self.assertIn('realquest-*.dump', calls[-1])

    def test_upload_failure_keeps_local_dump_and_does_not_prune(self):
        result, calls, base = self.run_backup(mode='upload', upload=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[0] == 'find' for call in calls))
        self.assertEqual(len(list((base / 'opt/realquest/backups').glob('*.dump'))), 1)


if __name__ == '__main__':
    unittest.main()
