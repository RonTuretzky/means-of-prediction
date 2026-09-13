import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import round4

class FullDataIsolationTests(unittest.TestCase):
    def test_fresh_fixture_inventory_cannot_silently_shrink(self):
        fixture=dict(name='example',html='fictional example',expected='neither')
        public={'one':{},'two':{}};seal=dict(markets=2,fixtures=2)
        round4.validate_test_fixtures({'one':[fixture],'two':[fixture]},public,seal)
        with self.assertRaisesRegex(RuntimeError,'omit or add'):
            round4.validate_test_fixtures({'one':[fixture]},public,seal)
        with self.assertRaisesRegex(RuntimeError,'counts differ'):
            round4.validate_test_fixtures({'one':[fixture],'two':[]},public,seal)

    def test_fresh_fixture_invalid_labels_are_not_safe_negatives(self):
        with self.assertRaisesRegex(RuntimeError,'Invalid independent fixture'):
            round4.validate_test_fixtures({'one':[dict(name='example',html='fictional example',expected=None)]},{'one':{}},dict(markets=1,fixtures=1))

    def test_generator_job_rejects_private_fields(self):
        p={'marketId':'1','question':'q','rules':'r','outcomeLabels':['Yes','No'],'email':'secret'}
        with self.assertRaises(ValueError):round4.job_for(p,'prompt')

    def test_cannot_read_fixtures_before_freezing_all_outputs(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text(json.dumps({'artifactHashes':{},'sourceHashes':{}}))
            with patch.object(round4,'score_controls') as score:
                with self.assertRaises(FileNotFoundError):round4.score_test(Path(d)/'private-fixtures.json')
                score.assert_not_called()

    def test_optimization_cannot_continue_after_selection(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text('{}')
            with patch.object(round4,'safe_call') as model:
                with self.assertRaisesRegex(RuntimeError,'Training closed'):round4.optimize('new','old')
                model.assert_not_called()

    def test_cached_request_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'job.json').write_text(json.dumps({'input':'original'}))
            with patch.object(round4,'invoke') as model:
                with self.assertRaisesRegex(RuntimeError,'request changed'):round4.safe_call({'input':'different'},d)
                model.assert_not_called()

    def test_more_recall_does_not_hide_more_false_positives(self):
        b=dict(factualHits=30,positivePasses=20,negativeFalsePositives=2,invalidPairs=1,wrongOutcomeOrConflict=0)
        self.assertFalse(round4.eligible(dict(b,factualHits=50,negativeFalsePositives=3),b))
        self.assertTrue(round4.eligible(dict(b,factualHits=31),b))
        self.assertFalse(round4.eligible(b,b))

    def test_supplemental_gate_does_not_hide_unscorable_controls(self):
        b=dict(positivePasses=20,negativeFalsePositives=2,unscorablePositives=0,unscorableNegatives=0)
        self.assertFalse(round4.gap_eligible(dict(b,positivePasses=30,unscorableNegatives=6),b))
        self.assertFalse(round4.gap_eligible(dict(b,positivePasses=19),b))
        self.assertTrue(round4.gap_eligible(dict(b,positivePasses=21),b))

    def test_new_control_merge_cannot_replace_previous_fixtures(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)):
            path=Path(d)
            for name,value in [('controls.json',{'1':[{'html':'original'}]}),('gap-controls.private.json',{'1':[{'html':'replacement'}]})]:
                (path/name).write_text(json.dumps(value))
            (path/'gap-control-seal.json').write_text(json.dumps({'sha256':round4.digest(path/'gap-controls.private.json')}))
            with self.assertRaisesRegex(RuntimeError,'overlap'):round4.all_development_controls()

    def test_availability_recovery_is_not_semantic_improvement(self):
        good=dict(marketId='one',status='completed',validPair=True,factualScore={'status':'hit'},controls=[])
        failed=dict(good,marketId='two',status='transport_failed',validPair=False,factualScore={'status':'unscorable'})
        result=round4.common_completed_comparison([good,dict(good,marketId='two')],[good,failed],[],[])
        self.assertEqual(result['markets'],['one']);self.assertFalse(result['eligible'])

    def test_common_completed_gate_includes_new_controls(self):
        row=dict(marketId='one',status='completed',validPair=True,factualScore={'status':'miss'},controls=[])
        fixed=dict(row,factualScore={'status':'hit'})
        control=dict(expected='neither',passed=True,falsePositive=False,scorable=True)
        b=[dict(marketId='one',controls=[control])]
        c=[dict(marketId='one',controls=[dict(control,passed=False,falsePositive=True)])]
        self.assertFalse(round4.common_completed_comparison([fixed],[row],c,b)['eligible'])
        self.assertTrue(round4.common_completed_comparison([fixed],[row],b,b)['eligible'])

    def test_teacher_recovery_preserves_failed_attempt_and_selects_first_completion(self):
        job={'input':'all data'};calls=[]
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)),patch('builtins.print'):
            root=Path(d)/'teacher'
            def call(job,directory):
                calls.append(directory);directory.mkdir(parents=True,exist_ok=True)
                parsed={'status':'transport_failed' if len(calls)==1 else 'completed','output':None if len(calls)==1 else {'lessons':['ok']},'requestSha256':round4.hash_value(job)}
                (directory/'parsed.json').write_text(json.dumps(parsed));(directory/'job.json').write_text(json.dumps(job));return parsed
            with patch.object(round4,'safe_call',side_effect=call):
                result=round4.complete_teacher_call(job,root)
                self.assertEqual(result['status'],'completed');self.assertEqual(len(calls),2)
                self.assertEqual(json.loads((root/'parsed.json').read_text())['status'],'transport_failed')
                self.assertEqual(round4.complete_teacher_call(job,root),result);self.assertEqual(len(calls),2)

    def test_failed_teacher_record_cannot_be_used_as_null_lesson(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'parsed.json').write_text(json.dumps({'status':'transport_failed','output':None}))
            with self.assertRaisesRegex(RuntimeError,'did not complete'):round4.selected_teacher_record(d)

    def test_complete_feedback_includes_added_candidates_and_all_controls(self):
        main=[dict(marketId=str(i),question='q',rules='r',outcomeLabels=['Yes','No']) for i in range(189)]
        extra=[dict(marketId='e'+str(i),question='q',rules='r',outcomeLabels=['Yes','No']) for i in range(49)]
        follow=[dict(marketId='f'+str(i),question='q',rules='r',outcomeLabels=['Yes','No']) for i in range(3)]
        cs=[dict(name='one',kind='negative',html='merely mentioned',expected='neither')]
        output=dict(outcomeARegex='won',outcomeBRegex='lost')
        rows=[dict(marketId=p['marketId'],output=output,factualScore=None,controls=round4.score_controls(output,cs) if p['marketId']=='0' else [],syntaxRepair=None,nativeValidation=[]) for p in main]
        captured=[]
        def model(job,directory):
            captured.append(job['input']);return {'output':dict(lessons=[],usefulGrammar=[],safetyFailures=[],gasReductions=[],dataQualityLimits=[]),'status':'completed'}
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)),patch.object(round4,'complete_teacher_call',side_effect=model),patch('builtins.print'):
            path=Path(d)
            values={'development-public.json':main,'expansion-public.json':extra,'followup-public.json':follow,'controls.json':{'0':cs},'all-factual-evidence.private.json':[],
                'methods/m/gap-control-scores.private.json':[],'methods/m/gap-control-summary.json':{}}
            for cohort,pub in [('expansion',extra),('followup',follow)]:
                values['methods/m/'+cohort+'-generations.json']=[dict(marketId=p['marketId'],output=output,status='completed') for p in pub]
                values['methods/m/'+cohort+'-retrieval.private.json']=[];values['methods/m/'+cohort+'-summary.json']={}
            for name,value in values.items():
                target=path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(value))
            methods={'m':dict(summary={},rows=rows,nativeSummary={})};round4.distill_complete_feedback(methods)
            seen=[r['marketId'] for p in captured for r in p['rows']]
            self.assertEqual(len(seen),241);self.assertEqual(len(set(seen)),241)
            self.assertEqual(sum(len(c) for p in captured for c in p['controls'].values()),1)
            self.assertEqual(methods['m']['feedbackNamespace'],'feedback-learning-complete')

    def test_modified_candidate_cannot_pass_raw_output_audit(self):
        public=dict(marketId='1',question='q',rules='r',outcomeLabels=['Yes','No'])
        job=round4.job_for(public,'prompt')
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            for name,value in [('job.json',job),('model-request.json',round4.build_request(job)),('transport-result.json',{'events':[]})]:
                (path/name).write_text(json.dumps(value))
            with self.assertRaisesRegex(RuntimeError,'Candidate differs'):
                round4.verify_model_artifact(path,job,dict(output={'outcomeARegex':'won'},usage={},status='completed'))

    def test_new_email_match_is_not_scored_as_a_labeled_fact_hit(self):
        public=dict(marketId='1',question='Who wins?',rules='Official winner.',outcomeLabels=['Yes','No'])
        case=dict(marketId='1',publicInput=public,emailId='known',factKey='one',expectedOutcome='Yes',availableByClosure=False)
        output=dict(outcomeARegex='won',outcomeBRegex='lost',limitations='fixture')
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)),patch.object(round4,'R2',Path(d)):
            values={'development-cases.private.json':[case],'development-panel.private.json':[case],
                'development-corpus.private.json':[{'id':'known','html':'upcoming','profileCompatible':False},{'id':'new','html':'won','profileCompatible':False}],
                'controls.json':{'1':[dict(name='positive',html='won',expected='A',kind='fixture'),dict(name='negative',html='upcoming',expected='neither',kind='fixture')]}}
            for name,value in values.items():(Path(d)/name).write_text(json.dumps(value))
            with patch('builtins.print'):round4.evaluate('test',[dict(marketId='1',output=output,status='completed')])
            s=json.loads((Path(d)/'methods/test/summary.json').read_text())
            self.assertEqual(s['factualHits'],0)
            self.assertEqual(s['allCorpusEmailsScanned'],2)
            self.assertEqual(s['unlabeledRetrievalPairs'],1)

    def test_feedback_sharding_includes_every_candidate_exactly_once(self):
        public=[dict(marketId=str(i),question='q',rules='r',outcomeLabels=['Yes','No']) for i in range(189)]
        rows=[dict(marketId=p['marketId'],output={'outcomeARegex':'won','outcomeBRegex':'lost'},factualScore=None,controls=[],syntaxRepair=None,nativeValidation=[]) for p in public]
        captured=[]
        def model(job,directory):
            captured.append(job['input'])
            return {'status':'completed','output':dict(lessons=['one'],usefulGrammar=[],safetyFailures=[],gasReductions=[],dataQualityLimits=[])}
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)),patch.object(round4,'safe_call',side_effect=model),patch('builtins.print'):
            for name,value in [('development-public.json',public),('controls.json',{}),('all-factual-evidence.private.json',[])]:
                (Path(d)/name).write_text(json.dumps(value))
            methods={'candidate':dict(summary={},rows=rows,nativeSummary={})}
            round4.distill_feedback(methods)
            seen=[r['marketId'] for p in captured for r in p['rows']]
            self.assertEqual(len(seen),189)
            self.assertEqual(len(set(seen)),189)
            self.assertEqual(len(methods['candidate']['lessonsFromEveryCandidate']),len(captured))
            self.assertTrue(all('candidateSha256' in r for r in methods['candidate']['rows']))

    def test_failed_request_with_null_usage_remains_in_accounting(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round4,'ROOT',Path(d)),patch.object(round4,'output_from',return_value=(None,None,'failed')),patch('builtins.print'):
            (Path(d)/'transport-result.json').write_text('{}')
            round4.report()
            usage=json.loads((Path(d)/'usage-audit.json').read_text())
            self.assertEqual(usage['requests'],1)
            self.assertEqual(usage['completed'],0)
            self.assertEqual(usage['missingUsage'],1)

if __name__=='__main__':unittest.main()
