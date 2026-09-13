import itertools,unittest
from compact_groups import compact
from round2_matcher import compile_pattern

class GroupCompactionTests(unittest.TestCase):
    def test_preserves_flags_classes_and_escaped_literals(self):
        self.assertEqual(compact(r'(?i)[(?:]+\(\?:a(?:b|c)'),r'(?i)[(?:]+\(\?:a(b|c)')

    def test_does_not_attempt_to_repair_invalid_patterns(self):
        self.assertEqual(compact('(?:('),'(?:(')

    def test_boolean_language_matches_on_exhaustive_small_inputs(self):
        patterns=[r'(?:a|b)+c',r'(?:ab|a){1,3}(?:b|c)?',r'(?i)(?:a(?:b|c)|c)+',r'[(?:]{1,2}(?:a|b)',r'\(\?:a(?:b|c)']
        for pattern in patterns:
            a=compile_pattern(pattern)[0];b=compile_pattern(compact(pattern))[0]
            for n in range(5):
                for chars in itertools.product('abcA():?',repeat=n):
                    text=''.join(chars).encode()
                    self.assertEqual(bool(a.search(text)),bool(b.search(text)),(pattern,text))

if __name__=='__main__':unittest.main()
