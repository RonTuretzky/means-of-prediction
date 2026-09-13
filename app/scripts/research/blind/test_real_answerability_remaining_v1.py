import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import real_answerability_remaining_v1 as a
import real_answerability_remaining_audit_v1 as audit


def items():
    return [{'caseId':str(i).zfill(3),'marketId':str(i),'kind':'factual','expected':'SECRET_OUTCOME',
        'metadata':{'emailId':'email'+str(i%18),'factKey':'family'+str(i%33),'availableByClosure':i<19,'oldScore':'SECRET_SCORE'},
        'email':{'subject':'Subject','dkimDomain':'example.test','signedDate':None,'receivedAt':'2026-01-01',
                 'completeSemanticText':'The full result is17. '+('body '*100),'representation':a.q.semantic.VERSION}}
        for i in range(161)]


def selected(xs):
    return [{'caseId':i['caseId'],'marketId':i['marketId'],'emailId':i['metadata']['emailId'],
        'family':i['metadata']['factKey'],'legacyTimingStratum':i['metadata']['availableByClosure']} for i in xs[:60]]


def entries():
    return [{'name':p+'/'+str(i),'caseId':str(i),'pass':p,'jobSha256':'hash'} for i in range(101) for p in ['a','b']]


class RemainingTests(unittest.TestCase):
    def test_exact_complement_independent_of_order_and_labels(self):
        xs=items();old=selected(xs);answer=a.select_remaining(xs,old)
        altered=list(reversed(copy.deepcopy(xs)))
        for x in altered:x['expected']='OTHER';x['metadata']['oldScore']='OTHER'
        self.assertEqual([x['caseId'] for x in answer],[x['caseId'] for x in a.select_remaining(altered,old)])
        self.assertEqual(len(answer),101);self.assertFalse({x['caseId'] for x in answer}&{x['caseId'] for x in old})

    def test_duplicate_partial_or_reassigned_prior_rejected(self):
        for mode in ['duplicate','partial','identity']:
            xs=items();old=selected(xs)
            if mode=='duplicate':old[-1]=old[0]
            if mode=='partial':xs.pop()
            if mode=='identity':old[0]['marketId']='wrong'
            with self.assertRaises(ValueError):a.select_remaining(xs,old)

    def test_same_original_blind_jobs_full_email_and_pass_isolation(self):
        item=items()[60];public={'marketId':item['marketId'],'question':'More than16?','rules':'Yes if more than16.','outcomeLabels':['Yes','No']}
        jobs=[a.job_for(item,public,p) for p in ['a','b']]
        for p,j in zip(['a','b'],jobs):
            self.assertEqual(j,a.original.make_job(item,public,p));self.assertNotIn('SECRET',json.dumps(j))
            self.assertEqual(j['input']['completeEmail'],item['email'])
        self.assertEqual(jobs[0]['input'],jobs[1]['input']);self.assertNotEqual(jobs[0]['instructions'],jobs[1]['instructions'])

    def test_private_public_fields_or_bad_pass_rejected(self):
        item=items()[60];public={'marketId':item['marketId'],'question':'q','rules':'r','outcomeLabels':['Yes','No'],'payout':'secret'}
        with self.assertRaises(ValueError):a.job_for(item,public,'a')
        public.pop('payout')
        with self.assertRaises(ValueError):a.job_for(item,public,'c')

    def test_usage_stop_before_submission(self):
        called=[]
        self.assertEqual(a.feed(entries(),4,lambda e:called.append(e),lambda:True),[])
        self.assertEqual(called,[])

    def test_usage_stop_drains_running_without_replacement(self):
        stop=threading.Event();barrier=threading.Barrier(4);called=[];guard=threading.Lock()
        def worker(e):
            with guard:called.append(e['name'])
            barrier.wait(timeout=3);stop.set()
            return {**e,'status':'failed'}
        rows=a.feed(entries(),4,worker,stop.is_set)
        self.assertEqual(len(rows),4);self.assertEqual(len(called),4)

    def test_existing_attempt_and_pre_call_stop_refused(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'ROOT',Path(tmp)),patch.object(a.h,'single_attempt') as call:
            e=entries()[0];directory=a.ROOT/'responses'/e['name'];directory.mkdir(parents=True)
            with patch.object(a.h,'stopped',return_value=False),self.assertRaises(RuntimeError):a.review_one(e)
            with patch.object(a.h,'stopped',return_value=True),self.assertRaises(RuntimeError):a.review_one(e)
            call.assert_not_called()

    def test_exact_raw_gate_denominators_and_failed_pass(self):
        es=entries();rows=[{'name':e['name'],'status':'completed','rawVerified':True} for e in es]
        self.assertEqual(sum(audit.paired_gate(rows,es).values()),101)
        rows[0]['status']='uncertain';rows[0]['rawVerified']=False
        self.assertEqual(sum(audit.paired_gate(rows,es).values()),100)
        rows[-1]=rows[0]
        with self.assertRaises(RuntimeError):audit.paired_gate(rows,es)

    def test_unattempted_and_unknown_artifacts_retained(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'ROOT',Path(tmp)):
            e=entries()[0];job={'input':{'publicMarket':{},'completeEmail':{}},'instructions':'x','schema':{},'effort':'high'}
            a.once(a.ROOT/'jobs'/(e['name']+'.json'),job)
            self.assertEqual(audit.reconcile(e)['status'],'unattempted')
            directory=a.ROOT/'responses'/e['name'];a.once(directory/'attempt-started.json',{'jobSha256':'hash'})
            result=audit.reconcile(e)
            self.assertEqual(result['status'],'uncertain');self.assertEqual(len(result['fileHashes']),1)
            self.assertIsNone(result['inputTokens']);self.assertFalse(result['rawVerified'])

    def test_failed_attempt_keeps_raw_hash_and_unknown_usage(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'ROOT',Path(tmp)):
            e=entries()[0];job={'input':{},'instructions':'x','schema':{},'effort':'high'}
            a.once(a.ROOT/'jobs'/(e['name']+'.json'),job)
            d=a.ROOT/'responses'/e['name'];a.once(d/'attempt-started.json',{'jobSha256':'hash'})
            a.once(d/'review.private.json',{**e,'status':'failed'})
            a.once(d/'model-request.json',a.build_request(job))
            a.once(d/'transport-result.json',{'requests':[{'status':429,'requestSha256':a.q.r.digest(d/'model-request.json')}],'events':[]})
            result=audit.reconcile(e)
            self.assertEqual(result['requestCount'],1);self.assertEqual(len(result['fileHashes']),4)
            self.assertIsNone(result['inputTokens']);self.assertFalse(result['rawVerified'])
            value=a.q.r.read(d/'transport-result.json');value['requests']*=2
            (d/'transport-result.json').write_text(json.dumps(value))
            with self.assertRaises(RuntimeError):audit.reconcile(e)

    def test_missing_cost_is_lower_bound(self):
        self.assertEqual(audit.known([3,None,False,float('nan')]),{'knownTotal':3,'missingOrInvalid':3,'isLowerBound':True})

    def completed_fixture(self, root):
        e=entries()[0];i=items()[0]
        public={'marketId':i['marketId'],'question':'q','rules':'Yes if more than16.','outcomeLabels':['Yes','No']}
        job=a.job_for(i,public,'a')
        output={'coreOutcome':'A','settlementOutcome':'INSUFFICIENT',
            'checks':[{'condition':c,'state':'MISSING','ruleQuote':'','evidenceQuote':'','reason':'Missing'} for c in a.original.CHECKS],
            'supportingQuotes':['The full result is17.'],'settlementRationale':'Source missing','asOfLimitations':[]}
        a.once(root/'jobs'/(e['name']+'.json'),job)
        d=root/'responses'/e['name'];a.once(d/'attempt-started.json',{'jobSha256':'hash'})
        a.once(d/'job.json',job);a.once(d/'model-request.json',a.build_request(job))
        a.once(d/'review.private.json',{**e,'status':'completed','output':output,'validationErrors':[]})
        transport={'requests':[{'status':200,'requestSha256':a.q.r.digest(d/'model-request.json')}],
            'events':[{'type':'response.completed','response':{'model':'gpt-6-astra','status':'completed',
                'usage':{'input_tokens':20,'output_tokens':30},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(output)}]}]}}]}
        a.once(d/'transport-result.json',transport)
        effective={'selectedAttempt':0,'attempts':[{}],'output':output}
        return e,job,effective,d

    def test_completed_raw_output_and_validation_reconciled(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'ROOT',Path(tmp)):
            e,job,effective,d=self.completed_fixture(a.ROOT)
            with patch.object(a.q,'verify_teacher',return_value=(job,effective)):
                self.assertTrue(audit.reconcile(e)['rawVerified'])
                saved=a.q.r.read(d/'review.private.json');saved['output']['coreOutcome']='B'
                (d/'review.private.json').write_text(json.dumps(saved))
                with self.assertRaises(RuntimeError):audit.reconcile(e)

    def test_completed_wrong_model_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'ROOT',Path(tmp)):
            e,job,effective,d=self.completed_fixture(a.ROOT)
            raw=a.q.r.read(d/'transport-result.json');raw['events'][0]['response']['model']='other'
            (d/'transport-result.json').write_text(json.dumps(raw))
            with patch.object(a.q,'verify_teacher',return_value=(job,effective)),self.assertRaises(RuntimeError):audit.reconcile(e)


if __name__=='__main__':unittest.main()
