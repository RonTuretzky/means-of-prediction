import contextlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import qwen_guarded_rules as g


class GuardedRuleTests(unittest.TestCase):
    def entries(self, n=12):
        return [{'marketId': str(i)} for i in range(n)]

    def test_bounded_inflight_and_all_nonusage_failed_records_retained(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(g.q, 'ROOT', Path(temp)), contextlib.redirect_stdout(io.StringIO()):
            barrier = threading.Barrier(3)
            lock = threading.Lock()
            active = 0
            maximum = 0
            def worker(method, entry, gate):
                nonlocal active, maximum
                with gate.lock:
                    gate.started.append(entry['marketId'])
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                barrier.wait(timeout=5)
                with lock:
                    active -= 1
                return {'marketId': entry['marketId'], 'status': 'transport_failed', 'output': None}
            result = g.feed('v3', self.entries(), 3, worker)
            self.assertEqual(maximum, 3)
            self.assertEqual(len(result['records']), 12)
            self.assertEqual(result['unattemptedMarketIds'], [])
            self.assertIsNone(result['stopReason'])

    def test_first_usage_stops_feeder_but_keeps_other_inflight_results(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(g.q, 'ROOT', Path(temp)), contextlib.redirect_stdout(io.StringIO()):
            barrier = threading.Barrier(3)
            observed = threading.Event()
            def worker(method, entry, gate):
                with gate.lock:
                    gate.started.append(entry['marketId'])
                barrier.wait(timeout=5)
                if entry['marketId'] == '0':
                    target = Path(temp) / 'usage-response'
                    target.mkdir()
                    g.q.r.save(target / 'transport-result.json', {'serviceErrors': [{'error': {'type': 'usage_limit_reached'}}]})
                    with gate.lock:
                        gate.halt('usage_limit_reached', target)
                    observed.set()
                    return {'marketId': '0', 'status': 'transport_failed', 'output': None}
                observed.wait(timeout=5)
                return {'marketId': entry['marketId'], 'status': 'completed', 'output': {}}
            result = g.feed('v3', self.entries(), 3, worker)
            self.assertEqual(result['submittedMarketIds'], ['0', '1', '2'])
            self.assertEqual(len(result['records']), 3)
            self.assertEqual(len(result['unattemptedMarketIds']), 9)
            self.assertTrue((Path(temp) / g.STOP).exists())
            with patch.object(g, 'one') as call:
                later = g.feed('v3', self.entries(), 3, call)
                call.assert_not_called()
                self.assertEqual(len(later['unattemptedMarketIds']), 12)

    def test_original_public_job_and_single_attempt_failure_preserved(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(g.q, 'ROOT', Path(temp)):
            public = {'marketId': '1', 'question': 'Threshold?', 'rules': 'strict original', 'outcomeLabels': ['A', 'B']}
            self.assertEqual(set(public), g.q.r.PUBLIC_KEYS)
            job = g.q.rule_job(public, 'reviewed prompt', {'public': 'context'})
            path = g.directory('v3') / 'inputs/1.json'
            path.parent.mkdir(parents=True)
            g.q.r.save(path, job)
            def fail(value, target):
                self.assertEqual(value, job)
                target.mkdir(parents=True)
                g.q.r.save(target / 'parsed.json', {'status': 'transport_failed', 'output': None})
                g.q.r.save(target / 'transport-result.json', {'serviceErrors': [{'error': {'type': 'usage_limit_reached'}}]})
                raise RuntimeError('preserved failure')
            gate = g.Gate()
            with patch.object(g.q.r, 'safe_call', side_effect=fail) as call, patch.object(g.q.r, 'verify_model_artifact'):
                record = g.one('v3', {'marketId': '1'}, gate)
                self.assertEqual(record['status'], 'transport_failed')
                self.assertIsNone(g.one('v3', {'marketId': '1'}, gate))
                self.assertEqual(call.call_count, 1)
            with self.assertRaises(ValueError):
                g.q.rule_job({**public, 'expected': 'A'}, 'prompt')

    def test_preexisting_uncertain_draw_is_never_retried(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(g.q, 'ROOT', Path(temp)):
            root = g.directory('v3')
            (root / 'inputs').mkdir(parents=True)
            g.q.r.save(root / 'inputs/1.json', {})
            (root.parent / 'rules/1/1').mkdir(parents=True)
            with patch.object(g.q.r, 'safe_call') as call:
                with self.assertRaises(RuntimeError):
                    g.one('v3', {'marketId': '1'}, g.Gate())
                call.assert_not_called()

    def test_partial_run_does_not_fabricate_rules_or_full_freeze(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(g.q, 'ROOT', Path(temp)), contextlib.redirect_stdout(io.StringIO()):
            root = g.directory('v3')
            root.mkdir(parents=True)
            plan = {'entries': self.entries(2), 'workers': 1}
            g.q.r.save(root / 'plan.json', plan)
            g.q.r.save(root / 'reviewed.json', {'approved': True, 'planSha256': g.q.r.digest(root / 'plan.json')})
            partial = {'records': [{'marketId': '0', 'status': 'transport_failed', 'output': None}], 'errors': [],
                       'attemptedMarketIds': ['0'], 'unattemptedMarketIds': ['1'], 'submittedMarketIds': ['0'], 'stopReason': 'usage_limit_reached'}
            with patch.object(g, 'verify_plan', return_value=plan), patch.object(g, 'prompt_review'), patch.object(g, 'feed', return_value=partial):
                with self.assertRaises(RuntimeError):
                    g.run('v3')
            self.assertFalse((root.parent / 'rules.json').exists())
            self.assertFalse((root.parent / 'rules-freeze.json').exists())
            self.assertEqual(g.q.r.read(root / 'dispatch-result.json'), partial)
            self.assertFalse(g.q.r.read(root / 'completed.json')['completeCohort'])


if __name__ == '__main__':
    unittest.main()
