"""Exercise the actual process interface, including the no-write validation path."""
import json
import copy
import hashlib
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import resource
except ImportError:  # Windows has no process file-size resource limit.
    resource = None

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/evidence_workspace.py'
EXAMPLE = ROOT / 'references/synthetic-example.json'


class CliTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None, preexec_fn=None):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              cwd=cwd, capture_output=True, text=True, preexec_fn=preexec_fn)

    def artifact_hashes(self, output):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in output.iterdir() if path.is_file()}

    def test_extreme_values_report_json_without_output_or_prior_data_changes(self):
        cases = [('freshness_hours', 10**400), ('freshness_hours', -(10**400)),
                 ('captured_at', '0001-01-01T00:00:00+01:00'),
                 ('captured_at', '9999-12-31T23:59:59-01:00'),
                 ('observed_at', '9999-12-31T23:59:59-01:00')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good_output = root / 'last-good'
            result = self.run_cli('build', '--input', EXAMPLE, '--output', good_output)
            self.assertEqual(result.returncode, 0, result.stderr)
            original = self.artifact_hashes(good_output)
            for index, (field, value) in enumerate(cases):
                raw = json.loads(EXAMPLE.read_text())
                if field == 'observed_at':
                    raw['records'][0][field] = value
                else:
                    raw[field] = value
                source = root / f'invalid-{index}.json'
                source.write_text(json.dumps(raw), encoding='utf-8')
                for command in ('validate', 'build'):
                    with self.subTest(field=field, value=value, command=command):
                        output = root / f'not-created-{index}'
                        extra = ['--output', output] if command == 'build' else []
                        result = self.run_cli(command, '--input', source, '--json-errors', *extra)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertEqual(result.stdout, '')
                        error = json.loads(result.stderr)
                        self.assertEqual(set(error), {'status', 'error', 'network_calls'})
                        self.assertEqual(error['status'], 'error')
                        self.assertIn(field, error['error'])
                        self.assertIn(str(source), error['error'])
                        self.assertNotIn('Traceback', result.stderr)
                        self.assertFalse(output.exists())
                        self.assertEqual(self.artifact_hashes(good_output), original)

    def test_current_and_previous_input_errors_name_the_affected_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'malformed.json'
            source.write_text('{', encoding='utf-8')
            for command, args, label in [
                ('validate', ['--input', source], 'Current input'),
                ('compare', ['--input', EXAMPLE, '--previous', source,
                             '--output', Path(directory) / 'not-created'], 'Previous input'),
            ]:
                with self.subTest(command=command):
                    result = self.run_cli(command, '--json-errors', *args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, '')
                    message = json.loads(result.stderr)['error']
                    self.assertIn(f'{label} {source}', message)
                    self.assertIn('not valid bounded UTF-8 JSON', message)
                    self.assertFalse((Path(directory) / 'not-created').exists())

    @unittest.skipUnless(resource is not None and hasattr(signal, 'SIGXFSZ'),
                         'A real file-size write failure requires POSIX resource limits')
    def test_partial_write_failure_names_artifact_and_keeps_prior_evidence(self):
        def restrict_file_size():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (700, 700))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good_output = root / 'last-good'
            initial = self.run_cli('build', '--input', EXAMPLE, '--output', good_output)
            self.assertEqual(initial.returncode, 0, initial.stderr)
            original = self.artifact_hashes(good_output)
            partial = root / 'failed-new-output'
            result = self.run_cli('build', '--input', EXAMPLE, '--output', partial,
                                  '--json-errors', preexec_fn=restrict_file_size)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, '')
            error = json.loads(result.stderr)
            self.assertEqual(error['status'], 'error')
            self.assertIn(str(partial / 'index.html'), error['error'])
            self.assertIn('may be partial', error['error'])
            self.assertIn('fix the cause', error['error'])
            self.assertIn('fresh --output directory', error['error'])
            self.assertTrue((partial / 'index.html').is_file())
            self.assertLess((partial / 'index.html').stat().st_size,
                            (good_output / 'index.html').stat().st_size)
            self.assertEqual(self.artifact_hashes(good_output), original)
            partial_before = self.artifact_hashes(partial)
            retry = self.run_cli('build', '--input', EXAMPLE, '--output', partial, '--json-errors')
            self.assertEqual(retry.returncode, 2, retry.stderr)
            self.assertIn('already exists', json.loads(retry.stderr)['error'])
            self.assertEqual(self.artifact_hashes(partial), partial_before)
            recovered = self.run_cli('build', '--input', EXAMPLE, '--output', root / 'fresh-output')
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(self.artifact_hashes(good_output), original)

    def test_validate_does_not_write_and_reports_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli('validate', '--input', EXAMPLE, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'valid')
            self.assertEqual(report['network_calls'], 0)
            self.assertIn('not verified', report['boundary'])

    def test_public_validation_excludes_private_records(self):
        raw = json.loads(EXAMPLE.read_text())
        raw['records'][0]['audience'] = 'private'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_text(json.dumps(raw))
            result = self.run_cli('validate', '--input', source, '--audience', 'public')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['records'], 0)

    def test_json_error_is_parseable_and_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bad.json'
            source.write_text('{')
            result = self.run_cli('validate', '--input', source, '--json-errors')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertEqual(json.loads(result.stderr)['status'], 'error')
            self.assertNotIn('Traceback', result.stderr)

    def test_malformed_pr_enums_report_json_errors_without_output(self):
        fixture = json.loads(EXAMPLE.read_text())
        head = fixture['records'][0]['data']['head_sha']
        review = {'reviewer': 'fixture', 'state': 'APPROVED', 'commit_id': head,
                  'submitted_at': fixture['captured_at'],
                  'url': 'https://github.com/example/repo/pull/1#pullrequestreview-1'}
        check = {'id': 'fixture-check', 'name': 'Synthetic check', 'head_sha': head,
                 'status': 'completed', 'conclusion': 'success',
                 'url': 'https://github.com/example/repo/actions/runs/1'}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            output = Path(directory) / 'must-not-exist'
            for field in ['pr_state', 'review_state', 'check_status', 'check_conclusion']:
                for malformed in [[], {}]:
                    raw = copy.deepcopy(fixture)
                    data = raw['records'][0]['data']
                    if field == 'pr_state':
                        data['state'] = malformed
                    elif field == 'review_state':
                        data['reviews'] = [{**review, 'state': malformed}]
                    else:
                        key = 'status' if field == 'check_status' else 'conclusion'
                        data['checks'] = [{**check, key: malformed}]
                    source.write_text(json.dumps(raw))
                    for command in ['validate', 'build']:
                        with self.subTest(field=field, value=malformed, command=command):
                            extra = ['--output', output] if command == 'build' else []
                            result = self.run_cli(command, '--input', source, '--json-errors', *extra)
                            self.assertEqual(result.returncode, 2, result.stderr)
                            self.assertEqual(result.stdout, '')
                            self.assertEqual(json.loads(result.stderr)['status'], 'error')
                            self.assertNotIn('Traceback', result.stderr)
                            self.assertFalse(output.exists())

    def test_missing_input_reports_json(self):
        result = self.run_cli('validate', '--input', '/missing/evidence.json', '--json-errors')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)['status'], 'error')

    def test_missing_output_has_actionable_error(self):
        result = self.run_cli('build', '--input', EXAMPLE, '--json-errors')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--output NEW_DIRECTORY', json.loads(result.stderr)['error'])

    def test_unused_arguments_are_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'untouched'
            for command, extra in [('validate', ['--output', output]),
                                   ('validate', ['--previous', EXAMPLE]),
                                   ('build', ['--previous', EXAMPLE, '--output', output])]:
                result = self.run_cli(command, '--input', EXAMPLE, '--json-errors', *extra)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stderr)['status'], 'error')
                self.assertFalse(output.exists())

    def test_build_lists_existing_artifacts_and_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'snapshot'
            result = self.run_cli('build', '--input', EXAMPLE, '--output', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(set(report['artifacts']), {'index.html', 'brief.md', 'view.json'})
            original = {name: Path(path).read_bytes() for name, path in report['artifacts'].items()}
            retry = self.run_cli('build', '--input', EXAMPLE, '--output', output, '--json-errors')
            self.assertEqual(retry.returncode, 2)
            self.assertIn('already exists', json.loads(retry.stderr)['error'])
            self.assertEqual(original, {name: (output / name).read_bytes() for name in original})

    def test_compare_lists_delta_and_keeps_source_content(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'comparison'
            result = self.run_cli('compare', '--input', EXAMPLE, '--previous', EXAMPLE, '--output', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertIn('delta.json', report['artifacts'])
            self.assertEqual(json.loads((output / 'delta.json').read_text())['changes'], [])

    def issue_input(self):
        raw = json.loads(EXAMPLE.read_text())
        when = raw['captured_at']
        raw['records'] = [{'id': 'synthetic-goal', 'kind': 'github_issue', 'audience': 'private',
                           'title': 'Synthetic goal', 'source_url': 'https://github.com/example/repo/issues/42',
                           'observed_at': when, 'data': {'issue_number': 42, 'state': 'open', 'state_reason': None,
                                                       'updated_at': when, 'closed_at': None,
                                                       'next_action': 'Inspect the current source.'}}]
        return raw

    def test_goal_build_and_public_export_through_actual_process(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'goal.json'
            source.write_text(json.dumps(self.issue_input()))
            for audience, expected in [('private', 1), ('public', 0)]:
                output = Path(directory) / audience
                result = self.run_cli('build', '--input', source, '--output', output, '--audience', audience)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['records'], expected)
                view = json.loads((output / 'view.json').read_text())
                self.assertEqual(len(view['cards']), expected)
                if audience == 'public':
                    for name in ['index.html', 'brief.md', 'view.json']:
                        self.assertNotIn('/issues/42', (output / name).read_text())

    def test_goal_closure_compare_keeps_outcome_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = self.issue_input()
            previous = Path(directory) / 'before.json'
            previous.write_text(json.dumps(raw))
            raw['records'][0]['data'].update(state='closed', state_reason='completed', closed_at=raw['captured_at'])
            current = Path(directory) / 'after.json'
            current.write_text(json.dumps(raw))
            output = Path(directory) / 'comparison'
            result = self.run_cli('compare', '--input', current, '--previous', previous, '--output', output)
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads((output / 'view.json').read_text())['cards'][0]
            self.assertEqual(card['status'], 'Closed · reported complete')
            self.assertEqual(card['production'], 'Unverified')
            self.assertIn('Do not resume', card['next_action'])
            self.assertEqual(json.loads((output / 'delta.json').read_text())['changes'][0]['change'], 'material_change')


if __name__ == '__main__':
    unittest.main(verbosity=2)

