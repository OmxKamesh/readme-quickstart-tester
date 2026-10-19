import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('first_run', ROOT / 'skills/first-run/scripts/first_run.py')
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'repo'
        shutil.copytree(ROOT / 'examples/python-broken', self.repo)
        self.git('init', '-q')
        self.commit()
        self.contract = {'version': 1, 'phase': 'baseline', 'steps': [{
            'id': 'hello', 'argv': [sys.executable, 'app.py'], 'cwd': '.',
            'source': {'path': 'README.md', 'line': 4, 'text': 'python app.py'},
            'assert_stdout': 'Hello, newcomer!'}]}

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE)

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Synthetic Test', '-c', 'user.email=test@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'synthetic fixture')

    def test_baseline_patch_fresh_replay(self):
        baseline = fr.replay(self.repo, self.contract, True)
        self.assertEqual('failed', baseline['status'])
        self.assertNotEqual(0, baseline['steps'][0]['exit_code'])
        self.git('apply', str(ROOT / 'examples/proposed.patch'))
        # Working changes must not silently repair the baseline.
        self.assertEqual('failed', fr.replay(self.repo, self.contract, True)['status'])
        self.commit()
        fixed = copy.deepcopy(self.contract)
        fixed['phase'] = 'repair'
        fixed['steps'][0]['argv'][1] = 'hello.py'
        fixed['steps'][0]['source']['text'] = 'python hello.py'
        repair = fr.replay(self.repo, fixed, True)
        self.assertEqual('verified', repair['status'])
        self.assertNotEqual(baseline['commit'], repair['commit'])
        self.assertEqual('failed', baseline['status'])

    def test_static_mode_never_executes(self):
        self.assertEqual('blocked', fr.replay(self.repo, self.contract)['status'])
        self.assertIsNone(fr.replay(self.repo, self.contract)['steps'][0]['exit_code'])

    def test_first_failure_stops_order(self):
        later = copy.deepcopy(self.contract['steps'][0])
        later['id'] = 'never-reached'
        self.contract['steps'].append(later)
        self.assertEqual(1, len(fr.replay(self.repo, self.contract, True)['steps']))

    def test_assertion_failure_even_on_exit_zero(self):
        self.contract['steps'][0]['argv'][1] = 'hello.py'
        self.contract['steps'][0]['assert_stdout'] = 'not the greeting'
        r = fr.replay(self.repo, self.contract, True)
        self.assertEqual(0, r['steps'][0]['exit_code'])
        self.assertEqual('failed', r['status'])

    def test_external_requirement_blocked(self):
        self.contract['steps'][0]['requirements'] = ['external account required']
        self.assertEqual('blocked', fr.replay(self.repo, self.contract, True)['status'])

    def test_wrong_directory_and_missing_runtime(self):
        self.contract['steps'][0]['cwd'] = 'absent'
        self.assertIn('directory', fr.replay(self.repo, self.contract, True)['steps'][0]['reason'])
        self.contract['steps'][0]['cwd'] = '.'
        self.contract['steps'][0]['argv'][0] = 'first-run-no-such-executable'
        self.assertIn('prerequisite', fr.replay(self.repo, self.contract, True)['steps'][0]['reason'])

    def test_stale_citation_blocked(self):
        self.contract['steps'][0]['source']['line'] = 3
        self.assertEqual('blocked', fr.replay(self.repo, self.contract, True)['status'])

    def test_traversal_rejected(self):
        for path in ('../escape', '/absolute', 'C:/outside', '..\\escape'):
            with self.assertRaises(ValueError):
                fr.relative(path)

    def test_malformed_contract_rejected(self):
        for bad in ([], {}, {'version': 1, 'steps': [1]}):
            with self.assertRaises(ValueError):
                fr.validate(bad)

    def test_cli_report_and_no_overwrite(self):
        contract = Path(self.tmp.name) / 'contract.json'
        contract.write_text(json.dumps(self.contract), encoding='utf-8')
        output = Path(self.tmp.name) / 'evidence'
        command = [sys.executable, str(ROOT / 'skills/first-run/scripts/first_run.py'),
                   str(self.repo), str(contract), '--out', str(output)]
        p = subprocess.run(command, capture_output=True)
        self.assertEqual(2, p.returncode)
        evidence = (output / 'evidence.json').read_bytes()
        self.assertEqual('blocked', json.loads(evidence)['status'])
        self.assertTrue((output / 'report.md').is_file())
        p = subprocess.run(command, capture_output=True)
        self.assertEqual(2, p.returncode)
        self.assertIn(b'output must be new', p.stderr)
        self.assertEqual(evidence, (output / 'evidence.json').read_bytes())

    def test_timeout_is_failure(self):
        self.contract['steps'][0]['argv'] = [sys.executable, '-c', 'import time; time.sleep(3)']
        self.contract['steps'][0]['timeout'] = 1
        result = fr.replay(self.repo, self.contract, True)
        self.assertEqual('failed', result['status'])
        self.assertIn('timeout', result['steps'][0]['reason'])

    @unittest.skipUnless(os.name == 'nt', 'Windows relative executable regression')
    def test_relative_executable_uses_export_directory(self):
        (self.repo / 'greet.cmd').write_text('@echo Hello, newcomer!\n')
        (self.repo / 'README.md').write_text('# Greeting\n\nRun:\n.\\greet.cmd\n')
        self.commit()
        self.contract['steps'][0]['argv'] = ['./greet.cmd']
        self.contract['steps'][0]['source']['text'] = '.\\greet.cmd'
        self.assertEqual('verified', fr.replay(self.repo, self.contract, True)['status'])

    def test_output_not_in_evidence(self):
        self.contract['steps'][0]['argv'][1] = 'hello.py'
        r = fr.replay(self.repo, self.contract, True)
        self.assertNotIn('Hello, newcomer!', json.dumps(r))
        self.assertEqual(64, len(r['steps'][0]['stdout_sha256']))

    def test_report_renders_untrusted_values_as_text(self):
        hostile = '![external](https://example.invalid/tracker) <img src=x> `code`\n# heading'
        result = fr.replay(self.repo, self.contract)
        result['steps'][0].update(id=hostile, reason=hostile)
        result['steps'][0]['source']['path'] = hostile
        rendered = fr.render(result)
        self.assertNotIn('![', rendered)
        self.assertNotIn('<img', rendered)
        self.assertNotIn('`code`', rendered)
        self.assertNotIn('\n# heading', rendered)
        self.assertIn('example.invalid/tracker', rendered)

    @unittest.skipUnless(shutil.which('node'), 'Node runtime unavailable')
    def test_node_passing(self):
        shutil.copyfile(ROOT / 'examples/node-passing/hello.js', self.repo / 'hello.js')
        shutil.copyfile(ROOT / 'examples/node-passing/README.md', self.repo / 'README.md')
        self.commit()
        s = self.contract['steps'][0]
        s['argv'] = ['node', 'hello.js']
        s['source']['text'] = 'node hello.js'
        self.assertEqual('verified', fr.replay(self.repo, self.contract, True)['status'])


if __name__ == '__main__':
    unittest.main()
