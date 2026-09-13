import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import qwen_guarded_challenge as c


def public():
    return [{'marketId': str(i), 'question': 'Synthetic event?', 'rules': 'Original synthetic terms.', 'outcomeLabels': ['A', 'B']} for i in range(12)]


class FreshGuardTests(unittest.TestCase):
    def test_repo_source_cannot_dispatch_fresh_calls(self):
        with patch.object(c.q, 'verify_selection') as verify:
            with self.assertRaises(RuntimeError): c.selection_gate('baseline')
            verify.assert_not_called()

    def test_unselected_method_and_opened_fixtures_block_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.q, 'ROOT', Path(tmp)), patch.object(c, 'sealed_only'), patch.object(c.q, 'verify_selection', return_value={'freshMethods': ['baseline', 'v3']}):
            with self.assertRaises(RuntimeError): c.selection_gate('v2')
            (Path(tmp) / 'fresh-opened.json').write_text('{}')
            with self.assertRaises(RuntimeError): c.selection_gate('baseline')

    def test_exact_two_public_draws_without_fixture_or_context_reads(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.q, 'ROOT', Path(tmp)):
            (Path(tmp) / 'baseline.txt').write_text('Frozen public-only generator.')
            calls = []
            def load(name):
                calls.append(name)
                if name != 'independent-holdout-public.json':
                    raise AssertionError('Unexpected data read: ' + name)
                return public()
            with patch.object(c.q, 'load', side_effect=load):
                jobs = c.public_jobs('baseline')
            self.assertEqual(calls, ['independent-holdout-public.json'])
            self.assertEqual(len(jobs), 24)
            self.assertEqual({(x['publicMarketId'], x['trial']) for x in jobs}, {(str(i), t) for i in range(12) for t in [1, 2]})
            for x in jobs:
                expected = c.q.rule_job(public()[int(x['publicMarketId'])], 'Frozen public-only generator.', None, x['trial'])
                self.assertEqual(x['job'], expected)
                self.assertNotIn('publicContext', x['job']['input'])

    def test_fresh_single_attempt_failure_keeps_original_job_and_trial(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.q, 'ROOT', Path(tmp)):
            entry = {'marketId': '0/2', 'publicMarketId': '0', 'trial': 2, 'inputFile': '0-2.json'}
            directory = c.root('baseline'); (directory / 'inputs').mkdir(parents=True)
            job = c.q.rule_job(public()[0], 'Frozen prompt.', None, 2)
            c.q.r.save(directory / 'inputs/0-2.json', job)
            def failure(value, target):
                self.assertEqual(value, job)
                self.assertEqual(target, directory.parent / 'challenge-rules/0/2')
                target.mkdir(parents=True)
                c.q.r.save(target / 'parsed.json', {'status': 'transport_failed', 'output': None})
                c.q.r.save(target / 'transport-result.json', {'serviceErrors': [{'error': {'type': 'usage_limit_reached'}}]})
                raise RuntimeError('Preserved failed draw')
            gate = c.g.Gate()
            with patch.object(c.q.r, 'safe_call', side_effect=failure) as call, patch.object(c.q.r, 'verify_model_artifact'):
                result = c.one('baseline', entry, gate)
                self.assertEqual((result['marketId'], result['trial']), ('0', 2))
                self.assertEqual(result['status'], 'transport_failed')
                self.assertIsNone(c.one('baseline', entry, gate))
                self.assertEqual(call.call_count, 1)
            self.assertTrue((Path(tmp) / c.g.STOP).exists())

    def test_partial_fresh_run_does_not_create_standard_rules_or_global_freeze(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(c.q, 'ROOT', Path(tmp)), contextlib.redirect_stdout(io.StringIO()):
            directory = c.root('baseline'); directory.mkdir(parents=True)
            plan = {'workers': 1, 'entries': [{'marketId': str(i) + '/' + str(t), 'publicMarketId': str(i), 'trial': t} for i in range(12) for t in [1, 2]]}
            c.q.r.save(directory / 'plan.json', plan)
            c.q.r.save(directory / 'reviewed.json', {'approved': True, 'planSha256': c.q.r.digest(directory / 'plan.json')})
            result = {'records': [{'marketId': '0', 'trial': 1, 'status': 'transport_failed', 'output': None}],
                'errors': [], 'attemptedMarketIds': ['0/1'], 'unattemptedMarketIds': [x['marketId'] for x in plan['entries'][1:]], 'stopReason': 'usage_limit_reached'}
            with patch.object(c, 'verify_plan', return_value=plan), patch.object(c.g, 'feed', return_value=result):
                with self.assertRaises(RuntimeError): c.run('baseline')
            self.assertFalse((directory.parent / 'challenge-rules.json').exists())
            self.assertFalse((directory.parent / 'challenge-rules-freeze.json').exists())
            self.assertFalse((Path(tmp) / 'challenge-freeze.json').exists())
            self.assertFalse((Path(tmp) / 'fresh-opened.json').exists())
            self.assertEqual(c.q.r.read(directory / 'dispatch-result.json'), result)


if __name__ == '__main__':
    unittest.main()
