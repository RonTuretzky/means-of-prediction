import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import qwen_final_audit as audit


class FinalAuditTests(unittest.TestCase):
    def test_fresh_guard_runs_before_any_fixture_read(self):
        with patch.object(audit.q, 'verify_selection', side_effect=RuntimeError('not frozen')):
            with patch.object(audit.q.r, 'read') as read:
                with self.assertRaises(RuntimeError): audit.verify_fresh_source()
                read.assert_not_called()

    def test_completed_output_is_bound_to_raw_http_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            request = {'messages': [], 'model': 'local'}
            output = {'factualOutcome': 'A', 'outcomeA': 'YES', 'outcomeB': 'NO', 'evidenceQuote': 'won', 'missingConditions': []}
            response = {'model': 'local', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(output)}}], 'usage': {'completion_tokens': 7}}
            (path / 'response.raw').write_text(json.dumps(response))
            for name, value in [('request.json', request), ('response.json', response)]: audit.q.r.save(path / name, value)
            result = {'status': 'completed', 'output': output, 'httpStatus': 200, 'usage': response['usage'],
                      'returnedModel': 'local', 'reasoningCharacters': 0,
                      'requestSha256': audit.q.r.hash_value(request), 'responseSha256': audit.q.r.digest(path / 'response.json'),
                      'rawResponseSha256': audit.q.r.digest(path / 'response.raw')}
            audit.q.r.save(path / 'result.json', result)
            record = {'directory': directory, **result}
            audit.verify_local(record, request)
            for mutation in [{'returnedModel': 'other'}, {'reasoningCharacters': 1}]:
                changed = {**result, **mutation}
                audit.q.r.save(path / 'result.json', changed)
                with self.assertRaises(RuntimeError): audit.verify_local({'directory': directory, **changed}, request)
            audit.q.r.save(path / 'result.json', result)
            (path / 'response.raw').write_text('{}')
            with self.assertRaises(RuntimeError): audit.verify_local(record, request)

    def test_failed_control_does_not_inflate_scored_negative_denominator(self):
        item = {'caseId': 'x', 'marketId': 'm', 'kind': 'control', 'expected': 'neither', 'metadata': {}, 'email': {'completeSemanticText': 'body'}}
        row = audit.q.score_record(item, {'status': 'failed', 'output': None, 'trial': 1})
        c = audit.counts([row])
        self.assertEqual(c['negativeRows'], 1)
        self.assertEqual(c['scoredNegatives'], 0)
        self.assertEqual(c['negativeRejections'], 0)
        self.assertEqual(c['unscorable'], 1)

    def test_runtime_check_rejects_model_substitution(self):
        info = dict(identifier='local', modelKey='qwen', format='gguf', path='qwen-Q4.gguf', sizeBytes=10,
                    architecture='qwen35moe', quantization={'name': 'Q4_K_M', 'bits': 4}, contextLength=131072)
        runtime = {'identifier': 'local', 'contextLength': 131072, 'loadedModels': [info]}
        preflight = {'contextLength': 131072, 'modelInfo': dict(info)}
        audit.q.verify_preflight_runtime(preflight, runtime)
        preflight['modelInfo']['path'] = 'other-model.gguf'
        with self.assertRaises(RuntimeError): audit.q.verify_preflight_runtime(preflight, runtime)

    def test_missing_usage_is_retained_for_failed_attempt(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(audit.q, 'ROOT', Path(directory)):
            path = Path(directory) / 'methods/baseline/rules/m/1'
            path.mkdir(parents=True)
            audit.q.r.save(path / 'transport-result.json', {'events': []})
            report = audit.usage()['groups']['astra/baseline/rules']
            self.assertEqual(report['attempts'], 1)
            self.assertEqual(report['completed'], 0)
            self.assertEqual(report['missingUsage'], 1)
            self.assertEqual(report['missingInputUsage'], 1)
            self.assertEqual(report['missingOutputUsage'], 1)
            self.assertEqual(report['missingDuration'], 1)
            self.assertTrue(all(report['knownTotalsAreLowerBounds'].values()))

    def test_input_only_omission_and_duration_are_accounted_separately(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(audit.q, 'ROOT', Path(directory)):
            path = Path(directory) / 'methods/v2/development/case/1'
            path.mkdir(parents=True)
            audit.q.r.save(path / 'started.json', {})
            audit.q.r.save(path / 'request.json', {'messages': []})
            audit.q.r.save(path / 'result.json', {'status': 'completed', 'usage': {'completion_tokens': 7}, 'seconds': 2})
            report = audit.usage()['groups']['local/v2/development']
            self.assertEqual((report['missingInputUsage'], report['missingOutputUsage'], report['missingDuration']), (1, 0, 0))
            self.assertEqual(report['missingUsage'], 1)
            self.assertEqual((report['inputTokens'], report['outputTokens'], report['summedRequestSeconds']), (0, 7, 2))
            self.assertEqual(report['knownTotalsAreLowerBounds'], {'inputTokens': True, 'outputTokens': False, 'summedRequestSeconds': False})
            audit.q.r.save(path / 'result.json', {'status': 'failed', 'usage': {'prompt_tokens': 100}})
            report = audit.usage()['groups']['local/v2/development']
            self.assertEqual((report['missingInputUsage'], report['missingOutputUsage'], report['missingDuration']), (0, 1, 1))
            self.assertEqual(report['inputTokens'], 100)

    def test_sdk_capped_and_native_rejected_probes_remain_in_accounting(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(audit.q, 'ROOT', Path(directory)):
            sdk = Path(directory) / 'runtime-probes/sdk-mode/case/open-free'
            native = Path(directory) / 'runtime-probes/native-mode/case/off'
            for path in [sdk, native]:
                path.mkdir(parents=True); audit.q.r.save(path / 'started.json', {})
            audit.q.r.save(sdk / 'request.json', {'api': 'SDK.complete', 'prompt': 'body'})
            audit.q.r.save(sdk / 'result.json', {'status': 'response_received', 'stats': {'stopReason': 'maxPredictedTokensReached', 'promptTokensCount': 100, 'predictedTokensCount': 2048}, 'seconds': 5})
            audit.q.r.save(native / 'request.json', {'input': 'body', 'system_prompt': 'instructions'})
            audit.q.r.save(native / 'result.json', {'status': 'failed', 'httpStatus': 400, 'usage': None})
            groups = audit.usage()['groups']
            self.assertEqual(groups['local/runtime-probes/sdk-mode']['outputTokensCapped'], 1)
            self.assertEqual(groups['local/runtime-probes/sdk-mode']['outputTokens'], 2048)
            self.assertEqual(groups['local/runtime-probes/sdk-mode']['completed'], 0)
            self.assertEqual(groups['local/runtime-probes/native-mode']['attempts'], 1)
            self.assertEqual(groups['local/runtime-probes/native-mode']['missingUsage'], 1)


if __name__ == '__main__': unittest.main()
