import copy
import tempfile
import unittest
from pathlib import Path

import real_answerability_v1 as a


def item(n=0, timely=False):
    return {'caseId': str(n).zfill(3), 'kind': 'factual', 'marketId': str(n),
            'expected': 'SECRET_OLD_LABEL',
            'metadata': {'factKey': 'family'+str(n % 10), 'emailId': 'email'+str(n % 8),
                         'availableByClosure': timely, 'privateScore': 'SECRET_SCORE'},
            'email': {'subject': 'Subject', 'dkimDomain': 'example.test', 'signedDate': None,
                      'receivedAt': '2026-01-02', 'completeSemanticText': 'The result is 17.',
                      'representation': 'frozen-complete-semantic'}}


def public(n=0):
    return {'marketId': str(n), 'question': 'More than 16?',
            'rules': 'Resolve Yes if more than 16.', 'outcomeLabels': ['Yes', 'No']}


def output():
    return {'coreOutcome': 'A', 'settlementOutcome': 'A',
            'checks': [{'condition': c, 'state': 'SATISFIED',
                        'ruleQuote': '', 'evidenceQuote': 'The result is 17.', 'reason': 'Reason'} for c in a.CHECKS],
            'supportingQuotes': ['The result is 17.'], 'settlementRationale': 'Reason', 'asOfLimitations': []}


class ReviewTests(unittest.TestCase):
    def test_blind_packet_excludes_labels_and_metadata(self):
        job = a.make_job(item(), public(), 'a')
        self.assertEqual(set(job['input']), {'publicMarket', 'completeEmail'})
        self.assertNotIn('SECRET', str(job))
        self.assertIsNone(job['input']['completeEmail']['signedDate'])
        self.assertEqual(job['input']['completeEmail']['completeSemanticText'], item()['email']['completeSemanticText'])

    def test_reject_extra_private_public_fields(self):
        p = public()
        p['payout'] = 1
        with self.assertRaises(ValueError):
            a.make_job(item(), p, 'a')

    def test_reject_incomplete_or_extra_email_fields(self):
        for field, value in [('completeSemanticText', ''), ('oldModelAnswer', 'A')]:
            i = item()
            i['email'][field] = value
            with self.assertRaises(ValueError):
                a.make_job(i, public(), 'a')

    def test_selection_is_deterministic_and_score_independent(self):
        items = [item(n, n < 19) for n in range(100)]
        first = [i['caseId'] for i in a.select(items)]
        altered = copy.deepcopy(list(reversed(items)))
        for i in altered:
            i['expected'] = 'OTHER'
            i['metadata']['privateScore'] = 'OTHER'
        second = [i['caseId'] for i in a.select(altered)]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 60)
        self.assertTrue(set(str(n).zfill(3) for n in range(19)).issubset(first))
        self.assertEqual(len({i['metadata']['factKey'] for i in a.select(items)}), 10)

    def test_duplicate_case_rejected(self):
        with self.assertRaises(ValueError):
            a.select([item(), item()], 1)

    def test_exact_quotes_checked_against_correct_sources(self):
        job = a.make_job(item(), public(), 'a')
        o = output()
        self.assertEqual(a.validate_output(o, job), [])
        o['supportingQuotes'] = ['The result is 18.']
        self.assertIn('Non-exact supporting quote', a.validate_output(o, job))
        o = output()
        o['checks'][0]['ruleQuote'] = 'The result is 17.'
        self.assertIn('Non-exact ruleQuote', a.validate_output(o, job))

    def test_unmet_conditions_cannot_authorize_outcome(self):
        o = output()
        o['checks'][0]['state'] = 'MISSING'
        self.assertIn('Settlement despite unmet conditions', a.validate_output(o, a.make_job(item(), public(), 'a')))
        o['settlementOutcome'] = 'INSUFFICIENT'
        self.assertEqual(a.validate_output(o, a.make_job(item(), public(), 'a')), [])

    def test_requires_all_seven_distinct_conditions(self):
        o = output()
        o['checks'][0] = copy.deepcopy(o['checks'][1])
        self.assertIn('Missing or duplicate conditions', a.validate_output(o, a.make_job(item(), public(), 'a')))

    def test_nonbinary_has_same_sufficiency_guard(self):
        o = output()
        o['settlementOutcome'] = 'NONBINARY'
        o['supportingQuotes'] = []
        self.assertIn('Settlement without a supporting quote', a.validate_output(o, a.make_job(item(), public(), 'a')))

    def test_passes_isolated_same_evidence(self):
        ja, jb = [a.make_job(item(), public(), which) for which in ['a', 'b']]
        self.assertEqual(ja['input'], jb['input'])
        self.assertNotEqual(ja['instructions'], jb['instructions'])
        self.assertNotIn('firstPass', str(jb))

    def test_immutable_attempt_marker(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'attempt-started.json'
            a.write_once(p, {'attempt': 1})
            with self.assertRaises(FileExistsError):
                a.write_once(p, {'attempt': 2})
            self.assertEqual(a.q.r.read(p), {'attempt': 1})


if __name__ == '__main__':
    unittest.main()
