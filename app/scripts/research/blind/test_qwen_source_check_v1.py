import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qwen_source_check_v1 as s


class SourceCheckTests(unittest.TestCase):
    def fixture(self):
        selected=[{'caseId':str(i),'marketId':str(i)} for i in range(60)]
        email={'subject':'s','dkimDomain':'example.org','signedDate':'','receivedAt':'',
            'completeSemanticText':'Full body sentinel '+('text '*100),'representation':s.q.semantic.VERSION}
        items={str(i):{'caseId':str(i),'marketId':str(i),'kind':'factual','email':email,
            'expected':'PRIVATE_LABEL','metadata':{'secret':'PRIVATE_METADATA'}} for i in range(60)}
        rules={str(i):{'status':'completed','output':{k:k+' predicate' for k in s.q.RULE_SCHEMA['properties']}} for i in range(60)}
        return selected,items,rules,{'identifier':'test'},'BASE'

    def test_only_prompt_differs_and_private_fields_absent(self):
        rows=s.build(*self.fixture())
        self.assertEqual(len(rows),120)
        for i in range(60):
            a,b=sorted(rows[i*2:i*2+2],key=lambda x:x['variant'])
            ra,rb=copy.deepcopy(a['request']),copy.deepcopy(b['request'])
            self.assertEqual(ra['messages'][0]['content'],'BASE')
            self.assertEqual(rb['messages'][0]['content'],'BASE'+s.ADDENDUM)
            ra['messages'][0]['content']=rb['messages'][0]['content']='same'
            self.assertEqual(ra,rb)
            self.assertNotIn('PRIVATE_',json.dumps(ra))
            self.assertEqual(json.loads(ra['messages'][1]['content'])['email'],self.fixture()[1][str(i)]['email'])

    def test_missing_rule_remains_two_failures(self):
        args=self.fixture(); args[2]['0']={'status':'transport_failed','output':None}
        rows=s.build(*args)
        self.assertTrue(all(r['request'] is None for r in rows[:2]))
        self.assertEqual(len(rows),120)

    def test_partial_or_duplicate_panel_rejected(self):
        args=list(self.fixture()); args[0]=args[0][:-1]
        with self.assertRaises(ValueError):s.build(*args)
        args=list(self.fixture()); args[0][-1]=args[0][0]
        with self.assertRaises(ValueError):s.build(*args)

    def test_identity_and_body_mismatch_rejected(self):
        args=self.fixture(); args[1]['0']['marketId']='bad'
        with self.assertRaises(ValueError):s.build(*args)
        args=self.fixture(); args[1]['0']['email']['extra']='bad'
        with self.assertRaises(ValueError):s.build(*args)

    def test_alternating_order(self):
        rows=s.build(*self.fixture())
        self.assertEqual([r['variant'] for r in rows[:4]],['baseline','source_check','source_check','baseline'])

    def saved(self, root, finish='stop'):
        request=s.build(*self.fixture())[0]['request']
        output={'factualOutcome':'A','outcomeA':'NO','outcomeB':'NO','evidenceQuote':'Full body','missingConditions':['source']}
        raw={'model':'test','choices':[{'finish_reason':finish,'message':{'content':json.dumps(output)}}],
            'usage':{'prompt_tokens':25,'completion_tokens':12}}
        s.c.once(root/'request.json',request); s.c.once(root/'response.json',raw)
        (root/'response.raw').write_text(json.dumps(raw))
        result={'status':'completed' if finish=='stop' else 'failed','output':output,'httpStatus':200,
            'returnedModel':'test','reasoningCharacters':0,'seconds':1,
            'finishReason':finish,'usage':raw['usage'],'requestSha256':s.q.r.hash_value(request),
            'responseSha256':s.q.r.digest(root/'response.json'),'rawResponseSha256':s.q.r.digest(root/'response.raw')}
        s.c.once(root/'result.json',result)
        return {'request':request}

    def test_raw_status_output_and_hashes_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); e=self.saved(root)
            self.assertEqual(s.audit_result(e,root)[0]['status'],'completed')
            result=s.q.r.read(root/'result.json'); result['output']['outcomeA']='YES'
            (root/'result.json').write_text(json.dumps(result))
            with self.assertRaises(RuntimeError):s.audit_result(e,root)

    def test_cap_failure_cannot_be_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); e=self.saved(root,'length')
            self.assertEqual(s.audit_result(e,root)[0]['status'],'failed')

    def test_hash_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); e=self.saved(root)
            (root/'response.raw').write_text('{}')
            with self.assertRaises(RuntimeError):s.audit_result(e,root)

    def test_failed_response_metadata_still_audited(self):
        for field,value in [('returnedModel','wrong'),('reasoningCharacters',99),('usage',None)]:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); e=self.saved(root,'length')
                result=s.q.r.read(root/'result.json'); result[field]=value
                (root/'result.json').write_text(json.dumps(result))
                with self.assertRaises(RuntimeError):s.audit_result(e,root)

    def test_completed_missing_model_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); e=self.saved(root)
            raw=s.q.r.read(root/'response.json'); raw.pop('model')
            (root/'response.json').write_text(json.dumps(raw)); (root/'response.raw').write_text(json.dumps(raw))
            result=s.q.r.read(root/'result.json'); result['returnedModel']=None
            result['responseSha256']=s.q.r.digest(root/'response.json'); result['rawResponseSha256']=s.q.r.digest(root/'response.raw')
            (root/'result.json').write_text(json.dumps(result))
            with self.assertRaises(RuntimeError):s.audit_result(e,root)


if __name__=='__main__':unittest.main()
