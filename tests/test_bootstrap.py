"""Exercise OS/package selection with command stubs; never change the test host."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeBootstrapTest(unittest.TestCase):
    def run_runtime(self, system='alinux', version='3', engine=False, compose='',
                    fail_package='', installed_compose='v2.30.3', source_only=False,
                    engine_version='Docker version 27.5.1, build mock'):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            bin_dir = base / 'bin'
            bin_dir.mkdir()
            for part in ['etc/apt/keyrings', 'etc/apt/sources.list.d']:
                (base / part).mkdir(parents=True)
            script = base / 'bootstrap.sh'
            script.write_text((ROOT / 'host/bootstrap.sh').read_text().replace('/etc/apt/', str(base / 'etc/apt') + '/'))
            os_release = base / 'os-release'
            os_release.write_text(f'ID={system}\nVERSION_ID={version}\nVERSION_CODENAME=noble\n')
            engine_state, compose_state = base / 'engine', base / 'compose'
            if engine:
                engine_state.touch()
            compose_state.write_text(compose)
            calls = base / 'calls'
            stub = bin_dir / 'stub'
            stub.write_text('#!' + sys.executable + '\n' + r'''
import json, os
from pathlib import Path
import sys
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as stream:
    stream.write(json.dumps([name] + args) + '\n')
if os.environ.get('FAIL_PACKAGE') and os.environ['FAIL_PACKAGE'] in args:
    sys.exit(42)
engine = Path(os.environ['ENGINE_STATE'])
compose = Path(os.environ['COMPOSE_STATE'])
if name in ['dnf', 'apt-get']:
    if 'docker-ce' in args:
        engine.touch()
    if 'docker-compose-plugin' in args:
        compose.write_text(os.environ['INSTALLED_COMPOSE'])
elif name == 'docker':
    if not engine.exists():
        sys.exit(127)
    if args == ['--version']:
        print(os.environ['ENGINE_VERSION'])
    elif args[:2] == ['compose', 'version']:
        version = compose.read_text()
        if not version:
            sys.exit(1)
        print(version)
elif name == 'curl' and '-o' in args:
    Path(args[args.index('-o') + 1]).write_text('mock signing key')
elif name == 'dpkg':
    print('amd64')
''')
            stub.chmod(0o755)
            for name in ['dnf', 'apt-get', 'docker', 'curl', 'dpkg', 'install']:
                (bin_dir / name).symlink_to(stub)
            (bin_dir / 'python3').symlink_to(sys.executable)
            env = dict(os.environ, PATH=str(bin_dir) + ':/usr/bin:/bin', CALLS=str(calls),
                       ENGINE_STATE=str(engine_state), COMPOSE_STATE=str(compose_state),
                       FAIL_PACKAGE=fail_package, INSTALLED_COMPOSE=installed_compose,
                       ENGINE_VERSION=engine_version)
            wrapper = r'''
command() {
    if [[ "$1" == -v && "$2" == docker && ! -f "$ENGINE_STATE" ]]; then return 1; fi
    builtin command "$@"
}
source "$1"
'''
            if not source_only:
                wrapper += '\ninstall_runtime "$2"\n'
            result = subprocess.run(['bash', '-c', wrapper, 'test', str(script), str(os_release)],
                                    env=env, capture_output=True, text=True)
            log = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            return result, log

    def test_alinux3_installs_real_engine_and_plugins_from_compatible_repo(self):
        result, calls = self.run_runtime()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[:2] == ['dnf', 'config-manager'] for c in calls))
        adapter = next(i for i, c in enumerate(calls) if 'dnf-plugin-releasever-adapter' in c)
        engine = next(i for i, c in enumerate(calls) if 'docker-ce' in c)
        self.assertLess(adapter, engine)
        self.assertIn('alinux3-plus', calls[adapter])
        self.assertIn('docker-compose-plugin', calls[engine])
        self.assertIn('containerd.io', calls[engine])
        self.assertFalse(any(c[0] == 'apt-get' or 'remove' in c or '--allowerasing' in c for c in calls))

    def test_alinux_2104_version_is_supported(self):
        result, _ = self.run_runtime(version='3.2104')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_usable_engine_and_compose_are_retained(self):
        result, calls = self.run_runtime(engine=True, compose='v2.30.3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any('docker-ce' in c or 'docker-compose-plugin' in c or 'config-manager' in c for c in calls))

    def test_existing_engine_with_missing_or_old_compose_only_installs_plugin(self):
        for compose in ['', 'v2.23.3']:
            with self.subTest(compose=compose):
                result, calls = self.run_runtime(engine=True, compose=compose)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(any('docker-compose-plugin' in c for c in calls))
                self.assertFalse(any('docker-ce' in c or 'containerd.io' in c for c in calls))

    def test_ubuntu_keeps_apt_installation_path(self):
        for version in ['22.04', '24.04']:
            with self.subTest(version=version):
                result, calls = self.run_runtime(system='ubuntu', version=version)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(any(c[0] == 'apt-get' and 'docker-ce' in c for c in calls))
                self.assertFalse(any(c[0] == 'dnf' for c in calls))

    def test_unsupported_system_fails_before_installation(self):
        for system, version in [('alinux', '2'), ('ubuntu', '20.04'), ('centos', '8')]:
            with self.subTest(system=system, version=version):
                result, calls = self.run_runtime(system=system, version=version)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])

    def test_adapter_install_failure_does_not_continue_to_engine_install(self):
        result, calls = self.run_runtime(fail_package='dnf-plugin-releasever-adapter')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('docker-ce' in c for c in calls))

    def test_still_outdated_compose_fails_with_actionable_error(self):
        result, _ = self.run_runtime(engine=True, compose='v2.23.3', installed_compose='v2.23.3')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Docker Compose 2.24+', result.stderr)

    def test_podman_shim_is_not_treated_as_docker_engine(self):
        result, calls = self.run_runtime(engine=True, engine_version='podman version 4.9.0')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] in ['dnf', 'apt-get'] for c in calls))

    def test_sourcing_script_does_not_prepare_the_host(self):
        result, calls = self.run_runtime(source_only=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
