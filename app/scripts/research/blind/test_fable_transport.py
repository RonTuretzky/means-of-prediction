import io, json, os, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import fable_transport
from fable_transport import MODEL, build_request, output_from, run, smoke_job
import experiment

SCHEMA = {'type': 'object', 'properties': {'a': {'type': 'string'}}, 'required': ['a'], 'additionalProperties': False}
JOB = {'instructions': 'fixed', 'input': {'publicMarket': {'question': 'Q'}, 'independentTrial': 1}, 'effort': 'medium', 'schema': SCHEMA}

def envelope(output=None, text=None, subtype='success', is_error=False, stop='tool_use', models=('claude-haiku-4-5-20251001', MODEL)):
    return {'type': 'result', 'subtype': subtype, 'is_error': is_error, 'stop_reason': stop, 'session_id': 'sess-1', 'total_cost_usd': 0.03,
            'usage': {'input_tokens': 2, 'cache_creation_input_tokens': 1000, 'cache_read_input_tokens': 0, 'output_tokens': 150},
            'modelUsage': {m: {'inputTokens': 1} for m in models},
            'structured_output': output, 'result': text if text is not None else (json.dumps(output) if output is not None else ''), 'num_turns': 1}

class FakeProcess:
    """Stands in for subprocess.Popen; records the argv and stdin it received."""
    calls = []
    def __init__(self, argv, stdin=None, stdout=None, stderr=None, text=None, cwd=None, env=None, exit_code=0, out=''):
        self.argv, self.cwd, self.env, self.pid, self.returncode = argv, cwd, env, os.getpid(), exit_code
        self.out = out; FakeProcess.calls.append(self)
    def communicate(self, input=None, timeout=None):
        self.stdin_text = input; return self.out, ''
    def kill(self): pass

def runner(result, exit_code=0):
    out = json.dumps(result) if isinstance(result, dict) else result
    return lambda argv, **kw: FakeProcess(argv, exit_code=exit_code, out=out, **kw)

class BuildRequestTests(unittest.TestCase):
    def test_request_is_tool_free_and_carries_only_the_audited_job(self):
        request = build_request({**JOB, 'tools': [{'type': 'shell'}], 'messages': [{'content': 'PRIVATE_TARGET_EMAIL'}], 'temperature': 0, 'thinking': {'type': 'disabled'}})
        self.assertEqual(request['model'], 'claude-fable-5-1'); self.assertEqual(request['tools'], []); self.assertEqual(request['maxTurns'], 1)
        for forbidden in ['temperature', 'thinking', 'messages', 'fallbacks']:
            self.assertNotIn(forbidden, request)
        self.assertNotIn('PRIVATE_TARGET_EMAIL', json.dumps(request))
        self.assertEqual(request['system'], 'fixed'); self.assertEqual(json.loads(request['input']), JOB['input'])
        args = request['argv']
        self.assertEqual(args[:1], ['-p']); self.assertNotIn('--bare', args); self.assertNotIn('--allowedTools', args)
        for flag, value in [('--model', MODEL), ('--effort', 'medium'), ('--tools', ''), ('--max-turns', '1'), ('--setting-sources', ''), ('--output-format', 'json')]:
            self.assertEqual(args[args.index(flag)+1], value)
        for flag in ['--no-session-persistence', '--strict-mcp-config', '--disable-slash-commands', '--system-prompt', '--json-schema', '--max-budget-usd']:
            self.assertIn(flag, args)
        self.assertEqual(json.loads(args[args.index('--json-schema')+1]), SCHEMA)

    def test_effort_validation_budget_and_guidance(self):
        with self.assertRaises(ValueError): build_request({**JOB, 'effort': 'ultra'})
        self.assertEqual(build_request({k: v for k, v in JOB.items() if k != 'effort'})['effort'], 'high')
        request = build_request({**JOB, 'maxOutputTokens': 8000, 'maxBudgetUsd': 2.5})
        self.assertEqual(request['maxOutputTokensGuidance'], 8000); self.assertEqual(request['argv'][request['argv'].index('--max-budget-usd')+1], '2.5')

    def test_request_is_deterministic_for_hashing(self):
        self.assertEqual(json.dumps(build_request(JOB)), json.dumps(build_request(json.loads(json.dumps(JOB)))))

class OutputFromTests(unittest.TestCase):
    def wrap(self, env): return {'provider': fable_transport.PROVIDER, 'events': [fable_transport.event_from(env)]}

    def test_completed_result_returns_structured_output(self):
        out, usage, status = output_from(self.wrap(envelope({'a': 'x'})))
        self.assertEqual(out, {'a': 'x'}); self.assertEqual(usage['output_tokens'], 150); self.assertEqual(status, 'completed')

    def test_errors_refusals_and_mismatches_never_count_as_success(self):
        self.assertEqual(output_from(self.wrap(envelope(None, text='', subtype='error_max_budget_usd', is_error=True)))[2], 'error_max_budget_usd')
        self.assertEqual(output_from(self.wrap(envelope(None, text='', subtype='error_max_turns', is_error=True)))[2], 'error_max_turns')
        self.assertEqual(output_from(self.wrap(envelope(None, text='', stop='refusal')))[2], 'refusal')
        self.assertEqual(output_from(self.wrap(envelope({'a': 'x'}, models=('claude-haiku-4-5-20251001', 'claude-opus-4-8'))))[2], 'model_mismatch')
        self.assertEqual(output_from(self.wrap(envelope({'a': 'x'}, models=('claude-haiku-4-5-20251001', MODEL, 'claude-opus-4-8'))))[2], 'model_mismatch')
        self.assertEqual(output_from(self.wrap(envelope(None, text='not json')))[2], 'invalid_json')
        self.assertEqual(output_from({'provider': fable_transport.PROVIDER, 'events': []}), (None, {}, 'transport_failed'))

    def test_experiment_dispatches_by_provider_and_keeps_legacy_shape(self):
        self.assertEqual(experiment.output_from(self.wrap(envelope({'a': 'x'})))[0], {'a': 'x'})
        legacy = {'events': [{'response': {'model': 'gpt-6-astra', 'status': 'completed', 'usage': {},
                  'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"a":"legacy"}'}]}]}}]}
        self.assertEqual(experiment.output_from(legacy)[0], {'a': 'legacy'})

class RunTests(unittest.TestCase):
    def setUp(self):
        FakeProcess.calls = []
        self.patches = [patch.dict(os.environ, {'MOP_CLAUDE_CODE_BIN': __file__, 'CLAUDECODE': '1', 'CLAUDE_CODE_SESSION_ID': 'parent'})]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()

    def test_run_records_request_isolation_output_and_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            state = run(JOB, Path(d)/'one', runner=runner(envelope({'a': 'x'})))
            files = sorted(p.name for p in (Path(d)/'one').iterdir())
            self.assertEqual(files, ['client-output.json', 'client-stderr.log', 'model-request.json', 'output.txt', 'process.json', 'transport-checkpoint.json', 'transport-result.json'])
            self.assertEqual(json.loads((Path(d)/'one'/'model-request.json').read_text()), build_request(JOB))
            call = FakeProcess.calls[0]
            self.assertEqual(call.argv[0], __file__); self.assertEqual(call.argv[1:], build_request(JOB)['argv'])
            self.assertEqual(call.stdin_text, json.dumps(JOB['input'], ensure_ascii=False))
            self.assertTrue(call.cwd.startswith(tempfile.gettempdir())); self.assertNotEqual(call.cwd, os.getcwd())
            self.assertNotIn('CLAUDECODE', call.env); self.assertNotIn('CLAUDE_CODE_SESSION_ID', call.env); self.assertIn('HOME', call.env)
            self.assertEqual(state['requests'][0]['exitCode'], 0); self.assertEqual(state['requests'][0]['status'], 'ok')
            self.assertEqual(state['requests'][0]['sessionId'], 'sess-1'); self.assertEqual(len(state['requests'][0]['requestSha256']), 64)
            self.assertEqual(state['events'][0]['model'], MODEL); self.assertEqual(state['costUsd'], 0.03)
            self.assertEqual(json.loads((Path(d)/'one'/'process.json').read_text())['pid'], os.getpid())
            self.assertEqual(experiment.output_from(json.loads((Path(d)/'one'/'transport-result.json').read_text()), Path(d)/'one')[0], {'a': 'x'})

    def test_error_envelope_is_retained_as_receipt_without_retry(self):
        with tempfile.TemporaryDirectory() as d:
            state = run(JOB, d, runner=runner(envelope(None, text='Budget exceeded', subtype='error_max_budget_usd', is_error=True), exit_code=1))
            self.assertEqual(len(FakeProcess.calls), 1)
            self.assertEqual(state['requests'][0]['status'], 'error'); self.assertEqual(state['subtype'], 'error_max_budget_usd')
            self.assertIn('error_max_budget_usd', state['serviceErrors'][0])
            self.assertEqual(experiment.output_from(state)[2], 'error_max_budget_usd')

    def test_unparseable_client_output_and_missing_executable_are_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            state = run(JOB, Path(d)/'a', runner=runner('Not logged in', exit_code=1))
            self.assertEqual(state['transportErrors'], ['UnparseableClientOutput']); self.assertEqual(state['events'], [])
            self.assertEqual(experiment.output_from(state)[2], 'transport_failed')
            with patch.dict(os.environ, {'MOP_CLAUDE_CODE_BIN': '/nonexistent/claude', 'CLAUDE_CODE_EXECPATH': '/nonexistent/claude'}), patch('shutil.which', return_value=None):
                state = run(JOB, Path(d)/'b')
            self.assertTrue(state['transportErrors'][0].startswith('RuntimeError: No Claude Code executable'))
            self.assertTrue((Path(d)/'b'/'transport-result.json').exists())

    def test_generate_uses_the_fable_transport_and_keeps_private_fields_out(self):
        case = {'marketId': '1', 'groupId': 'g', 'split': 'test', 'expectedOutcome': 'SECRET_OUTCOME', 'emailId': 'SECRET_MAIL_ID',
                'publicInput': {'marketId': '1', 'question': 'Who wins?', 'rules': 'Public rules', 'outcomeLabels': ['A', 'B']}}
        output = {'outcomeARegex': 'won', 'outcomeBRegex': 'lost', 'limitations': 'none'}
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', runner(envelope(output))):
            out = experiment.generate(case, 'fixed prompt', 'high', 8000, 1, Path(d)/'one')
            self.assertEqual(out['status'], 'completed'); self.assertEqual(out['output']['outcomeARegex'], 'won')
            request = json.loads((Path(d)/'one'/'model-request.json').read_text())
            self.assertEqual(request['model'], MODEL); self.assertNotIn('SECRET_', json.dumps(request)); self.assertNotIn('SECRET_', FakeProcess.calls[0].stdin_text)
            self.assertEqual(json.loads((Path(d)/'one'/'transport-result.json').read_text())['model'], MODEL)

    def test_smoke_job_is_synthetic_and_capped(self):
        job = smoke_job(); request = build_request(job)
        self.assertEqual(job['input']['publicMarket']['marketId'], 'smoke-0'); self.assertEqual(request['maxBudgetUsd'], 1.0)

if __name__ == '__main__':
    unittest.main()
