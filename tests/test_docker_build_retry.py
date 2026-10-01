import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOKEN_ERROR = ('failed to fetch oauth token: unexpected status from POST request '
               'to https://auth.docker.io/token: {code} Bad Gateway')


class DockerBuildRetryTest(unittest.TestCase):
    def run_build(self, failures):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'docker').write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
base = pathlib.Path(os.environ['STUB_ROOT'])
calls = base / 'calls'
previous = calls.read_text().splitlines() if calls.exists() else []
with calls.open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
failures = json.loads(os.environ['BUILD_FAILURES'])
if len(previous) < len(failures):
    print(failures[len(previous)], file=sys.stderr)
    sys.exit(37)
print('build succeeded')
''')
            (base / 'sleep').write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$STUB_ROOT/delays"\n')
            for name in ['docker', 'sleep']:
                (base / name).chmod(0o755)
            args = ['build', '--progress=plain', '-t', 'gateway check', 'gateway']
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/retry_docker_build.sh'), *args],
                env=dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH'],
                         STUB_ROOT=str(base), BUILD_FAILURES=json.dumps(failures)),
                capture_output=True, text=True,
            )
            calls = [json.loads(line) for line in (base / 'calls').read_text().splitlines()]
            self.assertTrue(all(call == args for call in calls))
            delays = (base / 'delays').read_text().splitlines() if (base / 'delays').exists() else []
            return result, calls, delays

    def test_success_does_not_retry(self):
        result, calls, delays = self.run_build([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(delays, [])

    def test_transient_token_and_metadata_errors_recover(self):
        messages = [TOKEN_ERROR.format(code=code) for code in [500, 502, 503, 504]]
        messages.append('unexpected status from HEAD request to '
                        'https://registry-1.docker.io/v2/library/caddy/manifests/2.10.2-alpine: 503 Service Unavailable')
        for message in messages:
            with self.subTest(message=message):
                result, calls, delays = self.run_build([message])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(calls), 2)
                self.assertEqual(delays, ['10'])
                self.assertIn(message, result.stdout)

    def test_persistent_outage_stops_after_three_attempts(self):
        result, calls, delays = self.run_build([TOKEN_ERROR.format(code=502)] * 3)
        self.assertEqual(result.returncode, 37)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, ['10', '20'])

    def test_permanent_errors_are_not_retried(self):
        messages = [TOKEN_ERROR.format(code=code) for code in [401, 403, 404, 429]]
        messages += ['failed to resolve source metadata: manifest unknown',
                     'Dockerfile parse error: unknown instruction',
                     'unexpected status from POST request to https://registry.example.com/token: 502 Bad Gateway']
        for message in messages:
            with self.subTest(message=message):
                result, calls, delays = self.run_build([message])
                self.assertEqual(result.returncode, 37)
                self.assertEqual(len(calls), 1)
                self.assertEqual(delays, [])

    def test_permanent_error_after_transient_error_stops_immediately(self):
        result, calls, delays = self.run_build([
            TOKEN_ERROR.format(code=502), 'Dockerfile parse error: unknown instruction',
        ])
        self.assertEqual(result.returncode, 37)
        self.assertEqual(len(calls), 2)
        self.assertEqual(delays, ['10'])


if __name__ == '__main__':
    unittest.main()
