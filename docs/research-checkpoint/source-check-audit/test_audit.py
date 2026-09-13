import unittest
import audit


class ReconciliationTests(unittest.TestCase):
    def test_strict_is_independent_of_factual(self):
        self.assertEqual(audit.strict({'outcomeA':'NO','outcomeB':'YES','factualOutcome':'A'}),'B')
        self.assertEqual(audit.strict({'outcomeA':'YES','outcomeB':'YES'}),'CONFLICT')

    def test_missing_cost_is_not_zero_cost(self):
        self.assertEqual(audit.known([12,None,float('nan')]),{'knownTotal':12,'missingOrInvalid':2,'isLowerBound':True})

    def test_insufficient_is_not_no(self):
        labels=[{'caseId':'a','reviewStatus':'adjudicated','settlementOutcome':'INSUFFICIENT'}]
        result=audit.measure(labels,{'a':'B'})
        self.assertEqual(result['directionalOrConflictingOutputsOnInsufficientPairs'],1)
        self.assertIsNone(result['recoveryAmongAnswerable'])

    def test_failures_remain_answerable_denominator(self):
        labels=[{'caseId':str(i),'reviewStatus':'adjudicated','settlementOutcome':'A'} for i in range(2)]
        result=audit.measure(labels,{'0':'A','1':'UNSCORABLE'})
        self.assertEqual(result['recoveryAmongAnswerable'],0.5)
        self.assertEqual(result['executionFailure'],1)

    def test_unresolved_cannot_be_answerable(self):
        labels=[{'caseId':'a','reviewStatus':'unresolved','settlementOutcome':'AMBIGUOUS'}]
        result=audit.measure(labels,{'a':'A'})
        self.assertEqual(result['unresolvedPairs'],1)
        self.assertEqual(result['answerablePairs'],0)


if __name__=='__main__':unittest.main()
