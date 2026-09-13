import copy,hashlib,unittest
from unittest.mock import patch
import qwen_metadata_diagnostic as d

class MetadataDiagnosticTests(unittest.TestCase):
    def fixture(self):
        raw=(b'Date: Mon, 7 Sep 2026 10:00:00 +0000\r\nSubject: Complete report\r\nFrom: source@example.org\r\n'
             b'DKIM-Signature: v=1; a=rsa-sha256; d=example.org; s=test; h=Date:Subject:From:Subject:Cc; b=fixture\r\n\r\nComplete unchanged body.\r\n')
        date='2026-09-07T10:00:00.000Z'
        meta={'date':date,'receivedAt':'2026-09-07T10:00:01.000Z','proof':{'domain':'example.org','signedAt':date},
              'signatures':[{'result':'pass','algorithm':'rsa-sha256','bodyLengthLimited':False,'domain':'example.org','selector':'test','signedHeaders':'Date: Subject: From'}]}
        return raw,hashlib.sha256(raw).hexdigest(),meta
    def test_oversigned_absent_headers_preserve_existing_field_linkage(self):
        raw,sha,meta=self.fixture();values,audit=d.verified_metadata(raw,sha,'Complete report',meta)
        self.assertEqual(values['signedDate'],meta['date']);self.assertFalse(audit['newRsaOrDnsVerification'])
    def test_raw_date_hash_and_header_coverage_mismatches_reject(self):
        raw,sha,meta=self.fixture()
        with self.assertRaises(RuntimeError):d.verified_metadata(raw+b'changed',sha,'Complete report',meta)
        altered=copy.deepcopy(meta);altered['date']='2026-09-08T10:00:00.000Z'
        with self.assertRaises(RuntimeError):d.verified_metadata(raw,sha,'Complete report',altered)
        altered=copy.deepcopy(meta);altered['signatures'][0]['signedHeaders']='Date: From'
        with self.assertRaises(RuntimeError):d.verified_metadata(raw,sha,'Complete report',altered)
    def test_current_signature_is_excluded_from_h_header_consumption(self):
        raw,_,meta=self.fixture();raw=raw.replace(b':Subject:Cc;',b':Subject:Cc:DKIM-Signature;')
        values,_=d.verified_metadata(raw,hashlib.sha256(raw).hexdigest(),'Complete report',meta)
        self.assertEqual(values['dkimDomain'],'example.org')
    def test_restoration_never_overwrites_populated_values_or_body(self):
        original={'subject':'Original subject','dkimDomain':'','signedDate':'','receivedAt':'existing receipt','completeSemanticText':'Whole body','representation':'fixed'}
        values={'subject':'Other','dkimDomain':'example.org','signedDate':'date','receivedAt':'other receipt'}
        restored,changed=d.restore_missing(original,values)
        self.assertEqual(changed,['dkimDomain','signedDate']);self.assertEqual(restored['subject'],'Original subject')
        self.assertEqual(restored['receivedAt'],'existing receipt');self.assertEqual(restored['completeSemanticText'],'Whole body')
    def test_inference_checks_post_selection_gates_before_input_reads(self):
        with patch.object(d,'gates',side_effect=RuntimeError('fresh incomplete')),patch.object(d,'load') as load:
            with self.assertRaises(RuntimeError):d.run('baseline')
            load.assert_not_called()
    def test_replay_agreement_separates_unavailable_and_explanation_variation(self):
        output={'factualOutcome':'A','outcomeA':'YES','outcomeB':'NO','evidenceQuote':'complete','missingConditions':[]}
        first={'caseId':'one','kind':'factual','status':'completed','output':output}
        missing={'caseId':'two','kind':'weak','status':'rule_unavailable','output':None}
        rows=[{'record':{**first,'variant':'original','output':{**output,'evidenceQuote':'other quote'}}},
              {'record':{**missing,'variant':'original'}}]
        summary=d.replay_comparison(rows,{'one':first,'two':missing})
        self.assertEqual(summary['all']['rows'],2);self.assertEqual(summary['all']['statusAgreement'],2)
        self.assertEqual(summary['all']['bothCompleted'],1);self.assertEqual(summary['all']['strictDecisionAgreement'],1)
        self.assertEqual(summary['all']['canonicalParsedJsonAgreement'],0);self.assertEqual(summary['byKind']['weak']['bothCompleted'],0)
    def test_execution_missing_usage_is_explicit(self):
        counts=d.execution_counts([{'status':'completed','seconds':1.5,'usage':{'prompt_tokens':10,'completion_tokens':3}},
            {'status':'transport_failed','seconds':None,'usage':None},{'status':'rule_unavailable'}])
        self.assertEqual(counts['attemptedRequests'],2);self.assertEqual(counts['attemptedWithoutInputUsage'],1)
        self.assertEqual(counts['attemptedWithoutOutputUsage'],1);self.assertEqual(counts['attemptedWithoutDuration'],1)
        self.assertEqual(counts['knownInputTokens'],10);self.assertEqual(counts['unavailableRuleRows'],1)

if __name__=='__main__':unittest.main()
