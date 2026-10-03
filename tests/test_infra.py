import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from render_host import load_host, render
from check_gateway_config import validate
from validate_image import image_reference
spec = importlib.util.spec_from_file_location('backup_sqlite', ROOT/'host/backup-sqlite.py')
backup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_module)
IMAGE = 'registry.cn-hangzhou.aliyuncs.com/example/caddy@sha256:' + 'a'*64
OLD_IMAGE = 'registry.cn-hangzhou.aliyuncs.com/example/caddy@sha256:' + 'b'*64

class HostTest(unittest.TestCase):
    def test_selected_host_contains_only_its_services(self):
        with tempfile.TemporaryDirectory() as directory:
            compose = render('aliyun-beijing-01', directory)
            self.assertEqual(set(compose['networks']), {'shadowtable', 'just-works', 'inkmind'})
            self.assertEqual(compose['networks']['just-works']['name'], 'just-works_proxy')
            self.assertEqual(set(compose['services']['caddy']['environment']), {'ACME_EMAIL','SHADOWTABLE_DOMAIN','JUST_WORKS_DOMAIN','INKMIND_DOMAIN'})
            text=(Path(directory)/'Caddyfile').read_text()
            self.assertIn('shadowtable-upstream:8787', text)
            self.assertIn('just-works-upstream:8080', text)
            self.assertIn('{$JUST_WORKS_DOMAIN}', text)
            self.assertIn('inkmind-upstream:80', text)
            self.assertIn('{$INKMIND_DOMAIN}', text)
            self.assertIn('flush_interval -1', text)
            self.assertNotIn('echooo',text)
            self.assertNotIn('wenlv',text)
    def test_shared_host_preserves_routes_and_setup_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            compose=render('aws-singapore-01',directory)
            self.assertEqual(set(compose['networks']), {'echooo','shadowtable','wenlv'})
            text=(Path(directory)/'Caddyfile').read_text()
            self.assertIn('/api/auth/setup',text)
            self.assertIn('flush_interval -1',text)
            self.assertNotIn('just-works', text)
    def test_unknown_or_path_target_rejected(self):
        for value in ['missing','../../gateway','aliyun-beijing-01\n']:
            with self.assertRaises(ValueError): load_host(value)
    def test_host_location_is_independent_of_business_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            host=root/'hosts/aliyun/beijing/01/host.json'
            host.parent.mkdir(parents=True)
            config={'target':'aliyun-beijing-01','cloud':'aliyun','location':'beijing',
                    'region':'cn-beijing','environment':'staging','services':['shadowtable']}
            host.write_text(json.dumps(config))
            self.assertEqual(load_host(config['target'], root)[1]['environment'], 'staging')
            for field,value in [('location','singapore'),('cloud','aws'),('environment','beijing')]:
                with self.subTest(field=field):
                    host.write_text(json.dumps(dict(config, **{field:value})))
                    with self.assertRaises(ValueError): load_host(config['target'], root)
    def test_missing_registry_digest_rejected(self):
        for value in ['caddy:latest', IMAGE+'\n', 'https://'+IMAGE]:
            with self.assertRaises(ValueError): image_reference(value)
    def test_consistent_online_backup_includes_uncheckpointed_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.sqlite'
            db=sqlite3.connect(source)
            self.addCleanup(db.close)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE example(value TEXT)')
            db.execute('INSERT INTO example VALUES(?)',('committed WAL data',))
            db.commit()
            dest=backup_module.backup(source,Path(directory)/'backups/snapshot.sqlite')
            with sqlite3.connect(dest) as restored:
                self.assertEqual(restored.execute('SELECT value FROM example').fetchone()[0], 'committed WAL data')
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
    def test_missing_database_does_not_create_empty_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): backup_module.backup(Path(directory)/'missing.sqlite',Path(directory)/'backup.sqlite')
            self.assertFalse((Path(directory)/'backup.sqlite').exists())

class InkMindBackupTest(unittest.TestCase):
    def test_named_backup_keeps_legacy_default_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'inkmind.db'
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE novels(title TEXT)')
                db.execute('INSERT INTO novels VALUES(?)', ('真实作品',))
            for prefix in ['inkmind', 'shadowtable']:
                args = [sys.executable, str(ROOT/'host/backup-sqlite.py'), str(source), directory]
                if prefix == 'inkmind': args += ['--prefix', prefix]
                result = subprocess.run(args, capture_output=True, text=True, check=True)
                snapshot = Path(result.stdout.strip())
                self.assertTrue(snapshot.name.startswith(prefix + '-'))
                self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
                with sqlite3.connect(snapshot) as db:
                    self.assertEqual(db.execute('SELECT title FROM novels').fetchone()[0], '真实作品')

class GatewayDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve()
        self.gateway=self.base/'gateway'
        (self.gateway/'config').mkdir(parents=True)
        (self.gateway/'releases').mkdir()
        self.target='aliyun-beijing-01'
        (self.gateway/'deployment-target').write_text(self.target+'\n')
        envfile=self.gateway/'gateway.env'
        envfile.write_text(f'CADDY_IMAGE={OLD_IMAGE}\nACME_EMAIL=admin@example.com\nSHADOWTABLE_DOMAIN=table.example.com\nJUST_WORKS_DOMAIN=works.example.com\nINKMIND_DOMAIN=inkmind.jastcraft.com\nCADDY_DATA_VOLUME=test-data\nCADDY_CONFIG_VOLUME=test-config\n')
        envfile.chmod(0o600)
        render(self.target,self.gateway/'config',str(self.gateway))
        (self.gateway/'config/image.env').write_text('CADDY_IMAGE='+OLD_IMAGE+'\n')
        self.old_caddy=(self.gateway/'config/Caddyfile').read_text()
        self.bin=self.base/'bin'; self.bin.mkdir()
        stub=r"""#!/usr/bin/env python3
import json, os, pathlib, re, sys
args=sys.argv[1:]
with open(os.environ['CALLS'],'a') as stream: stream.write(json.dumps(args)+'\n')
mode=os.environ.get('FAIL_MODE','')
if args[:2]==['ps','-q']:
    if os.environ.get('OLD_RUNNING')=='1': print('old-gateway')
    sys.exit(0)
if 'inspect' in args: sys.exit(0)
if 'compose' not in args: sys.exit(0)
values={}
for index, arg in enumerate(args):
    if arg=='--env-file':
        for line in pathlib.Path(args[index+1]).read_text().splitlines():
            if '=' in line:
                key,value=line.split('=',1); values[key]=value
if 'config' in args and 'json' in args:
    spec=json.loads(pathlib.Path(args[args.index('-f')+1]).read_text())
    def expand(value):
        if isinstance(value,str): return re.sub(r'\$\{([A-Z_]+)(?::[^}]*)?\}',lambda m: values[m[1]],value)
        if isinstance(value,list): return [expand(v) for v in value]
        if isinstance(value,dict): return {k:expand(v) for k,v in value.items()}
        return value
    print(json.dumps(expand(spec)))
if 'pull' in args and mode=='pull': sys.exit(1)
if 'run' in args and mode=='validate': sys.exit(1)
if 'up' in args and mode=='startup' and values.get('CADDY_IMAGE','').endswith('a'*64): sys.exit(1)
"""
        (self.bin/'docker').write_text(stub); (self.bin/'docker').chmod(0o755)
        (self.bin/'flock').write_text('#!/bin/sh\nexit 0\n'); (self.bin/'flock').chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],GATEWAY_ROOT=str(self.gateway),CALLS=str(self.base/'calls'),OLD_RUNNING='1')
    def deploy(self,mode=''):
        result=subprocess.run(['bash',str(ROOT/'gateway/deploy.sh'),self.target,IMAGE],env=dict(self.env,FAIL_MODE=mode),capture_output=True,text=True)
        log=self.base/'calls'
        calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result,calls
    def test_success_promotes_only_gateway(self):
        result,calls=self.deploy()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.gateway/'current').is_symlink())
        self.assertIn(IMAGE,(self.gateway/'config/image.env').read_text())
        self.assertTrue(any('up' in c and c[-1]=='caddy' for c in calls))
        self.assertFalse(any('app' in c or 'db' in c for c in calls))
    def test_failed_pull_and_validation_leave_active_configuration_untouched(self):
        for mode in ['pull','validate']:
            with self.subTest(mode=mode):
                result,calls=self.deploy(mode)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual((self.gateway/'config/Caddyfile').read_text(),self.old_caddy)
                self.assertIn(OLD_IMAGE,(self.gateway/'config/image.env').read_text())
                self.assertFalse(any('up' in c for c in calls))
                (self.base/'calls').unlink()
    def test_failed_start_restores_configuration_and_old_gateway(self):
        result,calls=self.deploy('startup')
        self.assertNotEqual(result.returncode,0)
        self.assertIn(OLD_IMAGE,(self.gateway/'config/image.env').read_text())
        self.assertEqual((self.gateway/'config/Caddyfile').read_text(),self.old_caddy)
        self.assertFalse((self.gateway/'current').exists())
        self.assertEqual(sum('up' in c for c in calls),2)
        self.assertFalse(any('volume' in c and 'rm' in c for c in calls))
    def test_first_failed_start_does_not_restart_candidate(self):
        self.env['OLD_RUNNING']='0'
        for file in (self.gateway/'config').iterdir(): file.unlink()
        result,calls=self.deploy('startup')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.gateway/'config/compose.yaml').exists())
        self.assertEqual(sum('up' in c for c in calls),1)
    def test_wrong_host_target_rejected_before_docker(self):
        (self.gateway/'deployment-target').write_text('aws-singapore-01\n')
        result,calls=self.deploy()
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,[])

if __name__=='__main__': unittest.main()
