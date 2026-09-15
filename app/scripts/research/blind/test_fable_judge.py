import json, unittest
import fable_judge
import qwen_round1 as q
from test_fable_round import items_fixture

RULE = {k: 'x' for k in q.RULE_SCHEMA['properties']}

class FableJudgeTests(unittest.TestCase):
    def test_subset_is_deterministic_and_keeps_all_factual_and_weak(self):
        rows, _ = items_fixture()
        a, b = fable_judge.subset(rows), fable_judge.subset(rows)
        self.assertEqual(a, b)
        self.assertTrue(all(r['caseId'] in a for r in rows if r['kind'] in ('factual', 'weak')))
        self.assertLessEqual(sum(r['kind'] == 'control' for r in rows if r['caseId'] in a), sum(r['kind'] == 'control' for r in rows))

    def test_judge_job_is_blind_and_matches_the_local_judge_content(self):
        email = {'subject': 's', 'domain': 'nytimes.com', 'signedDate': 'd', 'receivedAt': 'r', 'html': '<p>Body text</p>', 'semanticText': 'Body text'}
        job = fable_judge.judge_job(RULE, email, 'judge prompt', 'medium')
        self.assertEqual(set(job['input']), {'email', 'rule'}); self.assertEqual(job['schema'], q.JUDGE_SCHEMA); self.assertEqual(job['instructions'], 'judge prompt')
        self.assertEqual(job['input']['email'], q.email_packet(email)); self.assertNotIn('expected', json.dumps(job)); self.assertEqual(job['maxBudgetUsd'], fable_judge.JUDGE_BUDGET_USD)
        with self.assertRaises(ValueError): fable_judge.judge_job({'factualA': 'only'}, email, 'p', 'low')

    def test_summarize_reports_statuses_cost_and_metrics(self):
        item = {'caseId': 'f0', 'kind': 'factual', 'marketId': 'm0', 'expected': 'A', 'metadata': {'factKey': 'k', 'emailId': 'e', 'availableByClosure': True}, 'email': {'subject': 's', 'dkimDomain': 'd', 'signedDate': '', 'receivedAt': '', 'completeSemanticText': 'won', 'representation': 'v'}}
        out = {'factualOutcome': 'A', 'outcomeA': 'YES', 'outcomeB': 'NO', 'evidenceQuote': 'won', 'missingConditions': []}
        rec = {'caseId': 'f0', 'marketId': 'm0', 'trial': 1, 'kind': 'factual', 'status': 'completed', 'output': out, 'seconds': 12.0, 'costUsd': 0.2, 'limitWaits': 0}
        scores = [q.score_record(item, rec)]
        s = fable_judge.summarize([rec], scores, {'method': 'baseline', 'judge': 'fable', 'effort': 'medium'})
        self.assertEqual(s['metrics']['factual']['groundedFactualPasses'], 1); self.assertEqual(s['statuses'], {'completed': 1}); self.assertEqual(s['listCostUsd'], 0.2)

if __name__ == '__main__':
    unittest.main()
