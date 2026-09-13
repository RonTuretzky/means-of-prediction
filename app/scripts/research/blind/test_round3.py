import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import round3

class RoundThreeIsolationTests(unittest.TestCase):
    def test_syntax_repair_cannot_receive_private_case_fields(self):
        with patch.object(round3,'safe_invoke') as model:
            with self.assertRaisesRegex(ValueError,'public market fields'):
                round3.repair_syntax({},dict(marketId='1',question='q',rules='r',outcomeLabels=['Yes','No'],email='private'))
            model.assert_not_called()

    def test_syntax_repair_uses_only_public_rules_candidate_and_errors_once(self):
        public=dict(marketId='1',question='q',rules='r',outcomeLabels=['Yes','No'])
        candidate=dict(outcomeARegex='(',outcomeBRegex='lost',limitations='test')
        with tempfile.TemporaryDirectory() as d:
            record=dict(status='completed',output=candidate,usage={'output_tokens':10},directory=d,privateEmail='do not send')
            (Path(d)/'syntax-repair').mkdir()
            result=dict(output=candidate,status='completed',usage={'output_tokens':2},requestSha256='fixture')
            with patch.object(round3,'safe_invoke',return_value=result) as model:
                fixed=round3.repair_syntax(record,public)
                self.assertEqual(model.call_count,1)
                self.assertEqual(set(model.call_args.args[0]['input']),{'publicMarket','candidate','syntaxErrors'})
                self.assertNotIn('privateEmail',model.call_args.args[0]['input'])
                self.assertEqual(len(fixed['pipelineUsage']),2)
                self.assertEqual(fixed['rawOutput'],candidate)

    def test_cannot_score_independent_fixtures_without_freezing_generations(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round3,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text(json.dumps({'artifactHashes':{}}))
            with patch.object(round3,'score_controls') as scorer:
                with self.assertRaises(FileNotFoundError):round3.score_test()
                scorer.assert_not_called()

    def test_cannot_train_after_selection(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round3,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text('{}')
            with patch.object(round3,'safe_invoke') as model:
                with self.assertRaisesRegex(RuntimeError,'Development closed'):round3.optimize('retained-v2','retained-v1')
                model.assert_not_called()

    def test_cached_request_must_match_instead_of_reusing_a_different_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'job.json').write_text(json.dumps({'input':'old'}))
            with patch.object(round3,'invoke') as model:
                with self.assertRaisesRegex(RuntimeError,'Request changed'):round3.safe_invoke({'input':'new'},Path(d))
                model.assert_not_called()

    def test_invalid_rejection_does_not_beat_useful_scorable_behavior(self):
        useful={'cleanHits':13,'factualCases':38,'positiveControlPasses':12,'positiveControls':84,
            'negativeFalsePositives':2,'negativeControls':126,'invalidPairs':0,'attempts':46,
            'nativeFactualHits':0,'pipelineOutputTokens':10000}
        inert=dict(useful,cleanHits=0,positiveControlPasses=0,negativeFalsePositives=0,invalidPairs=46)
        self.assertGreater(round3.rank(useful),round3.rank(inert))

if __name__=='__main__':unittest.main()
