import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import qwen_round1 as q

class BlindQwenTests(unittest.TestCase):
    def output(self,**kw):return dict({'factualOutcome':'A','outcomeA':'YES','outcomeB':'NO','evidenceQuote':'won','missingConditions':[]},**kw)
    def test_no_is_not_opposite(self):
        self.assertEqual(q.settlement(self.output(outcomeA='NO')),'NEITHER')
        self.assertEqual(q.settlement(self.output(outcomeB='YES')),'CONFLICT')
    def test_malformed_output_is_unscorable(self):
        self.assertFalse(q.valid_judgment(self.output(missingConditions=[1])))
        self.assertFalse(q.valid_judgment({'factualOutcome':'A'}))
        self.assertEqual(q.settlement(self.output(outcomeA='maybe')),'UNSCORABLE')
    def test_entire_email_without_labels(self):
        email={'html':'<p>'+('x'*160000)+'</p>','subject':'Subject','expectedOutcome':'A','payout':'Yes','domain':'example.org'}
        rule={k:k for k in q.RULE_SCHEMA['properties']}
        request=q.judge_request(rule,email,'instructions',{'identifier':'local-qwen'})
        self.assertEqual(len(request['messages']),2)
        packet=json.loads(request['messages'][1]['content'])
        self.assertEqual(packet['email']['completeSemanticText'],'x'*160000)
        self.assertNotIn('completeDecodedHtml',packet['email'])
        self.assertNotIn('expectedOutcome',request['messages'][1]['content'])
        self.assertNotIn('payout',request['messages'][1]['content'])
        self.assertNotIn('tools',request)
    def test_generator_rejects_nonpublic_fields(self):
        with self.assertRaises(ValueError):q.rule_job({'marketId':'1','expectedOutcome':'A'},'x')
    def test_unscorable_never_safe_rejection(self):
        item={'caseId':'x','marketId':'1','kind':'control','expected':'neither','metadata':{},'email':{'completeDecodedHtml':'won'}}
        row=q.score_record(item,{'status':'failed','output':self.output(outcomeA='NO'),'trial':1})
        self.assertFalse(row['strictPass']);self.assertFalse(row['valid']);self.assertEqual(row['settlementOutcome'],'UNSCORABLE')
    def test_positive_second_label_requires_affirmative_second_predicate(self):
        item={'caseId':'x','marketId':'1','kind':'control','expected':'B','metadata':{},'email':{'completeSemanticText':'under'}}
        correct=q.score_record(item,{'status':'completed','trial':1,'output':self.output(factualOutcome='B',outcomeA='NO',outcomeB='YES',evidenceQuote='under')})
        wrong=q.score_record(item,{'status':'completed','trial':1,'output':self.output(evidenceQuote='under')})
        self.assertTrue(correct['strictPass']);self.assertTrue(correct['groundedFactualPass']);self.assertFalse(correct['wrongOutcome'])
        self.assertFalse(wrong['strictPass']);self.assertTrue(wrong['wrongOutcome'])
    def test_wrong_side_and_quote_are_separate(self):
        item={'caseId':'x','marketId':'1','kind':'factual','expected':'A','metadata':{},'email':{'completeDecodedHtml':'lost'}}
        row=q.score_record(item,{'status':'completed','output':self.output(outcomeA='NO',outcomeB='YES'),'trial':1})
        self.assertTrue(row['factualPass']);self.assertFalse(row['groundedFactualPass']);self.assertIsNone(row['wrongOutcome']);self.assertIsNone(row['strictPass'])
    def test_unlabeled_is_not_negative(self):
        item={'caseId':'x','marketId':'1','kind':'unlabeled','expected':None,'metadata':{},'email':{'completeDecodedHtml':'won'}}
        row=q.score_record(item,{'status':'completed','output':self.output(),'trial':1})
        self.assertIsNone(row['falsePositive']);self.assertIsNone(row['strictPass'])
    def test_local_transport_failure_is_cached_not_retried(self):
        request={'model':'local-qwen','messages':[]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(q.http.client,'HTTPConnection') as conn:
                conn.return_value.request.side_effect=ConnectionError('offline')
                first=q.local_call(request,directory);second=q.local_call(request,directory)
                self.assertEqual(first['status'],'transport_failed');self.assertEqual(first,second)
                self.assertEqual(conn.call_count,1)
            with self.assertRaises(RuntimeError):q.local_call(dict(request,model='other'),directory)
    def test_uncertain_inference_never_restarted(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'started.json').write_text('{}')
            with patch.object(q.http.client,'HTTPConnection') as conn:
                with self.assertRaises(RuntimeError):q.local_call({'model':'local'},directory)
                conn.assert_not_called()
    def test_nonjson_http_response_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(q.http.client,'HTTPConnection') as conn:
                response=conn.return_value.getresponse.return_value;response.read.return_value=b'HTTP upstream failed';response.status=500
                result=q.local_call({'model':'local'},directory)
            self.assertEqual(result['status'],'transport_failed')
            self.assertEqual(Path(directory,'response.raw').read_bytes(),b'HTTP upstream failed')
            self.assertTrue(result['rawResponseSha256'])
    def test_feedback_covers_full_html_and_every_finalized_case(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(q,'ROOT',Path(directory)):
            q.ROOT.mkdir(exist_ok=True)
            raw=[];items=[]
            for i in range(3):
                email={'html':f'<p>Complete claim {i}. Footer retained.</p>'}
                base={'caseId':str(i),'marketId':str(i),'kind':'control','expected':'A','metadata':{}}
                raw.append({**base,'email':q.raw_email_packet(email)})
                items.append({**base,'email':q.email_packet(email)})
            q.once('development-items.private.json',raw);q.once(q.ITEMS,items)
            q.once('public-inputs.json',[{'marketId':str(i),'question':'q','rules':'r','outcomeLabels':['Yes','No']} for i in range(3)])
            rule={k:'rule' for k in q.RULE_SCHEMA['properties']}
            q.once('methods/baseline/rules.json',[{'marketId':str(i),'status':'completed' if i<2 else 'transport_failed','output':rule if i<2 else None} for i in range(3)])
            q.once('methods/baseline/development-summary.json',{})
            for i in range(2):q.once(f'methods/baseline/development/{i}/1/result.json',{'status':'completed','output':self.output(evidenceQuote=f'Complete claim {i}.'),'seconds':1})
            calls=[]
            def teacher(job,path):calls.append(job);return {'status':'completed','output':{}}
            with patch.object(q,'teacher_call',side_effect=teacher):q.distill('baseline',workers=1)
            groups=[g for job in calls for g in job['input']['groups']]
            cases=[c for g in groups for c in g['cases']]
            self.assertEqual({c['item']['caseId'] for c in cases},{'0','1','2'})
            self.assertEqual(len(cases),3)
            self.assertTrue(all('Footer retained.' in g['originalCompleteHtml'] for g in groups))
            missing=next(c for c in cases if c['item']['caseId']=='2')
            self.assertEqual(missing['rawJudgment']['status'],'rule_unavailable');self.assertFalse(missing['score']['valid'])
    def test_feedback_partition_keeps_complete_body_and_each_case_once(self):
        group={'email':{'completeSemanticText':'full semantic body'},'originalCompleteHtml':'<p>Full body and footer</p>',
            'cases':[{'item':{'caseId':str(i)},'result':'x'*100} for i in range(6)]}
        parts=q.feedback_fragments(group,limit=500)
        self.assertGreater(len(parts),1)
        self.assertEqual([c for p in parts for c in p['cases']],group['cases'])
        for part in parts:
            self.assertEqual(part['email'],group['email']);self.assertEqual(part['originalCompleteHtml'],group['originalCompleteHtml'])
            self.assertLessEqual(len(json.dumps(part,ensure_ascii=False)),500)
        self.assertEqual(q.feedback_fragments(group,limit=500),parts)
        self.assertIs(q.feedback_fragments(group,limit=10000)[0],group)
    def test_feedback_partition_fails_when_single_complete_email_case_cannot_fit(self):
        with self.assertRaisesRegex(RuntimeError,'no evidence truncated'):
            q.feedback_fragments({'email':{'completeSemanticText':'x'*500},'cases':[{'item':{'caseId':'1'}}]},limit=400)
    def test_feedback_fragment_lineage_reuses_only_identical_artifacts(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(q,'ROOT',Path(directory)):
            q.save_feedback_fragment_lineage('lineage.json',{'cases':['1','2']})
            before=(q.ROOT/'lineage.json').read_bytes()
            q.save_feedback_fragment_lineage('lineage.json',{'cases':['1','2']})
            self.assertEqual((q.ROOT/'lineage.json').read_bytes(),before)
            with self.assertRaises(RuntimeError):q.save_feedback_fragment_lineage('lineage.json',{'cases':['2','1']})
    def test_fresh_preflight_keeps_draws_distinct_and_labels_out(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(q,'ROOT',Path(directory)):
            q.once('runtime.json',{'identifier':'local'})
            (q.ROOT/'baseline-judge.txt').write_text('Judge supplied evidence only.')
            rule={k:'rule' for k in q.RULE_SCHEMA['properties']}
            q.once('methods/baseline/challenge-rules.json',[{'marketId':'m','trial':i,'status':'completed','output':rule} for i in [1,2]])
            q.once('challenge-items.private.json',[{'caseId':'c','marketId':'m','kind':'control','expected':'B','metadata':{'secretScorerNote':'do not send'},'email':q.email_packet({'html':'<p>Full evidence.</p>'})}])
            with patch.object(q,'verify_challenge_freeze',return_value={'methods':['baseline']}):q.prepare_preflight('baseline','challenge')
            rows=q.load('methods/baseline/challenge-semantic-preflight-requests.private.json')['requests']
            self.assertEqual({x['caseId'] for x in rows},{'c/1','c/2'})
            for row in rows:
                text=json.dumps(row['request']);self.assertNotIn('secretScorerNote',text);self.assertNotIn('expected',text)
                self.assertIn('Full evidence.',text)
    def test_fresh_inference_checks_freeze_before_reading_cases(self):
        with patch.object(q,'verify_challenge_freeze',side_effect=RuntimeError('freeze altered')):
            with patch.object(q,'load') as load:
                with self.assertRaises(RuntimeError):q.judge_items('baseline',phase='challenge')
                load.assert_not_called()
    def test_fresh_study_includes_selected_winner_over_ineligible_high_utility(self):
        summaries={'baseline':{'utility':1},'v1':{'utility':2},'v2':{'utility':3}}
        comparisons={m:{'pairedStrictImprovement':True} for m in ['v1','v2']}
        with patch.object(q,'eligible',side_effect=lambda candidate,baseline:candidate is summaries['v1']):
            self.assertEqual(q.selection_methods(summaries,comparisons),('v1','v1'))
        with patch.object(q,'eligible',return_value=False):
            self.assertEqual(q.selection_methods(summaries,comparisons),('baseline','v2'))

if __name__=='__main__':unittest.main()
