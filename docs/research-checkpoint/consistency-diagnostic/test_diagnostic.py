import unittest
import diagnostic as d
class PolicyTests(unittest.TestCase):
 def out(self,missing=None,quote='fact',a='YES',b='NO'):
  return dict(factualOutcome='A',outcomeA=a,outcomeB=b,evidenceQuote=quote,missingConditions=[] if missing is None else missing)
 def test_exact_and_empty(self):self.assertEqual(d.decisions('completed',self.out(),'fact')['exact_quote_empty_missing'],'A')
 def test_missing_rejects_even_if_other_branch(self):self.assertEqual(d.decisions('completed',self.out(['Only B source unavailable']),'fact')['exact_quote_empty_missing'],'NEITHER')
 def test_whitespace_quote_exact_not_normalized(self):self.assertEqual(d.decisions('completed',self.out(quote='fact '),'fact')['exact_quote_empty_missing'],'NEITHER')
 def test_empty_quote_rejects(self):self.assertEqual(d.decisions('completed',self.out(quote=''),'fact')['exact_quote_empty_missing'],'NEITHER')
 def test_blank_entry_is_nonempty_list(self):self.assertEqual(d.decisions('completed',self.out(['']),'fact')['exact_quote_empty_missing'],'NEITHER')
 def test_conflict_remains_diagnostic_not_direction(self):self.assertEqual(d.decisions('completed',self.out(b='YES'),'fact')['exact_quote_empty_missing'],'CONFLICT')
 def test_failure_not_safe_rejection(self):
  r={'expected':'INSUFFICIENT','decisions':d.decisions('rule_unavailable',None,'')};m=d.metrics([r],'exact_quote_empty_missing')
  self.assertEqual((m['failures'],m['negativeRejections'],m['negativeCompleted']),(1,0,0))
 def test_wrong_side_and_positive_recovery(self):
  rows=[{'expected':e,'decisions':{p:x for p in d.POLICIES}} for e,x in [('A','A'),('A','B'),('B','NEITHER'),('B','UNSCORABLE')]]
  m=d.metrics(rows,'raw');self.assertEqual((m['positiveTotal'],m['positiveCompleted'],m['correctPositive'],m['wrongSidePositive'],m['positiveAbstentions'],m['failures']),(4,3,1,1,1,1))
if __name__=='__main__':unittest.main()
