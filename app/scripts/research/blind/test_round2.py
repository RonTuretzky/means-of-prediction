import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import round2
from round2_matcher import compile_pattern,search

class RoundTwoTests(unittest.TestCase):
    def test_boundary_repair_removes_only_an_existing_start_alternative(self):
        source={'outcomeARegex':r'(?i)(?:^|[\s>])Team won','outcomeBRegex':r'^Team lost','limitations':'test'}
        fixed,keys=round2.boundary_repair(source)
        self.assertEqual(fixed['outcomeARegex'],r'(?i)(?:[\s>])Team won')
        self.assertEqual(fixed['outcomeBRegex'],r'^Team lost')
        self.assertEqual(keys,['outcomeARegex']);self.assertIn('^|',source['outcomeARegex'])
        pattern,error=compile_pattern(fixed['outcomeARegex']);self.assertIsNone(error)
        self.assertIsNone(search(pattern,'Team won')[0]);self.assertIsNotNone(search(pattern,'>Team won')[0])

    def test_escaped_plus_can_be_optional_without_being_a_lazy_quantifier(self):
        pattern,error=compile_pattern(r'\+?3\.4 percent')
        self.assertIsNone(error)
        for text in ['+3.4 percent','3.4 percent']:self.assertIsNotNone(search(pattern,text)[0])
        self.assertIsNone(search(pattern,'3.5 percent')[0])
        self.assertIsNotNone(compile_pattern(r'a+?')[1])
        self.assertIsNotNone(compile_pattern(r'a\++?')[1])

    def test_cannot_score_new_email_before_generation_seal(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round2,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text(json.dumps({'artifactHashes':{}}))
            with patch.object(round2.subprocess,'run') as render:
                with self.assertRaises(FileNotFoundError):round2.score_challenge()
                render.assert_not_called()

    def test_new_holdout_cannot_use_unselected_method(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round2,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text(json.dumps({'artifactHashes':{},'challengeMethods':['baseline'],'trialsPerChallengeMarket':2}))
            with patch.object(round2,'generate') as model:
                with self.assertRaisesRegex(RuntimeError,'frozen plan'):round2.batch('unselected','holdout',trials=2)
                model.assert_not_called()

    def test_training_closes_after_selection(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round2,'ROOT',Path(d)):
            (Path(d)/'selection.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'Selection frozen'):round2.optimize('another','baseline')
            with self.assertRaisesRegex(RuntimeError,'Development phase is closed'):round2.batch('baseline')

    def test_frozen_prompt_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as d,patch.object(round2,'ROOT',Path(d)):
            p=Path(d)/'selected.txt';p.write_text('original')
            seal={'artifactHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()}}
            (Path(d)/'selection.json').write_text(json.dumps(seal))
            round2.verify_selection();p.write_text('new test-informed prompt')
            with self.assertRaisesRegex(RuntimeError,'Selected artifact changed'):round2.verify_selection()

if __name__=='__main__':unittest.main()
