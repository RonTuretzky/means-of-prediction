import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import qwen_capacity_recovery as c


class RecoveryTests(unittest.TestCase):
    def test_usage_error_detected_without_message_matching(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            c.q.r.save(path / 'transport-result.json', {'serviceErrors': ['{"error":{"type":"usage_limit_reached"}}']})
            self.assertTrue(c.usage_limited(path))
            c.q.r.save(path / 'transport-result.json', {'serviceErrors': ['bad json', '{"error":{"type":"server_error"}}']})
            self.assertFalse(c.usage_limited(path))

    def test_new_usage_error_persists_stop_before_another_call(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)):
            c.q.once(c.POLICY, {'priorFailedRequests': {}})
            def failed(job, directory):
                directory.mkdir(parents=True)
                c.q.r.save(directory / 'parsed.json', {'status': 'transport_failed', 'output': None})
                c.q.r.save(directory / 'transport-result.json', {'serviceErrors': ['{"error":{"type":"usage_limit_reached"}}']})
                raise RuntimeError('failure')
            with patch.object(c.q.r, 'safe_call', side_effect=failed) as call:
                with self.assertRaises(RuntimeError): c.teacher({}, Path(temp) / 'first')
                with self.assertRaises(RuntimeError): c.teacher({}, Path(temp) / 'second')
                self.assertEqual(call.call_count, 1)
            self.assertTrue((Path(temp) / c.STOP).exists())

    def test_failed_nonusage_call_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)):
            c.q.once(c.POLICY, {'priorFailedRequests': {}})
            def failed(job, directory):
                directory.mkdir(parents=True)
                result = {'status': 'transport_failed', 'output': None}
                c.q.r.save(directory / 'parsed.json', result)
                return result
            with patch.object(c.q.r, 'safe_call', side_effect=failed) as call:
                with self.assertRaises(RuntimeError): c.teacher({}, Path(temp) / 'first')
                with self.assertRaises(RuntimeError): c.teacher({}, Path(temp) / 'first')
                self.assertEqual(call.call_count, 1)

    def test_fourth_attempt_preserves_three_failures(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)):
            directory = Path(temp) / 'feedback/v2/58'
            job = {'input': 'whole evidence'}
            c.q.once(c.POLICY, {'priorFailedRequests': {'feedback/v2/58': {'sameInputSha256': c.q.r.hash_value(job), 'failedAttempts': 3}}})
            for number in range(3):
                d = directory if number == 0 else directory / 'teacher-recovery' / str(number)
                d.mkdir(parents=True, exist_ok=True)
                c.q.r.save(d / 'parsed.json', {'status': 'transport_failed', 'output': None})
            def succeeded(value, target):
                self.assertEqual(value, job)
                self.assertEqual(target, directory / 'teacher-recovery/3')
                target.mkdir(parents=True)
                result = {'status': 'completed', 'output': {'lesson': 'generic'}}
                c.q.r.save(target / 'parsed.json', result)
                return result
            with patch.object(c.q.r, 'verify_model_artifact'), patch.object(c.q.r, 'safe_call', side_effect=succeeded) as call:
                result = c.teacher(job, directory)
                self.assertEqual(call.call_count, 1)
            self.assertEqual(result['selectedAttempt'], 3)
            self.assertEqual([a['status'] for a in result['attempts']], ['transport_failed'] * 3 + ['completed'])


if __name__ == '__main__':
    unittest.main()
