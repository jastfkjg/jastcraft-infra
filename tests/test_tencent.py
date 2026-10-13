"""Exercise existing-host Tencent support without SSH, Docker or cloud access."""
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from render_host import load_host, render
import test_infra

TARGET = 'tencent-shanghai-01'
IMAGE = 'registry.example.com/infra/caddy@sha256:' + 'a' * 64


def populated_checkout(directory, services):
    root = Path(directory)
    for folder, names in {
        'scripts': ['render_host.py', 'check_gateway_config.py', 'validate_image.py'],
        'gateway': ['deploy.sh', 'compose.sh'],
        'gateway/routes': [service + '.caddy' for service in services],
    }.items():
        (root / folder).mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copyfile(ROOT / folder / name, root / folder / name)
    manifest = root / 'hosts/tencent/shanghai/01/host.json'
    manifest.parent.mkdir(parents=True)
    config = dict(load_host(TARGET)[1], services=services)
    manifest.write_text(json.dumps(config))
    return root, manifest, config


class TencentInventoryTest(unittest.TestCase):
    def test_empty_host_is_registered_with_the_correct_region(self):
        folder, host = load_host(TARGET)
        self.assertEqual(folder, ROOT / 'hosts/tencent/shanghai/01')
        self.assertEqual(host['region'], 'ap-shanghai')
        self.assertEqual(host['environment'], 'prod')
        self.assertEqual(host['services'], [])

    def test_empty_host_cannot_render_or_create_output_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'candidate'
            with self.assertRaisesRegex(ValueError, 'Host has no services'):
                render(TARGET, output)
            self.assertFalse(output.exists())

    def test_check_cli_accepts_inventory_and_rejects_empty_deployment(self):
        command = [sys.executable, str(ROOT / 'scripts/render_host.py'), TARGET, '--check']
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        result = subprocess.run(command + ['--require-services'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Host has no services', result.stderr)

    def test_future_service_selection_renders_only_selected_routes_and_networks(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = populated_checkout(directory, ['shadowtable', 'directo'])
            output = root / 'rendered'
            compose = render(TARGET, output, root=root)
            self.assertEqual(set(compose['networks']), {'shadowtable', 'directo'})
            self.assertEqual(set(compose['services']['caddy']['environment']),
                             {'ACME_EMAIL', 'SHADOWTABLE_DOMAIN', 'DIRECTO_DOMAIN'})
            self.assertEqual(compose['services']['caddy']['ports'], ['80:80', '443:443'])
            routes = (output / 'Caddyfile').read_text()
            self.assertIn('shadowtable-upstream:8787', routes)
            self.assertIn('directo-api-upstream:3001', routes)
            self.assertNotIn('wenlv', routes)

    def test_invalid_service_lists_and_mismatched_cloud_still_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root, manifest, config = populated_checkout(directory, ['directo'])
            for services in [None, {}, '', ['unknown'], ['directo', 'directo'], [[]]]:
                with self.subTest(services=services):
                    manifest.write_text(json.dumps(dict(config, services=services)))
                    with self.assertRaises(ValueError):
                        load_host(TARGET, root)
            manifest.write_text(json.dumps(dict(config, cloud='aliyun')))
            with self.assertRaisesRegex(ValueError, 'directory'):
                load_host(TARGET, root)

    def test_workflow_targets_match_all_registered_hosts(self):
        workflow = (ROOT / '.github/workflows/deploy-gateway.yml').read_text()
        choices = re.search(r'options: \[([^]]+)\]', workflow).group(1)
        targets = [json.loads(path.read_text())['target']
                   for path in (ROOT / 'hosts').glob('*/*/*/host.json')]
        self.assertEqual({choice.strip() for choice in choices.split(',')}, set(targets))


class TencentPublishTest(unittest.TestCase):
    def test_empty_host_fails_before_any_remote_connection(self):
        result = subprocess.run(['bash', str(ROOT / 'scripts/publish_gateway.sh')],
                                cwd=ROOT, capture_output=True, text=True,
                                env=dict(os.environ, HOST_TARGET=TARGET, GATEWAY_TARGET=TARGET,
                                         SSH_HOST='', SSH_KEY='', SSH_KNOWN_HOSTS=''))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Host has no services', result.stderr)

    def gateway_fixture(self):
        case = test_infra.GatewayDeploymentTest()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.target = TARGET
        (case.gateway / 'deployment-target').write_text(TARGET + '\n')
        return case

    def test_empty_host_preserves_existing_gateway_without_docker_calls(self):
        case = self.gateway_fixture()
        before = {path.name: path.read_bytes() for path in (case.gateway / 'config').iterdir()}
        result, calls = case.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Host has no services', result.stderr)
        self.assertEqual(calls, [])
        self.assertEqual(before, {path.name: path.read_bytes() for path in (case.gateway / 'config').iterdir()})
        self.assertEqual(list((case.gateway / 'releases').iterdir()), [])

    def test_populated_tencent_gateway_supports_success_and_startup_rollback(self):
        for mode in ['', 'startup']:
            with self.subTest(mode=mode):
                case = self.gateway_fixture()
                root, _, _ = populated_checkout(case.base / 'checkout', ['directo'])
                result = subprocess.run(['bash', str(root / 'gateway/deploy.sh'), TARGET, IMAGE],
                                        env=dict(case.env, FAIL_MODE=mode), capture_output=True, text=True)
                calls = [json.loads(line) for line in (case.base / 'calls').read_text().splitlines()]
                if mode:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual((case.gateway / 'config/Caddyfile').read_text(), case.old_caddy)
                    self.assertIn(test_infra.OLD_IMAGE, (case.gateway / 'config/image.env').read_text())
                    self.assertFalse((case.gateway / 'current').exists())
                    self.assertEqual(sum('up' in call for call in calls), 2)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue((case.gateway / 'current').is_symlink())
                    self.assertEqual((case.gateway / 'config/host').read_text(), TARGET + '\n')
                    self.assertIn(IMAGE, (case.gateway / 'config/image.env').read_text())
                self.assertFalse(any('volume' in call and 'rm' in call for call in calls))


class TencentBootstrapTest(unittest.TestCase):
    def test_validation_accepts_tencent_and_retains_existing_clouds(self):
        wrapper = 'source "$1"; validate_bootstrap_arguments deploy "$2" "$3" "$4"'
        for target in [TARGET, 'aws-singapore-01', 'aliyun-beijing-01']:
            for services in ['', 'directo,shadowtable']:
                with self.subTest(target=target, services=services):
                    result = subprocess.run(['bash', '-c', wrapper, 'test',
                                             str(ROOT / 'host/bootstrap.sh'), services, target, 'prod'],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
        for services, target, environment in [('unknown', TARGET, 'prod'),
                                               ('', 'tencent-shanghai-1', 'prod'),
                                               ('', TARGET, 'beijing')]:
            result = subprocess.run(['bash', '-c', wrapper, 'test',
                                     str(ROOT / 'host/bootstrap.sh'), services, target, environment],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_empty_bootstrap_then_service_setup_uses_tencent_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            bin_dir = base / 'bin'
            bin_dir.mkdir()
            script = base / 'bootstrap.sh'
            # Only the test copy skips root/package setup; all directory/marker logic runs.
            source = (ROOT / 'host/bootstrap.sh').read_text()
            source = source.replace('[[ "$EUID" == 0 ]] ||', 'true ||')
            source = source.replace('install_runtime\nsystemctl', ':\nsystemctl')
            script.write_text(source.replace('/opt/', str(base / 'opt') + '/'))
            stub = bin_dir / 'stub'
            stub.write_text('#!' + sys.executable + '\n' + '''
from pathlib import Path
import sys
if Path(sys.argv[0]).name == 'install':
    for argument in sys.argv[1:]:
        if argument.startswith('/'):
            Path(argument).mkdir(parents=True, exist_ok=True)
''')
            stub.chmod(0o755)
            for name in ['install', 'systemctl', 'id', 'useradd', 'usermod', 'chown']:
                (bin_dir / name).symlink_to(stub)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
            for services in ['', 'just-works']:
                result = subprocess.run(['bash', str(script), 'deploy', services, TARGET, 'prod'],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((base / 'opt/gateway/deployment-target').read_text(), TARGET + '\n')
                if not services:
                    self.assertEqual([path.name for path in (base / 'opt').iterdir()], ['gateway'])
            self.assertEqual((base / 'opt/just-works/deployment-target').read_text(), 'tencent-prod\n')
            self.assertFalse((base / 'opt/just-works/data').exists())


class TencentBackupTest(unittest.TestCase):
    def run_backup(self, cloud='tencent', fail=False, endpoint='cos.ap-shanghai.myqcloud.com',
                   destination=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        data = base / 'opt/shadowtable/data'
        data.mkdir(parents=True)
        with sqlite3.connect(data / 'shadowtable.sqlite') as database:
            database.execute('CREATE TABLE example(value TEXT)')
            database.execute('INSERT INTO example VALUES(?)', ('backup data',))
        library = base / 'lib'
        library.mkdir()
        shutil.copyfile(ROOT / 'host/backup-sqlite.py', library / 'backup-sqlite.py')
        script = base / 'backup.sh'
        source = (ROOT / 'host/backup.sh').read_text()
        script.write_text(source.replace('/opt/', str(base / 'opt') + '/')
                          .replace('/usr/local/lib/jastcraft/', str(library) + '/'))
        bin_dir = base / 'bin'
        bin_dir.mkdir()
        stub = bin_dir / 'stub'
        stub.write_text('#!' + sys.executable + '\n' + '''
import json, os
from pathlib import Path
import sys
name = Path(sys.argv[0]).name
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps([name] + sys.argv[1:]) + '\\n')
if name in ['coscli', 'aws', 'ossutil'] and os.environ['FAIL_UPLOAD'] == '1':
    sys.exit(42)
''')
        stub.chmod(0o755)
        for name in ['coscli', 'aws', 'ossutil', 'flock', 'find']:
            (bin_dir / name).symlink_to(stub)
        scheme = {'aws': 's3', 'aliyun': 'oss', 'tencent': 'cos'}[cloud]
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                   CALLS=str(base / 'calls'), FAIL_UPLOAD='1' if fail else '0',
                   BACKUP_CLOUD=cloud, BACKUP_SERVICE='shadowtable',
                   BACKUP_DESTINATION=destination or scheme + '://backups-1250000000/shadowtable/prod/',
                   BACKUP_COS_ENDPOINT=endpoint)
        result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True)
        calls = [json.loads(line) for line in (base / 'calls').read_text().splitlines()] if (base / 'calls').exists() else []
        return result, calls, base

    def test_cos_upload_uses_endpoint_and_a_consistent_private_snapshot(self):
        result, calls, _ = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        upload = next(call for call in calls if call[0] == 'coscli')
        snapshot = Path(upload[2])
        self.assertEqual(upload[1], 'cp')
        self.assertEqual(upload[3], 'cos://backups-1250000000/shadowtable/prod/' + snapshot.name)
        self.assertEqual(upload[4:], ['--endpoint', 'cos.ap-shanghai.myqcloud.com'])
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(snapshot) as database:
            self.assertEqual(database.execute('SELECT value FROM example').fetchone()[0], 'backup data')
        self.assertEqual(calls[-1][0], 'find')

    def test_failed_cos_upload_keeps_snapshot_and_does_not_prune_old_backups(self):
        result, calls, base = self.run_backup(fail=True)
        self.assertEqual(result.returncode, 42)
        self.assertFalse(any(call[0] == 'find' for call in calls))
        self.assertEqual(len(list((base / 'opt/shadowtable/backups').glob('*.sqlite'))), 1)

    def test_invalid_cos_configuration_fails_before_snapshot_creation(self):
        for configuration in [{'endpoint': ''}, {'endpoint': 'https://cos.ap-shanghai.myqcloud.com'},
                              {'destination': 'oss://example/shadowtable/prod'}]:
            with self.subTest(configuration=configuration):
                result, calls, base = self.run_backup(**configuration)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])
                self.assertFalse((base / 'opt/shadowtable/backups').exists())

    def test_existing_s3_and_oss_uploads_do_not_require_cos_options(self):
        for cloud, cli in [('aws', 'aws'), ('aliyun', 'ossutil')]:
            with self.subTest(cloud=cloud):
                result, calls, _ = self.run_backup(cloud=cloud, endpoint='')
                self.assertEqual(result.returncode, 0, result.stderr)
                upload = next(call for call in calls if call[0] == cli)
                self.assertNotIn('--endpoint', upload)
                self.assertEqual(calls[-1][0], 'find')


if __name__ == '__main__':
    unittest.main()
