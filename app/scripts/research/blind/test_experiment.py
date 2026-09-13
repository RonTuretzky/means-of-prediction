import base64, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from astra_transport import build_request
from experiment import output_from, generate
from matcher import compile_pattern, score
from improve import score_controls, summarize
from witness import witness
from finalize import verify_frozen_artifacts, verify_selection

class ExperimentTests(unittest.TestCase):
    def test_raw_transport_changes_are_detected_before_scoring(self):
        with tempfile.TemporaryDirectory() as d,patch('finalize.ROOT',Path(d)):
            p=Path(d)/'transport-result.json';p.write_text('{"original":true}')
            seal={'files':{},'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()}}
            verify_frozen_artifacts(seal)
            p.write_text('{"altered":true}')
            with self.assertRaisesRegex(RuntimeError,'artifact changed'):verify_frozen_artifacts(seal)

    def test_public_context_changes_are_detected(self):
        with tempfile.TemporaryDirectory() as d,patch('finalize.ROOT',Path(d)):
            p=Path(d)/'public-contexts.json';p.write_text('{}')
            selected={'promptHashes':{},'publicContextsSha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            verify_selection(selected);p.write_text('{"changed":true}')
            with self.assertRaisesRegex(RuntimeError,'Frozen input changed'):verify_selection(selected)

    def test_streamed_output_is_recovered_when_terminal_envelope_omits_it(self):
        result={'events':[{'response':{'model':'gpt-6-astra','status':'completed','output':[],'usage':{'output_tokens':5000}}}],
                'outputItems':[{'type':'message','content':[{'type':'output_text','text':'{"outcomeARegex":"won","outcomeBRegex":"lost","limitations":"none"}'}]}]}
        out,usage,status=output_from(result)
        self.assertEqual(out['outcomeARegex'],'won');self.assertEqual(usage['output_tokens'],5000);self.assertEqual(status,'completed')

    def test_incomplete_response_cannot_count_as_a_success(self):
        response={'events':[{'response':{'model':'gpt-6-astra','status':'incomplete','output':[{'type':'message','content':[{'type':'output_text','text':'{"outcomeARegex":"won"}'}]}]}}]}
        out,_,status=output_from(response)
        self.assertIsNone(out);self.assertEqual(status,'incomplete')

    def test_transport_rejects_inherited_tools_and_messages_by_construction(self):
        body=build_request({'instructions':'fixed','input':{'publicMarket':{'question':'test'}},'schema':{'type':'object'},
                           'tools':[{'type':'shell'}],'messages':[{'content':'PRIVATE_TARGET_EMAIL'}],'max_output_tokens':2000})
        self.assertEqual(body['tools'],[]);self.assertEqual(body['tool_choice'],'none')
        self.assertNotIn('PRIVATE_TARGET_EMAIL',json.dumps(body));self.assertNotIn('max_output_tokens',body)

    def test_case_private_fields_are_not_sent_to_generator(self):
        case={'marketId':'1','groupId':'g','split':'test','expectedOutcome':'SECRET_OUTCOME','emailId':'SECRET_MAIL_ID',
              'publicInput':{'marketId':'1','question':'Who wins?','rules':'Public rules','outcomeLabels':['A','B']}}
        result={'events':[{'response':{'model':'gpt-6-astra','status':'completed','usage':{},'output':[{'type':'message','content':[{'type':'output_text','text':'{"outcomeARegex":"won","outcomeBRegex":"lost","limitations":"none"}'}]}]}}]}
        with tempfile.TemporaryDirectory() as d,patch('experiment.run',return_value=result) as model:
            generate(case,'fixed prompt','high',8000,1,Path(d)/'one')
            job=model.call_args.args[0]
            self.assertNotIn('SECRET_',json.dumps(job));self.assertEqual(set(job['input']['publicMarket']),set(case['publicInput']))

    def test_extra_public_fields_are_rejected(self):
        case={'publicInput':{'marketId':'1','question':'Q','rules':'R','outcomeLabels':['Y','N'],'email':'SECRET'}}
        with tempfile.TemporaryDirectory() as d,self.assertRaises(AssertionError):generate(case,'p','high',8000,1,d)

    def test_contract_dialect_restrictions(self):
        for pattern in [r'(?i)\bwon',r'(?i)(?=won)',r'^won',r'won.*?',r'a{65535}','('*17+'a'+')'*17]:
            with self.subTest(pattern=pattern):self.assertIsNotNone(compile_pattern(pattern)[1])
        self.assertIsNone(compile_pattern(r'(?i)won(?:[\s\S]{0,10})[0-9]+')[1])

    def test_both_outcome_matches_are_conflicts_not_hits(self):
        result=score({'outcomeARegex':'won','outcomeBRegex':'lost'},{'html':'won and lost'},
                     {'publicInput':{'outcomeLabels':['Yes','No']},'expectedOutcome':'Yes'})
        self.assertEqual(result['status'],'conflict')

    def test_wrong_outcome_and_forecast_are_penalized(self):
        output={'outcomeARegex':'won','outcomeBRegex':'lost'}
        rows=score_controls(output,[{'name':'f','kind':'forecast','html':'The prediction is that the team won','expected':'neither'}])
        self.assertFalse(rows[0]['passed'])
        r={'score':{'status':'hit'},'controls':rows,'usage':{'output_tokens':5000}}
        summary=summarize([r]);self.assertEqual(summary['cleanHits'],1);self.assertEqual(summary['safeControlHits'],0)
        self.assertEqual(summary['negativeControlFailures'],1)

    def test_qp_window_maps_to_original_encoded_bytes(self):
        body=b'<p>Team=20A wo=\r\nn 3=E2=80=932.</p>'
        text='<p>Team A won 3\u20132.</p>'
        email={'encoding':1,'profileCompatible':True,'canonicalBodyBase64':base64.b64encode(body).decode(),'html':text}
        pattern=compile_pattern('Team A won')[0]
        result=witness(email,{'start':3,'end':13},pattern)
        self.assertTrue(result['compatible']);self.assertEqual(base64.b64decode(result['encodedBase64']),b'Team=20A wo=\r\nn')
        email['html']='different source'
        self.assertFalse(witness(email,{'start':3,'end':13},pattern)['compatible'])

if __name__=='__main__':unittest.main()
