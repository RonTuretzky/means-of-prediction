import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import real_answerability_audit_v1 as audit
from astra_transport import build_request
from test_real_answerability_v1 import item, output, public


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.override = patch.object(audit.a, 'ROOT', self.root)
        self.override.start()
        self.entry = {'name': 'a/000', 'caseId': '000', 'pass': 'a'}
        self.d = self.root/'responses/a/000'
        self.d.mkdir(parents=True)
        self.job = audit.a.make_job(item(), public(), 'a')
        self.out = output()
        self.write(self.root/'jobs/a/000.json', self.job)
        self.write(self.d/'job.json', self.job)
        self.write(self.d/'model-request.json', build_request(self.job))
        usage = {'input_tokens': 100, 'output_tokens': 20}
        self.transport = {'requests': [{'status': 200, 'requestSha256': audit.a.q.r.digest(self.d/'model-request.json')}],
                          'events': [{'type': 'response.completed', 'response': {'model': 'gpt-6-astra', 'status': 'completed',
                                      'usage': usage, 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(self.out)}]}]}}]}
        self.write(self.d/'transport-result.json', self.transport)
        self.write(self.d/'parsed.json', {'output': self.out, 'usage': usage, 'status': 'completed'})
        self.write(self.d/'teacher-effective.json', {'sameInputSha256': audit.a.q.r.hash_value(self.job), 'status': 'completed',
                    'selectedAttempt': 0, 'attempts': [{'directory': str(self.d), 'status': 'completed',
                    'parsedSha256': audit.a.q.r.digest(self.d/'parsed.json')}], 'output': self.out})
        self.saved = {**self.entry, 'status': 'completed', 'validationErrors': [], 'output': self.out}
        self.write(self.d/'review.private.json', self.saved)

    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_accept_raw_service_bound_annotation(self):
        row = audit.reconcile(self.entry)
        self.assertTrue(row['rawVerified'])
        self.assertEqual(row['inputTokens'], 100)

    def test_reject_mutated_saved_annotation(self):
        self.saved['output'] = dict(self.out, coreOutcome='B')
        self.write(self.d/'review.private.json', self.saved)
        with self.assertRaisesRegex(RuntimeError, 'raw service output'):
            audit.reconcile(self.entry)

    def test_reject_additional_request(self):
        self.transport['requests'] *= 2
        self.write(self.d/'transport-result.json', self.transport)
        with self.assertRaisesRegex(RuntimeError, 'request count'):
            audit.reconcile(self.entry)

    def test_reject_actual_tool_setting_mutation(self):
        request = build_request(self.job)
        request['tools'] = [{'type': 'web_search'}]
        self.write(self.d/'model-request.json', request)
        with self.assertRaisesRegex(RuntimeError, 'Actual model request'):
            audit.reconcile(self.entry)

    def test_reject_annotation_identity_mutation(self):
        self.saved['caseId'] = '001'
        self.write(self.d/'review.private.json', self.saved)
        with self.assertRaisesRegex(RuntimeError, 'identity mismatch'):
            audit.reconcile(self.entry)

    def test_failed_attempt_retains_all_hashes_and_available_usage(self):
        self.write(self.d/'review.private.json', {**self.entry, 'status': 'failed', 'error': 'parse failed'})
        row = audit.reconcile(self.entry)
        self.assertFalse(row['rawVerified'])
        self.assertEqual(row['inputTokens'], 100)
        self.assertEqual(row['outputTokens'], 20)
        self.assertIn('responses/a/000/review.private.json', row['fileHashes'])
        self.assertIn('responses/a/000/model-request.json', row['fileHashes'])

    def test_failed_attempt_rejects_extra_http_request(self):
        self.write(self.d/'review.private.json', {**self.entry, 'status': 'failed'})
        self.transport['requests'] *= 2
        self.write(self.d/'transport-result.json', self.transport)
        with self.assertRaisesRegex(RuntimeError, 'Failed request count'):
            audit.reconcile(self.entry)

    def test_failed_attempt_without_transport_keeps_usage_unknown(self):
        self.write(self.d/'review.private.json', {**self.entry, 'status': 'failed'})
        (self.d/'transport-result.json').unlink()
        row = audit.reconcile(self.entry)
        self.assertIsNone(row['inputTokens'])
        self.assertIsNone(row['outputTokens'])
        self.assertTrue(row['fileHashes'])


if __name__ == '__main__':
    unittest.main()
