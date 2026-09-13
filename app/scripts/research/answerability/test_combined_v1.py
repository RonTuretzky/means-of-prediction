import copy
import unittest
from unittest.mock import patch

import combined_v1 as c


def fixture():
    selected=[{'caseId':str(i),'marketId':str(i)} for i in range(101)]
    labels=[{'caseId':str(i),'settlementOutcome':'INSUFFICIENT','reviewStatus':'adjudicated',
        'reviewedPasses':['a','b'],'humanValidated':False,'reviewer':'model','reason':'Missing source',
        'jobSha256':'hash','supportingQuotes':[]} for i in range(101)]
    eligible={str(i):True for i in range(101)}
    reader=lambda cid:({'input':{'completeEmail':{'completeSemanticText':'exact evidence'}}},'hash')
    return labels,selected,eligible,reader


class CombinedTests(unittest.TestCase):
    def test_complete_unique_labels_required(self):
        args=fixture();c.validate_labels(*args)
        args[0][-1]=copy.deepcopy(args[0][0])
        with self.assertRaises(ValueError):c.validate_labels(*args)

    def test_incomplete_review_cannot_be_semantically_adjudicated(self):
        args=fixture();args[2]['0']=False
        with self.assertRaises(ValueError):c.validate_labels(*args)
        args[0][0].update(reviewStatus='unresolved',settlementOutcome='AMBIGUOUS',unresolvedKind='annotation_incomplete')
        c.validate_labels(*args)

    def test_positive_requires_exact_quote_and_resolved_review(self):
        for patch_value in [{'settlementOutcome':'A'}, {'settlementOutcome':'A','supportingQuotes':['wrong']},
            {'settlementOutcome':'A','supportingQuotes':['exact evidence'],'reviewStatus':'unresolved'}]:
            args=fixture();args[0][0].update(patch_value)
            with self.assertRaises(ValueError):c.validate_labels(*args)
        args=fixture();args[0][0].update(settlementOutcome='A',supportingQuotes=['exact evidence'])
        c.validate_labels(*args)

    def test_source_identity_and_two_pass_review_required(self):
        for patch_value in [{'jobSha256':'bad'},{'reviewedPasses':['a']},{'humanValidated':True}]:
            args=fixture();args[0][0].update(patch_value)
            with self.assertRaises(ValueError):c.validate_labels(*args)

    def raw_fixture(self):
        selected=fixture()[1];entries=[{'name':p+'/'+s['caseId']} for s in selected for p in ['a','b']]
        rows=[{'name':e['name'],'rawVerified':True,'status':'completed','fileHashes':{}} for e in entries]
        plan={'entries':entries,'selected':selected,'pins':{str(c.a.HERE/'real_answerability_remaining_audit_v1.py'):'hash'}}
        report={'rows':rows,'partial':False,'accountedFor':202,'planSha256':'hash','auditorSha256':'hash',
            'pairsEligibleForAdjudication':fixture()[2],'eligiblePairCount':101}
        return report,plan

    def test_raw_coverage_duplicates_and_partial_rejected(self):
        with patch.object(c.a.q.r,'digest',return_value='hash'):
            report,plan=self.raw_fixture();self.assertEqual(sum(c.audit_gate(report,plan).values()),101)
            report['partial']=True
            with self.assertRaises(RuntimeError):c.audit_gate(report,plan)
            report['partial']=False;report['rows'][-1]=report['rows'][0]
            with self.assertRaises(RuntimeError):c.audit_gate(report,plan)

    def test_raw_pair_eligibility_recomputed(self):
        with patch.object(c.a.q.r,'digest',return_value='hash'):
            report,plan=self.raw_fixture();report['rows'][0].update(rawVerified=False,status='failed')
            with self.assertRaises(RuntimeError):c.audit_gate(report,plan)
            report['pairsEligibleForAdjudication']['0']=False;report['eligiblePairCount']=100
            self.assertFalse(c.audit_gate(report,plan)['0'])

    def test_strict_not_factual_and_quotes_remain_separate(self):
        labels=[{'caseId':'1'},{'caseId':'2'}];selected=[{'caseId':'1','marketId':'m1'},{'caseId':'2','marketId':'m2'}]
        qr=[{'caseId':'1','settlementOutcome':'NEITHER','factualOutcome':'A','exactQuote':True},
            {'caseId':'2','settlementOutcome':'B','factualOutcome':'A','exactQuote':False}]
        rr=[{'marketId':'m1','status':'completed','factualScore':{'validPair':True,'status':'miss','matches':[None,None]}},
            {'marketId':'m2','status':'failed','factualScore':{'validPair':False}}]
        result=c.decisions(labels,selected,qr,rr)
        self.assertEqual(result['qwenStrictSide'],{'1':'NEITHER','2':'B'})
        self.assertEqual(result['qwenStrictSideWithExactQuote'],{'1':'NEITHER','2':'NEITHER'})
        self.assertEqual(result['regexCandidateSide'],{'1':'NEITHER','2':'UNSCORABLE'})
        with self.assertRaises(ValueError):c.decisions(labels,selected,qr+qr[:1],rr)


if __name__=='__main__':unittest.main()
