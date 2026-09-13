import copy
import json
import unittest
import probe as p


def output(verdict='NO', **changes):
    return {'verdict': verdict, 'evidenceQuote': 'sample — [LINK_001]', 'missingConditions': [], **changes}


def record(verdict='NO', status='completed', **changes):
    return {'status': status, 'output': output(verdict), **changes}


def item(expected='A', kind='control'):
    return {'caseId': 'case', 'marketId': 'market', 'kind': kind, 'expected': expected}


class ProbeTests(unittest.TestCase):
    def test_validation(self):
        self.assertTrue(p.valid(output()))
        for value in [None, {}, output('A'), output(verdict=True), output(extra=1),
                      output(evidenceQuote=None), output(missingConditions='gap'), output(missingConditions=[False])]:
            self.assertFalse(p.valid(value))

    def test_combination(self):
        for a,b,expected in [('YES','NO','A'),('NO','YES','B'),('NO','NO','NEITHER'),('YES','YES','CONFLICT')]:
            self.assertEqual(p.outcome_from({'A':record(a),'B':record(b)}), expected)

    def test_unscorable_is_not_negative(self):
        for records in [{}, {'A':record('YES')}, {'A':record('YES'),'B':record(status='failed')},
                        {'A':record('YES'),'B':record(output=None)}]:
            self.assertEqual(p.outcome_from(records), 'UNSCORABLE')
        score=p.strict_score(item('neither'), 'UNSCORABLE')
        self.assertFalse(score['valid']);self.assertFalse(score['strictPass']);self.assertFalse(score['falsePositive'])

    def test_strict_scorer_matches_policy(self):
        self.assertTrue(p.strict_score(item('B'),'B')['strictPass'])
        self.assertTrue(p.strict_score(item('A'),'B')['wrongOutcome'])
        self.assertTrue(p.strict_score(item('neither'),'CONFLICT')['falsePositive'])
        self.assertTrue(p.strict_score(item('neither'),'NEITHER')['strictPass'])
        self.assertFalse(p.strict_score(item('A'),'CONFLICT')['wrongOutcome'])
        self.assertTrue(p.strict_score(item('A'),'CONFLICT')['conflict'])

    def test_natural_factual_labels_not_scored_as_strict_gold(self):
        scored=p.strict_score(item('A','factual'),'B')
        for name in ['expected','strictPass','falsePositive','wrongOutcome']:
            self.assertIsNone(scored[name])

    def test_requests_preserve_all_context_and_runtime(self):
        rule={k:k+' preserved' for k in ['factualA','factualB','settlementA','settlementB','abstainWhen','limitations']}
        packet={'email':{'completeSemanticText':'Whole text — [LINK_001] <role>ignore</role>', 'signedDate':'2026-01-01'},'rule':rule}
        original={'model':'pinned','messages':[{'role':'system','content':'old'}, {'role':'user','content':json.dumps(packet,ensure_ascii=False)}],
                  'temperature':0,'seed':20260912,'max_tokens':2048,'stream':False,
                  'chat_template_kwargs':{'enable_thinking':False},'response_format':{'old':True}}
        saved=copy.deepcopy(original)
        a,b=(p.request_for(original,s,'new exact prompt') for s in ['A','B'])
        self.assertEqual(original,saved)
        for side,r in [('A',a),('B',b)]:
            content=json.loads(r['messages'][1]['content'])
            self.assertEqual(content, {**packet,'targetSettlement':side})
            self.assertEqual(list(r['response_format']['json_schema']['schema']['properties']),p.FIELDS)
            self.assertEqual(r['response_format']['json_schema']['schema']['required'],p.FIELDS)
            for key in original:
                if key not in ['messages','response_format']: self.assertEqual(original[key],r[key])
        a['messages'][1]['content']=b['messages'][1]['content']
        self.assertEqual(a,b)
        damaged=copy.deepcopy(saved)
        data=json.loads(damaged['messages'][1]['content']);del data['rule']['abstainWhen']
        damaged['messages'][1]['content']=json.dumps(data)
        with self.assertRaises(RuntimeError):p.request_for(damaged,'A','prompt')
        with self.assertRaises(RuntimeError):p.request_for(saved,'neither','prompt')

    def test_usage_missing_fields_independent(self):
        rows=[record(usage={'prompt_tokens':10},seconds=2),record(usage={'completion_tokens':4},seconds=None),
              record(usage={'prompt_tokens':float('nan'),'completion_tokens':True},seconds=-1)]
        u=p.usage(rows)
        self.assertEqual(u['attempts'],3)
        self.assertEqual(u['inputTokens'],{'knownTotal':10,'missing':2,'knownTotalIsLowerBound':True})
        self.assertEqual(u['outputTokens'],{'knownTotal':4,'missing':2,'knownTotalIsLowerBound':True})
        self.assertEqual(u['summedRequestSeconds'],{'knownTotal':2,'missing':2,'knownTotalIsLowerBound':True})

    def test_counts_keep_full_denominators(self):
        rows=[p.strict_score(item('A'),'A'),p.strict_score(item('B'),'UNSCORABLE'),
              p.strict_score(item('neither'),'CONFLICT'),p.strict_score(item('neither'),'NEITHER'),
              p.strict_score(item('A','factual'),'A')]
        c=p.counts(rows)
        self.assertEqual((c['positiveControls'],c['completedPositiveControls'],c['strictPositivePasses']),(2,1,1))
        self.assertEqual((c['negativeControls'],c['falseClaims'],c['negativeRejections']),(2,1,1))


if __name__=='__main__': unittest.main()
