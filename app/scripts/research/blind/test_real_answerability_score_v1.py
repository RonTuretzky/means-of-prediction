import unittest
from unittest.mock import patch
import real_answerability_score_v1 as s


def label(cid, side, status='adjudicated'):
    return {'caseId': cid, 'settlementOutcome': side, 'reviewStatus': status}


class ScoreTests(unittest.TestCase):
    def test_audit_coverage_cannot_substitute_duplicate_rows_for_missing_review(self):
        plan = {'entries': [{'name': 'a/x'}, {'name': 'b/x'}]}
        record = {'partial': False, 'pending': [], 'accountedFor': 2,
                  'rows': [{'name': 'a/x'}, {'name': 'a/x'}]}
        with self.assertRaisesRegex(RuntimeError, 'Complete unique'):
            s.check_audit(record, plan)

    def test_complete_audit_binds_current_auditor_and_all_raw_files(self):
        plan = {'entries': [{'name': 'a/x'}, {'name': 'b/x'}]}
        record = {'partial': False, 'pending': [], 'accountedFor': 2,
                  'planSha256': 'hash', 'auditorSha256': 'hash',
                  'rows': [{'name': 'a/x'}, {'name': 'b/x'}]}
        with patch.object(s.a.q.r, 'digest', return_value='hash'), patch.object(s, 'verify_raw_hashes') as verify:
            s.check_audit(record, plan)
            verify.assert_called_once_with(record)
            record['auditorSha256'] = 'changed'
            with self.assertRaisesRegex(RuntimeError, 'auditor changed'):
                s.check_audit(record, plan)

    def test_empty_answerable_subset_is_unknown_not_zero(self):
        result = s.measure([label('x', 'INSUFFICIENT')], {'x': 'NEITHER'})
        self.assertIsNone(result['recoveryAmongAnswerable'])
        self.assertIsNone(result['correctnessAmongDirectionalAnswersOnAnswerablePairs'])

    def test_failures_and_abstentions_stay_in_denominator(self):
        labels = [label(str(i), 'A') for i in range(5)]
        result = s.measure(labels, dict(zip(map(str, range(5)), ['A', 'B', 'NEITHER', 'UNSCORABLE', 'CONFLICT'])))
        self.assertEqual(result['answerablePairs'], 5)
        self.assertEqual(result['recoveryAmongAnswerable'], .2)
        self.assertEqual(result['correctnessAmongDirectionalAnswersOnAnswerablePairs'], .5)
        for key in ['correct', 'wrongSide', 'abstention', 'executionFailure', 'conflict']:
            self.assertEqual(result[key], 1)
        self.assertEqual(result['panelPairs'], 5)
        self.assertEqual(result['executionFailuresAcrossPanel'], 1)

    def test_insufficient_evidence_is_not_no(self):
        result = s.measure([label('x', 'INSUFFICIENT')], {'x': 'B'})
        self.assertEqual(result['answerablePairs'], 0)
        self.assertEqual(result['directionalOrConflictingOutputsOnInsufficientPairs'], 1)

    def test_execution_failure_outside_answerable_subset_remains_visible(self):
        result = s.measure([label('x', 'INSUFFICIENT')], {'x': 'UNSCORABLE'})
        self.assertEqual(result['executionFailure'], 0)
        self.assertEqual(result['executionFailuresAcrossPanel'], 1)

    def test_ambiguity_nonbinary_unresolved_reported_separately(self):
        labels = [label('a', 'AMBIGUOUS'), label('b', 'NONBINARY'), label('c', 'INSUFFICIENT', 'unresolved')]
        result = s.measure(labels, {'a': 'NEITHER', 'b': 'NEITHER', 'c': 'NEITHER'})
        self.assertEqual(result['unresolvedPairs'], 2)
        self.assertEqual(result['nonbinaryPairs'], 1)
        self.assertEqual(result['answerablePairs'], 0)

    def test_regex_conflict_not_a_correct_side(self):
        row = {'status': 'completed', 'factualScore': {'validPair': True, 'status': 'conflict', 'matches': [{}, {}]}}
        self.assertEqual(s.regex_decision(row), 'CONFLICT')

    def test_regex_timeout_not_abstention_or_match(self):
        row = {'status': 'completed', 'factualScore': {'validPair': True, 'status': 'timeout', 'matches': [{}, None]}}
        self.assertEqual(s.regex_decision(row), 'UNSCORABLE')

    def test_missing_case_or_invalid_decision_rejected(self):
        for decisions in [{}, {'x': 'yes'}]:
            with self.assertRaises(ValueError):
                s.measure([label('x', 'A')], decisions)

    def test_full_score_uses_strict_qwen_decision_and_preserves_group_counts(self):
        selected = [{'caseId': 'a', 'marketId': '1', 'emailId': 'mail', 'family': 'event'},
                    {'caseId': 'b', 'marketId': '2', 'emailId': 'mail', 'family': 'event'}]
        labels = [label('a', 'A'), label('b', 'B')]
        qr = [{'caseId': 'a', 'kind': 'factual', 'settlementOutcome': 'NEITHER', 'factualOutcome': 'A', 'exactQuote': True},
              {'caseId': 'b', 'kind': 'factual', 'settlementOutcome': 'B', 'factualOutcome': 'B', 'exactQuote': False}]
        rr = [{'marketId': '1', 'status': 'completed', 'factualScore': {'validPair': True, 'status': 'hit', 'matches': [{}, None]}},
              {'marketId': '2', 'status': 'completed', 'factualScore': {'validPair': True, 'status': 'miss', 'matches': [None, None]}}]
        sealed = {k: 'hash' for k in ['labelsSha256', 'planSha256', 'rawAuditSha256', 'scorerSha256']}
        sealed['methodHashes'] = {str(s.QWEN): 'hash', str(s.REGEX): 'hash'}
        result = {}

        def read(path):
            if path == s.QWEN: return qr
            if path == s.REGEX: return rr
            if path.name == 'adjudicated-labels-seal.json': return sealed
            if path.name == 'adjudicated-labels.private.json': return labels
            if path.name == 'adjudicated-baseline-comparison.private.json': return result
            return {'rows': []}

        with patch.object(s.a, 'verify_plan', return_value={'selected': selected}), \
             patch.object(s, 'check_labels'), patch.object(s, 'verify_raw_hashes'), \
             patch.object(s, 'METHOD_HASHES', sealed['methodHashes']), \
             patch.object(s.a.q.r, 'read', side_effect=read), \
             patch.object(s.a.q.r, 'digest', return_value='hash'), \
             patch.object(s.a, 'write_once', side_effect=lambda path, value: result.update(value)), \
             patch('builtins.print'):
            s.score()
        self.assertEqual(result['answerableDistinctEmails'], 1)
        self.assertEqual(result['answerableDistinctFamilies'], 1)
        self.assertEqual(result['qwenStrictSide']['correct'], 1)
        self.assertEqual(result['qwenStrictSide']['abstention'], 1)
        self.assertEqual(result['qwenStrictSideWithExactQuote']['correct'], 0)
        self.assertEqual(result['regexCandidateSide']['correct'], 1)


if __name__ == '__main__':
    unittest.main()
