"""Synthetic coverage for source-linked coordination updates and explicit history."""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/evidence_workspace.py'
spec = importlib.util.spec_from_file_location('coordination_evidence_workspace', SCRIPT)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
NOW = '2026-10-11T12:00:00Z'


def update(rid='update-one', **fields):
    record = {
        'id': rid, 'kind': 'coordination_update', 'audience': 'private',
        'title': 'Synthetic coordination update',
        'source_url': 'https://github.com/example/studio/issues/17#issuecomment-42',
        'observed_at': NOW,
        'data': {
            'lane_id': 'synthetic-lane', 'project': 'Synthetic project',
            'owner': 'Synthetic owner', 'source_date': '2026-10-10',
            'state': 'next_action', 'summary': 'A bounded synthetic source assertion.',
            'next_action': 'Inspect the synthetic result.',
            'checkpoint_at': '2026-10-12T09:00:00+00:00', 'supersedes': [],
        },
    }
    record['data'].update(fields)
    return record


def snapshot(records):
    return {
        'format': w.FORMAT, 'title': 'Synthetic coordination snapshot',
        'scope': 'Synthetic fixtures only; no execution or adoption claims.',
        'captured_at': NOW, 'freshness_hours': 24, 'records': records,
    }


def cards(records, audience='private'):
    return {card['id']: card for card in w.build(snapshot(records), audience)['cards']}


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class CoordinationContractTests(unittest.TestCase):
    def assert_invalid(self, record):
        with self.assertRaises(w.EvidenceError):
            w.build(snapshot([record]))

    def test_normalized_card_preserves_coordination_metadata_and_source(self):
        record = update()
        card = cards([record])[record['id']]
        for key in ('lane_id', 'project', 'owner', 'source_date', 'state',
                    'checkpoint_at', 'supersedes'):
            self.assertEqual(card[key], record['data'][key], key)
        self.assertEqual(card['superseded_by'], [])
        self.assertEqual(card['reported_next_action'], record['data']['next_action'])
        self.assertEqual(card['next_action'], record['data']['next_action'])
        self.assertEqual(card['source_url'], record['source_url'])
        self.assertIn(record['data']['summary'], card['facts'])
        self.assertEqual(card['production'], 'Unverified')

    def test_states_have_distinct_work_categories_without_completion_proof(self):
        for state, category in [('needs_acceptance', 'Action'), ('next_action', 'Action'),
                                ('blocked', 'Action'), ('reported_complete', 'Completion'),
                                ('research', 'Research'), ('superseded', 'History')]:
            with self.subTest(state=state):
                card = cards([update(state=state)])['update-one']
                self.assertEqual(card['category'], category)
                self.assertEqual(card['state'], state)
                self.assertEqual(card['production'], 'Unverified')
                self.assertTrue(card['limits'])

    def test_explicit_nulls_are_preserved_without_inventing_owner_or_dates(self):
        record = update(owner=None, source_date=None, next_action=None, checkpoint_at=None)
        card = cards([record])['update-one']
        for key in ('owner', 'source_date', 'checkpoint_at', 'reported_next_action'):
            self.assertIsNone(card[key], key)
        self.assertIsInstance(card['next_action'], str)
        self.assertTrue(card['next_action'].strip())
        for output in (w.render(w.build(snapshot([record]))), w.markdown(w.build(snapshot([record])))):
            self.assertNotIn('Owner: None', output)

    def test_all_coordination_fields_are_required_even_when_nullable(self):
        for key in update()['data']:
            with self.subTest(key=key):
                record = update()
                del record['data'][key]
                self.assert_invalid(record)

    def test_unknown_fields_and_raw_material_are_rejected(self):
        for key in ('body', 'comments', 'worker_acknowledged', 'completion_percent', 'extra'):
            with self.subTest(key=key):
                record = update()
                record['data'][key] = 'Unbounded raw source material'
                self.assert_invalid(record)
        record = update()
        record['unexpected_record_field'] = True
        self.assert_invalid(record)

    def test_data_requires_an_object(self):
        for value in (None, [], 'summary', 1, True):
            with self.subTest(value=value):
                record = update()
                record['data'] = value
                self.assert_invalid(record)

    def test_text_types_and_bounds_are_enforced(self):
        for key, limit in [('project', 220), ('owner', 220), ('summary', 1200), ('next_action', 1200)]:
            for value in ('', '   ', 'x' * (limit + 1), [], {}, 7, True, 'bad\x00text'):
                with self.subTest(key=key, value_type=type(value).__name__):
                    record = update(**{key: value})
                    self.assert_invalid(record)
            self.assertEqual(cards([update(**{key: 'x' * limit})])['update-one']['kind'], 'coordination_update')
        for key in ('project', 'summary'):
            self.assert_invalid(update(**{key: None}))

    def test_lane_id_is_a_bounded_stable_lowercase_identifier(self):
        for value in ('', 'Lane', 'a b', '-lane', 'a/b', 'x' * 97, None, [], 5, True):
            with self.subTest(value=value):
                self.assert_invalid(update(lane_id=value))
        for value in ('a', 'a.b_c-9', 'x' * 96):
            with self.subTest(value=value):
                self.assertEqual(cards([update(lane_id=value)])['update-one']['lane_id'], value)

    def test_state_requires_an_exact_supported_string(self):
        for value in ('done', 'NEXT_ACTION', '', None, [], {}, True, 1):
            with self.subTest(value=value):
                self.assert_invalid(update(state=value))

    def test_source_date_requires_an_exact_real_calendar_date(self):
        for value in ('20261010', '2026-10-1', '2026-1-10', '2026-02-29', '2026-13-01',
                      '2026-10-10T00:00:00Z', '2026-10-10 ', '', [], {}, 20261010, True):
            with self.subTest(value=value):
                self.assert_invalid(update(source_date=value))
        self.assertEqual(cards([update(source_date='2024-02-29')])['update-one']['source_date'], '2024-02-29')

    def test_source_date_compares_to_utc_observation_date_not_capture(self):
        record = update(source_date='2026-10-11')
        record['observed_at'] = '2026-10-10T23:30:00-01:00'
        self.assertEqual(cards([record])['update-one']['source_date'], '2026-10-11')
        record['observed_at'] = '2026-10-11T00:30:00+02:00'
        self.assert_invalid(record)
        record = update(source_date='2026-10-11')
        record['observed_at'] = '2026-10-10T12:00:00Z'
        self.assert_invalid(record)

    def test_planned_checkpoint_may_be_future_but_requires_timezone(self):
        future = '2027-01-01T08:30:00-08:00'
        self.assertEqual(cards([update(checkpoint_at=future)])['update-one']['checkpoint_at'], future)
        for value in ('2026-10-12T09:00:00', '2026-10-12', '2026-02-30T00:00:00Z',
                      'tomorrow', '', [], {}, 42, True):
            with self.subTest(value=value):
                self.assert_invalid(update(checkpoint_at=value))

    def test_exact_github_issue_and_pull_comment_sources_are_accepted(self):
        for kind in ('issues', 'pull'):
            record = update()
            record['source_url'] = f'https://github.com/example/studio/{kind}/17#issuecomment-42'
            self.assertEqual(cards([record])['update-one']['source_url'], record['source_url'])

    def test_noncomment_and_noncanonical_source_locators_are_rejected(self):
        for value in (
            'https://github.com/example/studio/issues/17',
            'https://github.com/example/studio/issues/17#pullrequestreview-42',
            'https://github.com/example/studio/issues/17#issuecomment-0',
            'https://github.com/example/studio/issues/0#issuecomment-42',
            'https://github.com/example/studio/issues/-17#issuecomment-42',
            'https://github.com/example/studio/issues/17#issuecomment--42',
            'https://github.com/example/studio/issues/17/extra#issuecomment-42',
            'https://github.com/example/studio/commits/17#issuecomment-42',
            'https://github.com/example/studio/issues/17?token=abc#issuecomment-42',
            'https://github.com/example/studio/issues/17#issuecomment-42-extra',
            'https://github.com/example/studio/issues/17#issuecomment-42/',
            'https://example.invalid/example/studio/issues/17#issuecomment-42',
            'https://github.com@evil.invalid/example/studio/issues/17#issuecomment-42',
            'https://user:password@github.com/example/studio/issues/17#issuecomment-42',
            'http://github.com/example/studio/issues/17#issuecomment-42',
        ):
            with self.subTest(value=value):
                record = update()
                record['source_url'] = value
                self.assert_invalid(record)

    def test_supersedes_requires_a_bounded_list_of_distinct_stable_ids(self):
        for value in (None, 'old', {}, True, [None], [42], [[]], [''], ['Old'],
                      ['a b'], ['x' * 97], ['old', 'old'], [f'old-{i}' for i in range(101)]):
            with self.subTest(value=value):
                self.assert_invalid(update(supersedes=value))


class CoordinationHistoryTests(unittest.TestCase):
    def test_only_explicit_supersession_makes_an_update_historical(self):
        old = update('old', source_date='2026-10-08', next_action='OLD_ACTION_SENTINEL')
        new = update('new', source_date='2026-10-10', next_action='Current action.', supersedes=['old'])
        result = cards([new, old])
        self.assertEqual(result['old']['category'], 'History')
        self.assertEqual(result['old']['superseded_by'], ['new'])
        self.assertNotEqual(result['old']['next_action'], 'OLD_ACTION_SENTINEL')
        self.assertIsInstance(result['old']['next_action'], str)
        self.assertTrue(result['old']['next_action'].strip())
        self.assertEqual(result['old']['reported_next_action'], 'OLD_ACTION_SENTINEL')
        for key in ('facts', 'limits', 'next_action', 'status'):
            self.assertNotIn('OLD_ACTION_SENTINEL', json.dumps(result['old'][key]))
        self.assertEqual(result['new']['category'], 'Action')
        self.assertEqual(result['new']['next_action'], 'Current action.')

    def test_newest_date_and_list_order_do_not_imply_supersession(self):
        old = update('old', source_date='2026-10-08')
        new = update('new', source_date='2026-10-10', state='reported_complete')
        before, after = cards([old, new]), cards([new, old])
        self.assertEqual(before, after)
        self.assertEqual(before['old']['category'], 'Action')
        self.assertEqual(before['new']['category'], 'Completion')
        self.assertEqual(before['old']['superseded_by'], [])

    def test_explicit_history_without_a_replacement_does_not_reactivate_work(self):
        record = update(state='superseded', next_action='INACTIVE_DIRECTION')
        card = cards([record])['update-one']
        self.assertEqual(card['category'], 'History')
        self.assertEqual(card['superseded_by'], [])
        self.assertEqual(card['reported_next_action'], 'INACTIVE_DIRECTION')
        self.assertNotIn('INACTIVE_DIRECTION', card['next_action'])
        self.assertTrue(card['limits'])

    def test_transitive_supersession_preserves_all_history(self):
        result = cards([update('first'), update('second', supersedes=['first']),
                        update('third', supersedes=['second'])])
        self.assertEqual(len(result), 3)
        self.assertEqual(result['first']['category'], 'History')
        self.assertEqual(result['second']['category'], 'History')
        self.assertEqual(result['third']['category'], 'Action')
        self.assertEqual(result['first']['superseded_by'], ['second'])
        self.assertEqual(result['second']['superseded_by'], ['third'])

    def test_multiple_explicit_successors_are_retained_without_choosing_a_winner(self):
        result = cards([update('old'), update('second', supersedes=['old']),
                        update('first', supersedes=['old'])])
        self.assertEqual(set(result['old']['superseded_by']), {'first', 'second'})
        self.assertEqual(result['first']['category'], 'Action')
        self.assertEqual(result['second']['category'], 'Action')

    def test_missing_self_and_cyclic_supersession_are_rejected(self):
        cases = [
            [update(supersedes=['missing'])],
            [update(supersedes=['update-one'])],
            [update('one', supersedes=['two']), update('two', supersedes=['one'])],
            [update('one', supersedes=['three']), update('two', supersedes=['one']),
             update('three', supersedes=['two'])],
        ]
        for records in cases:
            with self.subTest(ids=[record['id'] for record in records]):
                with self.assertRaises(w.EvidenceError):
                    w.build(snapshot(records))

    def test_supersession_cannot_cross_lanes_audiences_or_record_kinds(self):
        old, new = update('old'), update('new', supersedes=['old'])
        wrong_lane = copy.deepcopy(old)
        wrong_lane['data']['lane_id'] = 'another-lane'
        wrong_audience = copy.deepcopy(old)
        wrong_audience['audience'] = 'public'
        handoff = {
            'id': 'old', 'kind': 'handoff', 'audience': 'private', 'title': 'Synthetic receipt',
            'source_url': 'https://github.com/example/studio/issues/17#issuecomment-42',
            'observed_at': NOW, 'data': {'comment_id': 42, 'created_at': NOW,
                                       'target': 'Synthetic owner', 'summary': 'Receipt only.'},
        }
        for predecessor in (wrong_lane, wrong_audience, handoff):
            with self.subTest(kind=predecessor['kind'], data=predecessor['data']):
                with self.assertRaises(w.EvidenceError):
                    w.build(snapshot([predecessor, new]))

    def test_build_does_not_mutate_source_records(self):
        source = snapshot([update('old'), update('new', supersedes=['old'])])
        original = copy.deepcopy(source)
        w.build(source)
        self.assertEqual(source, original)


class CoordinationProjectionTests(unittest.TestCase):
    def test_public_outputs_and_digest_exclude_private_history_and_metadata(self):
        public = update('public-update', lane_id='public-lane')
        public['audience'] = 'public'
        old = update('private-old', lane_id='private-lane', project='PRIVATE_PROJECT_SENTINEL',
                     owner='PRIVATE_OWNER_SENTINEL', next_action='PRIVATE_ACTION_SENTINEL')
        new = update('private-new', lane_id='private-lane', supersedes=['private-old'])
        source = snapshot([public, old, new])
        source.update(title='PRIVATE_TITLE_SENTINEL', scope='PRIVATE_SCOPE_SENTINEL')
        view = w.build(source, 'public')
        self.assertEqual([c['id'] for c in view['cards']], ['public-update'])
        for output in (json.dumps(view), w.markdown(view), w.render(view)):
            for secret in ('PRIVATE_', 'private-lane', 'private-old', 'private-new'):
                self.assertNotIn(secret, output)
        self.assertEqual(view['visible_source_sha256'],
                         w.build(snapshot([public]), 'public')['visible_source_sha256'])

    def test_private_graph_is_validated_before_public_redaction(self):
        private = update(supersedes=['missing'])
        with self.assertRaises(w.EvidenceError):
            w.build(snapshot([private]), 'public')

    def test_public_supersession_cannot_reference_a_hidden_private_record(self):
        old = update('private-old')
        new = update('public-new', supersedes=['private-old'])
        new['audience'] = 'public'
        with self.assertRaises(w.EvidenceError):
            w.build(snapshot([old, new]), 'public')

    def test_retrieval_only_and_freshness_changes_are_not_material_progress(self):
        before = snapshot([update()])
        after = copy.deepcopy(before)
        after['captured_at'] = '2026-10-11T13:00:00Z'
        after['records'][0]['observed_at'] = after['captured_at']
        self.assertEqual(w.compare(w.build(before), w.build(after))['changes'], [])
        self.assertEqual(w.compare(w.build(before),
                                   w.build(before, as_of='2026-10-13T13:00:00Z'))['changes'], [])

    def test_material_coordination_changes_are_detected(self):
        before = w.build(snapshot([update()]))
        for field, value in [('owner', 'Another owner'), ('project', 'Another project'),
                             ('lane_id', 'another-lane'), ('state', 'blocked'),
                             ('source_date', '2026-10-09'), ('summary', 'New source fact.'),
                             ('next_action', 'A different next action.'),
                             ('checkpoint_at', '2026-10-14T09:00:00Z')]:
            with self.subTest(field=field):
                after = w.build(snapshot([update(**{field: value})]))
                changes = w.compare(before, after)['changes']
                self.assertEqual(len(changes), 1)
                self.assertEqual(changes[0]['change'], 'material_change')

    def test_supersession_reports_new_receipt_and_changed_predecessor(self):
        old = update('old')
        before = w.build(snapshot([old]))
        after = w.build(snapshot([old, update('new', supersedes=['old'])]))
        changes = {change['id']: change for change in w.compare(before, after)['changes']}
        self.assertEqual(changes['new']['change'], 'newly_observed')
        self.assertEqual(changes['old']['change'], 'material_change')
        self.assertIn('superseded_by', changes['old']['fields'])

    def test_missing_update_is_not_reported_as_deletion(self):
        change = w.compare(w.build(snapshot([update()])), w.build(snapshot([])))['changes'][0]
        self.assertEqual(change['change'], 'not_observed_in_new_snapshot')


class CoordinationRenderingTests(unittest.TestCase):
    def test_history_and_active_cards_exist_without_javascript(self):
        view = w.build(snapshot([update('old'), update('new', supersedes=['old'])]))
        output = w.render(view)
        markup = Markup(output)
        articles = [attrs for tag, attrs in markup.elements if tag == 'article']
        self.assertEqual(len(articles), 2)
        self.assertEqual({attrs['data-category'] for attrs in articles}, {'Action', 'History'})
        for attrs in articles:
            self.assertNotIn('hidden', attrs)
        filters = {attrs['data-filter'] for tag, attrs in markup.elements
                   if tag == 'button' and 'data-filter' in attrs}
        self.assertTrue({'All', 'Action', 'Completion', 'Research', 'History'}.issubset(filters))
        self.assertIn('<noscript>', output)
        self.assertEqual(len([1 for tag, attrs in markup.elements
                              if tag == 'a' and attrs.get('href', '').startswith('https://github.com/')]), 2)

    def test_user_text_is_escaped_in_html_attributes_and_embedded_json(self):
        attack = '</script><img src=x onerror="alert(1)"> & @@CARDS@@'
        record = update(project=attack, owner=attack, summary=attack, next_action=attack)
        record['title'] = attack
        output = w.render(w.build(snapshot([record])))
        markup = Markup(output)
        self.assertFalse(any(tag == 'img' for tag, _ in markup.elements))
        self.assertFalse(any(key.startswith('on') for _, attrs in markup.elements for key in attrs))
        self.assertIn('&lt;img', output)
        self.assertIn('@@CARDS@@', output)
        payload = re.search(r'<script\b[^>]*\bid="evidence-data"[^>]*>(.*?)</script>', output, re.S).group(1)
        self.assertNotIn('<', payload)
        self.assertEqual(json.loads(payload)['cards'][0]['reported_next_action'], attack)

    def test_csp_hashes_match_rendered_script_and_style_bytes(self):
        output = w.render(w.build(snapshot([update()])))
        markup = Markup(output)
        csp = next(attrs['content'] for tag, attrs in markup.elements
                   if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy')
        self.assertIn("connect-src 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        for tag in ('script', 'style'):
            chunks = re.findall(fr'<{tag}(?:\s[^>]*)?>(.*?)</{tag}>', output, re.S)
            self.assertTrue(chunks)
            for chunk in chunks:
                digest = base64.b64encode(hashlib.sha256(chunk.encode()).digest()).decode()
                self.assertIn("'sha256-" + digest + "'", csp)

    def test_markdown_retains_the_source_and_inactive_action_is_not_next_step(self):
        old = update('old', next_action='OLD_NEXT_STEP_SENTINEL')
        new = update('new', supersedes=['old'])
        output = w.markdown(w.build(snapshot([old, new])))
        self.assertIn(old['source_url'], output)
        self.assertNotIn('Next step: OLD_NEXT_STEP_SENTINEL', output)

    def test_render_is_deterministic(self):
        view = w.build(snapshot([update('old'), update('new', supersedes=['old'])]))
        self.assertEqual(w.render(view), w.render(view))


class CoordinationCliTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              cwd=cwd, capture_output=True, text=True)

    def test_actual_validate_and_build_preserve_history_and_explicit_nulls(self):
        source_data = snapshot([update('old', owner=None, checkpoint_at=None),
                                update('new', supersedes=['old'])])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_text(json.dumps(source_data), encoding='utf-8')
            validated = self.run_cli('validate', '--input', source, '--json-errors', cwd=directory)
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout)['records'], 2)
            self.assertEqual(list(Path(directory).iterdir()), [source])
            output = Path(directory) / 'result'
            built = self.run_cli('build', '--input', source, '--output', output, '--json-errors')
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(set(json.loads(built.stdout)['artifacts']), {'index.html', 'brief.md', 'view.json'})
            result = {card['id']: card for card in json.loads((output / 'view.json').read_text())['cards']}
            self.assertEqual(result['old']['category'], 'History')
            self.assertIsNone(result['old']['owner'])
            self.assertIsNone(result['old']['checkpoint_at'])

    def test_invalid_graph_returns_a_json_error_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_text(json.dumps(snapshot([update(supersedes=['missing'])])))
            output = Path(directory) / 'untouched'
            result = self.run_cli('build', '--input', source, '--output', output, '--json-errors')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)['status'], 'error')
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)

