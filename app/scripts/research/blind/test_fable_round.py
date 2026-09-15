import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import fable_round
import fable_transport
import qwen_round1 as q
import qwen_capacity_recovery as c
import round4
from test_fable_transport import envelope, runner

def items_fixture():
    """Synthetic rows: 6 factual markets in 3 groups, controls on 4 markets, weak and unlabeled rows. No email text."""
    rows = []
    for i in range(6):
        rows.append({'caseId': f'f{i}', 'kind': 'factual', 'marketId': f'm{i}', 'expected': 'A', 'metadata': {'factKey': f'k{i%3}', 'emailId': f'e{i}', 'availableByClosure': i % 2 == 0}})
    for i in range(4):
        for j in range(3):
            rows.append({'caseId': f'c{i}{j}', 'kind': 'control', 'marketId': f'm{i}', 'expected': ['A', 'B', 'neither'][j], 'metadata': {'index': j}})
    rows.append({'caseId': 'w0', 'kind': 'weak', 'marketId': 'm7', 'expected': None, 'metadata': {'emailId': 'e9'}})
    rows.append({'caseId': 'u0', 'kind': 'unlabeled', 'marketId': 'm8', 'expected': None, 'metadata': {'emailId': 'e10'}})
    cases = [{'marketId': f'm{i}', 'groupId': f'g{i//2}'} for i in range(6)]
    return rows, cases

class ValidationSplitTests(unittest.TestCase):
    def test_split_is_deterministic_keeps_groups_together_and_respects_caps(self):
        rows, cases = items_fixture()
        target = {'factualMin': 2, 'factualMax': 3, 'controlMin': 3, 'controlMax': 6}
        a = fable_round.validation_split(rows, cases, target); b = fable_round.validation_split(rows, cases, target)
        self.assertEqual(a, b)
        self.assertLessEqual(a['validationCounts']['factual'], 3); self.assertLessEqual(a['validationCounts'].get('control', 0), 6)
        self.assertGreaterEqual(a['validationCounts']['factual'], 2)
        held = set(a['validationCaseIds'])
        for mid in a['validationMarketIds']:
            group = next((x['groupId'] for x in cases if x['marketId'] == mid), None)
            if group:
                siblings = [x['marketId'] for x in cases if x['groupId'] == group]
                self.assertTrue(all(s in a['validationMarketIds'] for s in siblings))
            self.assertTrue(all(r['caseId'] in held for r in rows if r['marketId'] == mid))
        self.assertEqual(sum(a['trainCounts'].values())+len(held), len(rows))

    def test_training_items_withholds_validation_rows_only_when_a_split_exists(self):
        rows, cases = items_fixture(); items = {r['caseId']: r for r in rows}
        with tempfile.TemporaryDirectory() as d, patch.object(q, 'ROOT', Path(d)):
            self.assertEqual(q.training_items(items), items)
            split = fable_round.validation_split(rows, cases, {'factualMin': 2, 'factualMax': 3, 'controlMin': 3, 'controlMax': 6})
            (Path(d)/'validation-split.json').write_text(json.dumps(split))
            train = q.training_items(items)
            self.assertEqual(set(train), set(items)-set(split['validationCaseIds'])); self.assertTrue(train)

class PromptReviewTests(unittest.TestCase):
    def test_review_requires_fields_and_rejects_private_identifiers(self):
        generator = 'Return factualA factualB settlementA settlementB abstainWhen limitations.'; judge = 'Return factualOutcome outcomeA outcomeB evidenceQuote missingConditions.'
        checks, ok = fable_round.review_prompts(generator, judge, {'123456', 'Secret subject line'})
        self.assertTrue(ok)
        _, ok = fable_round.review_prompts(generator+' market 123456', judge, {'123456'}); self.assertFalse(ok)
        _, ok = fable_round.review_prompts(generator.replace('abstainWhen', ''), judge, set()); self.assertFalse(ok)
        _, ok = fable_round.review_prompts(generator+' expectedOutcome lookup table', judge, set()); self.assertFalse(ok)
        _, ok = fable_round.review_prompts(generator+'x'*13000, judge, set()); self.assertFalse(ok)

class SubsetSummaryTests(unittest.TestCase):
    def test_utility_uses_subset_denominators(self):
        rows = [{'caseId': 'a', 'kind': 'factual', 'expected': 'A', 'valid': True, 'factualPass': True, 'groundedFactualPass': True, 'strictPass': None, 'falsePositive': None, 'wrongOutcome': None, 'wrongFactualOutcome': False, 'conflict': False, 'metadata': {'factKey': 'k'}},
                {'caseId': 'b', 'kind': 'control', 'expected': 'A', 'valid': True, 'factualPass': True, 'groundedFactualPass': True, 'strictPass': True, 'falsePositive': None, 'wrongOutcome': False, 'wrongFactualOutcome': False, 'conflict': False, 'metadata': {}},
                {'caseId': 'c', 'kind': 'control', 'expected': 'neither', 'valid': True, 'factualPass': True, 'groundedFactualPass': None, 'strictPass': False, 'falsePositive': True, 'wrongOutcome': None, 'wrongFactualOutcome': None, 'conflict': False, 'metadata': {}}]
        s = fable_round.subset_summary(rows)
        self.assertEqual(s['metrics']['factual']['groundedFactualPasses'], 1); self.assertEqual(s['metrics']['control']['falsePositives'], 1)
        self.assertAlmostEqual(s['utility'], 1.0+1/1-3*1/1-0)

class FableArtifactVerificationTests(unittest.TestCase):
    def test_round4_verifies_fable_artifacts_and_rejects_tampering(self):
        job = {'instructions': 'p', 'input': {'publicMarket': {'q': 1}, 'independentTrial': 1}, 'effort': 'medium', 'schema': {'type': 'object'}, 'maxBudgetUsd': 3.0}
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'MOP_CLAUDE_CODE_BIN': __file__}), patch.object(fable_transport, 'LIMIT_GATE', Path(d)/'gate.json'):
            state = fable_transport.run(job, Path(d)/'one', runner=runner(envelope({'a': 'x'})))
            out, usage, status = fable_transport.output_from(state, Path(d)/'one')
            record = {'output': out, 'usage': usage, 'status': status, 'requestSha256': round4.hash_value(job)}
            round4.save(Path(d)/'one'/'job.json', job)
            round4.verify_model_artifact(Path(d)/'one', job, record)
            with self.assertRaisesRegex(RuntimeError, 'Actual model request differs'):
                round4.verify_model_artifact(Path(d)/'one', {**job, 'effort': 'high'}, record)
            tampered = json.loads((Path(d)/'one'/'model-request.json').read_text()); tampered['system'] = 'changed'
            (Path(d)/'one'/'model-request.json').write_text(json.dumps(tampered))
            with self.assertRaisesRegex(RuntimeError, 'Actual model request differs'):
                round4.verify_model_artifact(Path(d)/'one', job, record)

    def test_capacity_recovery_recognises_only_unwaited_fable_limits(self):
        limited = envelope(None, text="You've hit your session limit · resets 1pm (America/New_York)", subtype='error_during_execution', is_error=True, models=())
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'transport-result.json').write_text(json.dumps({'provider': 'claude-code-cli', 'events': [fable_transport.event_from(limited)], 'usageLimit': {'message': 'x'}}))
            self.assertTrue(c.usage_limited(d))
            (Path(d)/'transport-result.json').write_text(json.dumps({'provider': 'claude-code-cli', 'events': [fable_transport.event_from(limited), fable_transport.event_from(envelope({'a': 1}))], 'usageLimit': {'message': 'x'}}))
            self.assertFalse(c.usage_limited(d))
            (Path(d)/'transport-result.json').write_text(json.dumps({'provider': 'claude-code-cli', 'events': [fable_transport.event_from(envelope(None, text='', subtype='error_max_budget_usd', is_error=True))]}))
            self.assertFalse(c.usage_limited(d))

class RoundRootTests(unittest.TestCase):
    def test_root_env_override_and_hosted_budgets_apply_only_to_fable_rounds(self):
        import subprocess, sys
        code = "import qwen_round1 as q, json; print(json.dumps({'root': str(q.ROOT), 'fable': q.FABLE_ROUND, 'job': q.rule_job({'marketId':'1','question':'q','rules':'r','outcomeLabels':['a','b']}, 'p')}))"
        with tempfile.TemporaryDirectory() as d:
            out = json.loads(subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env={**os.environ, 'MOP_QWEN_ROOT': d+'/fable-test'}, cwd=Path(__file__).parent).stdout)
            self.assertEqual(out['root'], d+'/fable-test'); self.assertTrue(out['fable']); self.assertEqual(out['job']['maxBudgetUsd'], 3.0); self.assertEqual(out['job']['effort'], 'medium')
            env = {k: v for k, v in os.environ.items() if k != 'MOP_QWEN_ROOT'}
            out = json.loads(subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, cwd=Path(__file__).parent).stdout)
            self.assertTrue(out['root'].endswith('astra-qwen-nyt-round1-20260912')); self.assertFalse(out['fable']); self.assertNotIn('maxBudgetUsd', out['job'])

if __name__ == '__main__':
    unittest.main()
