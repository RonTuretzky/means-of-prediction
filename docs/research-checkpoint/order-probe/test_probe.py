import copy
import json
import unittest
from types import SimpleNamespace
import probe as p


def example():
    fields = {key: {'type': 'string'} for key in p.ORIGINAL_ORDER}
    fields['missingConditions'] = {'type': 'array', 'items': {'type': 'string'}}
    return {'model': 'unit', 'messages': [{'role': 'user', 'content': 'Complete example body. Café.'}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'test', 'strict': True,
                'schema': {'type': 'object', 'properties': fields, 'required': p.ORIGINAL_ORDER.copy(), 'additionalProperties': False}}},
            'temperature': 0, 'seed': 20260912, 'max_tokens': 2048}


class ProbeTests(unittest.TestCase):
    def test_original_wire_identical(self):
        source = example()
        self.assertEqual(p.wire(source), p.wire(p.reorder(source, 'original')))

    def test_quote_first_changes_only_order(self):
        source = example()
        preserved = copy.deepcopy(source)
        altered = p.reorder(source, 'quote-first')
        self.assertEqual(source, preserved)
        a = altered['response_format']['json_schema']['schema']
        b = source['response_format']['json_schema']['schema']
        self.assertEqual(list(a['properties']), p.QUOTE_ORDER)
        self.assertEqual(a['required'], p.QUOTE_ORDER)
        self.assertEqual(a['properties'], b['properties'])
        self.assertEqual(set(a['required']), set(b['required']))
        self.assertEqual(altered['messages'], source['messages'])
        self.assertNotEqual(p.wire(altered), p.wire(source))

    def test_canonical_hash_cannot_detect_properties_only_order(self):
        source = example()
        altered = copy.deepcopy(source)
        schema = altered['response_format']['json_schema']['schema']
        schema['properties'] = {key: schema['properties'][key] for key in p.QUOTE_ORDER}
        self.assertEqual(json.dumps(altered, sort_keys=True), json.dumps(source, sort_keys=True))
        self.assertNotEqual(p.wire(altered), p.wire(source))

    def test_unexpected_order_rejected(self):
        source = example()
        source['response_format']['json_schema']['schema']['required'] = p.QUOTE_ORDER
        with self.assertRaises(RuntimeError):
            p.reorder(source, 'quote-first')

    def test_missing_and_invalid_measurements_are_unknown(self):
        for value in [None, True, -1, float('nan'), float('inf'), '2']:
            self.assertFalse(p.known(value))
        self.assertTrue(p.known(0))
        self.assertTrue(p.known(1.5))

    def test_response_identity_and_reasoning_bind_to_raw(self):
        raw = {'model': 'pinned', 'choices': [{'message': {'reasoning_content': 'abc'}}]}
        row = {'returnedModel': 'pinned', 'reasoningCharacters': 3}
        p.validate_response_metadata(row, raw, 'pinned')
        with self.assertRaises(RuntimeError):
            p.validate_response_metadata(row, raw, 'different')
        with self.assertRaises(RuntimeError):
            p.validate_response_metadata({**row, 'reasoningCharacters': 2}, raw, 'pinned')

    def test_ignored_order_intervention_is_visible(self):
        self.assertTrue(p.requested_order_matches({'variant': 'original', 'outputFieldOrder': p.ORIGINAL_ORDER}))
        self.assertTrue(p.requested_order_matches({'variant': 'quote-first', 'outputFieldOrder': p.QUOTE_ORDER}))
        self.assertFalse(p.requested_order_matches({'variant': 'quote-first', 'outputFieldOrder': p.ORIGINAL_ORDER}))

    def test_replay_reports_factual_and_status_changes(self):
        q = SimpleNamespace(settlement=lambda output: output['strict'])
        old = {'caseId': 'x', 'status': 'completed', 'output': {'strict': 'A', 'factualOutcome': 'A'}}
        new = {**old, 'output': {'strict': 'A', 'factualOutcome': 'NEITHER'}}
        report = p.replay_agreement(new, old, q)
        self.assertTrue(report['sameStatus'])
        self.assertTrue(report['sameSettlement'])
        self.assertFalse(report['sameFactualOutcome'])
        failed = {**old, 'status': 'failed', 'output': None}
        report = p.replay_agreement(failed, old, q)
        self.assertFalse(report['sameStatus'])
        self.assertIsNone(report['sameFactualOutcome'])
        self.assertIsNone(report['sameCanonicalJson'])


if __name__ == '__main__':
    unittest.main()
