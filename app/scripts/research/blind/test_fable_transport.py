import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import fable_transport
from fable_transport import MODEL, build_request, output_from, run, smoke_job
import experiment

SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}, 'required': ['a'], 'additionalProperties': False}
JOB = {'instructions': 'fixed', 'input': {'publicMarket': {'question': 'Q'}, 'independentTrial': 1}, 'effort': 'medium', 'schema': SCHEMA}

def message(text='{"a":"x"}', stop='end_turn', model=MODEL, usage=None):
    return {'type': 'message', 'model': model, 'stop_reason': stop, 'stop_details': None,
            'content': [{'type': 'thinking'}, {'type': 'text', 'text': text}],
            'usage': usage if usage is not None else {'input_tokens': 10, 'output_tokens': 5}}

class FakeMessage:
    def __init__(self, record, request_id='req_1'):
        self.record = record; self._request_id = request_id
    def to_dict(self): return json.loads(json.dumps(self.record))

class FakeStream:
    def __init__(self, record): self.record = record
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def get_final_message(self): return FakeMessage(self.record)

def fake_client(record):
    client = MagicMock()
    client.messages.stream.side_effect = lambda **body: FakeStream(record)
    return client

class BuildRequestTests(unittest.TestCase):
    def test_request_is_tool_free_and_carries_only_the_audited_job(self):
        body = build_request({**JOB, 'tools': [{'type': 'shell'}], 'messages': [{'content': 'PRIVATE_TARGET_EMAIL'}],
                              'temperature': 0, 'thinking': {'type': 'disabled'}})
        self.assertEqual(body['model'], 'claude-fable-5-1')
        for forbidden in ['tools', 'tool_choice', 'temperature', 'top_p', 'top_k', 'thinking', 'fallbacks', 'betas']:
            self.assertNotIn(forbidden, body)
        self.assertNotIn('PRIVATE_TARGET_EMAIL', json.dumps(body))
        self.assertEqual(body['system'], 'fixed')
        self.assertEqual(body['messages'], [{'role': 'user', 'content': [{'type': 'text', 'text': json.dumps(JOB['input'], ensure_ascii=False)}]}])
        self.assertEqual(body['output_config'], {'effort': 'medium', 'format': {'type': 'json_schema', 'schema': SCHEMA}})
        self.assertEqual(body['max_tokens'], fable_transport.DEFAULT_MAX_OUTPUT_TOKENS)

    def test_explicit_output_cap_and_effort_validation(self):
        self.assertEqual(build_request({**JOB, 'maxOutputTokens': 2000})['max_tokens'], 2000)
        self.assertEqual(build_request({k: v for k, v in JOB.items() if k != 'effort'})['output_config']['effort'], 'high')
        with self.assertRaises(ValueError): build_request({**JOB, 'effort': 'ultra'})

    def test_request_is_deterministic_for_hashing(self):
        self.assertEqual(json.dumps(build_request(JOB)), json.dumps(build_request(json.loads(json.dumps(JOB)))))

class OutputFromTests(unittest.TestCase):
    def test_completed_message_parses_json(self):
        out, usage, status = output_from({'provider': 'anthropic', 'events': [message()]})
        self.assertEqual(out, {'a': 'x'}); self.assertEqual(usage['output_tokens'], 5); self.assertEqual(status, 'completed')

    def test_non_terminal_stop_reasons_never_count_as_success(self):
        for stop, expected in [('max_tokens', 'incomplete'), ('refusal', 'refusal'), ('pause_turn', 'pause_turn')]:
            out, _, status = output_from({'provider': 'anthropic', 'events': [message(stop=stop)]})
            self.assertIsNone(out); self.assertEqual(status, expected)

    def test_model_mismatch_and_invalid_json_and_missing_events(self):
        self.assertEqual(output_from({'provider': 'anthropic', 'events': [message(model='claude-opus-4-8')]})[2], 'model_mismatch')
        self.assertEqual(output_from({'provider': 'anthropic', 'events': [message(text='not json')]})[2], 'invalid_json')
        self.assertEqual(output_from({'provider': 'anthropic', 'events': []}), (None, {}, 'transport_failed'))

    def test_experiment_dispatches_by_provider_and_keeps_legacy_shape(self):
        self.assertEqual(experiment.output_from({'provider': 'anthropic', 'events': [message()]})[0], {'a': 'x'})
        legacy = {'events': [{'response': {'model': 'gpt-6-astra', 'status': 'completed', 'usage': {},
                  'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"a":"legacy"}'}]}]}}]}
        self.assertEqual(experiment.output_from(legacy)[0], {'a': 'legacy'})
        self.assertEqual(experiment.output_from({'events': [message()]})[2], 'model_mismatch')

class RunTests(unittest.TestCase):
    def test_run_records_request_hash_output_and_no_secret(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-SECRET-KEY'}):
            state = run(JOB, Path(d)/'one', client=fake_client(message()))
            files = sorted(p.name for p in (Path(d)/'one').iterdir())
            self.assertEqual(files, ['model-request.json', 'output.txt', 'process.json', 'transport-checkpoint.json', 'transport-result.json'])
            self.assertEqual(json.loads((Path(d)/'one'/'model-request.json').read_text()), build_request(JOB))
            self.assertEqual(state['requests'][0]['status'], 200); self.assertEqual(state['requests'][0]['requestId'], 'req_1')
            self.assertEqual(len(state['requests'][0]['requestSha256']), 64)
            self.assertEqual(state['model'], MODEL); self.assertEqual(state['stopReason'], 'end_turn')
            self.assertEqual(state['events'][0]['content'], [{'type': 'thinking'}, {'type': 'text', 'text': '{"a":"x"}'}])
            self.assertEqual((Path(d)/'one'/'output.txt').read_text(), '{"a":"x"}')
            for p in (Path(d)/'one').iterdir(): self.assertNotIn('SECRET', p.read_text())
            self.assertEqual(experiment.output_from(json.loads((Path(d)/'one'/'transport-result.json').read_text()), Path(d)/'one')[0], {'a': 'x'})

    def test_service_error_is_retained_as_receipt_without_retry(self):
        import anthropic, httpx2
        response = httpx2.Response(429, request=httpx2.Request('POST', 'https://api.anthropic.com/v1/messages'),
                                   text='{"type":"error","error":{"type":"rate_limit_error","message":"slow down"}}')
        client = MagicMock()
        client.messages.stream.side_effect = anthropic.RateLimitError('rate limited', response=response, body=None)
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'k'}):
            state = run(JOB, d, client=client)
            self.assertEqual(client.messages.stream.call_count, 1)
            self.assertEqual(state['requests'][0]['status'], 429); self.assertEqual(state['events'], [])
            self.assertIn('rate_limit_error', state['serviceErrors'][0])
            self.assertEqual(experiment.output_from(state)[2], 'transport_failed')

    def test_missing_credential_is_a_receipt_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'ANTHROPIC_API_KEY': ''}), \
             patch.object(fable_transport, 'CREDENTIAL_FILE', Path(d)/'absent.json'):
            state = run(JOB, Path(d)/'r')
            self.assertEqual(state['requests'][0]['status'], None)
            self.assertTrue(state['transportErrors'][0].startswith('RuntimeError: No Anthropic credential'))
            self.assertTrue((Path(d)/'r'/'transport-result.json').exists())

    def test_generate_uses_the_fable_transport_and_keeps_private_fields_out(self):
        case = {'marketId': '1', 'groupId': 'g', 'split': 'test', 'expectedOutcome': 'SECRET_OUTCOME', 'emailId': 'SECRET_MAIL_ID',
                'publicInput': {'marketId': '1', 'question': 'Who wins?', 'rules': 'Public rules', 'outcomeLabels': ['A', 'B']}}
        record = message(text='{"outcomeARegex":"won","outcomeBRegex":"lost","limitations":"none"}')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'k'}), \
             patch.object(fable_transport, 'make_client', return_value=fake_client(record)):
            out = experiment.generate(case, 'fixed prompt', 'high', 8000, 1, Path(d)/'one')
            self.assertEqual(out['status'], 'completed'); self.assertEqual(out['output']['outcomeARegex'], 'won')
            request = json.loads((Path(d)/'one'/'model-request.json').read_text())
            self.assertEqual(request['model'], MODEL); self.assertNotIn('SECRET_', json.dumps(request))
            self.assertEqual(json.loads((Path(d)/'one'/'transport-result.json').read_text())['model'], MODEL)

    def test_smoke_job_is_synthetic_and_valid(self):
        job = smoke_job(); body = build_request(job)
        self.assertEqual(job['input']['publicMarket']['marketId'], 'smoke-0'); self.assertEqual(body['max_tokens'], 2000)

if __name__ == '__main__':
    unittest.main()
