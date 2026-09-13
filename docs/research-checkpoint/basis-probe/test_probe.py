import copy
import json
import tempfile
import unittest
from pathlib import Path
import probe as p

Q = p.o.study_module()


def request():
    return {'model': 'synthetic-pinned', 'messages': [
        {'role': 'system', 'content': 'Synthetic instructions.'},
        {'role': 'user', 'content': 'Full inert input with Café and 5 + 4.'}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'test', 'strict': True,
            'schema': copy.deepcopy(Q.JUDGE_SCHEMA)}}, 'temperature': 0, 'seed': 20260912, 'max_tokens': 2048}


def output():
    return {'decisionBasis': {'sourceQuote': '5 + 4', 'entity': 'Synthetic game', 'quantity': '9 runs', 'comparison': '5 + 4 = 9 > 6.5'},
            'factualOutcome': 'B', 'outcomeA': 'NO', 'outcomeB': 'YES', 'evidenceQuote': '5 + 4', 'missingConditions': []}


class ProbeTests(unittest.TestCase):
    def test_original_request_is_byte_identical(self):
        original = request()
        self.assertEqual(p.o.wire(original), p.o.wire(p.request_for(original, 'original')))

    def test_only_declared_schema_and_system_appendix_change(self):
        original = request(); before = copy.deepcopy(original)
        changed = p.request_for(original, 'basis-first')
        self.assertEqual(original, before)
        self.assertEqual(changed['messages'][1], original['messages'][1])
        self.assertEqual(changed['messages'][0]['content'], original['messages'][0]['content'] + p.APPENDIX)
        schema = changed['response_format']['json_schema']['schema']
        self.assertEqual(list(schema['properties']), ['decisionBasis', *p.FIELDS])
        for key in p.FIELDS:
            self.assertEqual(schema['properties'][key], Q.JUDGE_SCHEMA['properties'][key])
        for key in ['model', 'temperature', 'seed', 'max_tokens']:
            self.assertEqual(changed[key], original[key])

    def test_invalid_baseline_order_and_variant_refused(self):
        original = request()
        original['response_format']['json_schema']['schema']['required'] = list(reversed(p.FIELDS))
        with self.assertRaises(RuntimeError): p.request_for(original, 'basis-first')
        with self.assertRaises(RuntimeError): p.request_for(request(), 'unknown')

    def test_unknown_observations_can_be_null(self):
        value = output()
        value['decisionBasis'] = {'sourceQuote': '', 'entity': None, 'quantity': None, 'comparison': None}
        self.assertTrue(p.valid(value, 'basis-first', Q))

    def test_schema_types_limits_and_exact_keys_are_enforced(self):
        for key, bad in [('sourceQuote', None), ('entity', 4), ('quantity', True), ('comparison', [])]:
            value = output(); value['decisionBasis'][key] = bad
            self.assertFalse(p.valid(value, 'basis-first', Q))
        for key in p.BASIS_FIELDS:
            value = output(); value['decisionBasis'][key] = 'é' * (p.LIMITS[key] + 1)
            self.assertFalse(p.valid(value, 'basis-first', Q))
        value = output(); value['decisionBasis']['extra'] = 'x'
        self.assertFalse(p.valid(value, 'basis-first', Q))

    def test_intervention_and_original_schemas_cannot_be_swapped(self):
        value = output()
        self.assertFalse(p.valid(value, 'original', Q))
        del value['decisionBasis']
        self.assertTrue(p.valid(value, 'original', Q))
        self.assertFalse(p.valid(value, 'basis-first', Q))

    def test_basis_never_corrects_a_wrong_final_side(self):
        record = {'status': 'completed', 'variant': 'basis-first', 'output': output()}
        before = copy.deepcopy(record)
        normalized = p.scoring_record(record, Q)
        self.assertEqual(Q.settlement(normalized['output']), 'B')
        self.assertEqual(record, before)
        self.assertEqual(normalized['output'], {key: record['output'][key] for key in p.FIELDS})

    def test_invalid_basis_cannot_earn_a_valid_score(self):
        value = output(); value['decisionBasis']['quantity'] = 9
        normalized = p.scoring_record({'status': 'completed', 'variant': 'basis-first', 'output': value}, Q)
        self.assertEqual(normalized['status'], 'failed')
        self.assertIsNone(normalized['output'])

    def test_capped_calls_cannot_be_rescued_by_valid_json(self):
        normalized = p.scoring_record({'status': 'failed', 'variant': 'basis-first', 'output': output()}, Q)
        self.assertEqual(normalized['status'], 'failed')
        self.assertIsNone(normalized['output'])

    def test_actual_nested_field_order_is_measured(self):
        record = {'variant': 'basis-first', 'output': output(), 'outputFieldOrder': ['decisionBasis', *p.FIELDS]}
        self.assertTrue(p.order_matches(record))
        record['output']['decisionBasis'] = dict(reversed(list(record['output']['decisionBasis'].items())))
        self.assertFalse(p.order_matches(record))
        self.assertTrue(p.valid(record['output'], 'basis-first', Q))

    def raw_fixture(self, directory, finish='length', content=None, model='pinned', rejection=False):
        value = output()
        if content is None: content = json.dumps(value)
        raw = {'error': {'message': 'rejected'}} if rejection else {'model': model, 'usage': {'prompt_tokens': 50, 'completion_tokens': 2048},
            'choices': [{'finish_reason': finish, 'message': {'content': content}}]}
        (directory / 'response.raw').write_text(json.dumps(raw))
        (directory / 'response.json').write_text(json.dumps(raw))
        try: parsed = None if rejection else json.loads(content)
        except ValueError: parsed = None
        status = 'completed' if not rejection and finish == 'stop' and p.valid(parsed, 'basis-first', Q) else 'failed'
        return {'variant': 'basis-first', 'status': status, 'output': parsed, 'httpStatus': 400 if rejection else 200,
            'rawResponseSha256': p.o.digest(directory / 'response.raw'), 'finishReason': None if rejection else finish,
            'usage': raw.get('usage'), 'returnedModel': raw.get('model'), 'reasoningCharacters': 0,
            'outputFieldOrder': list(parsed) if isinstance(parsed, dict) else None}

    def test_capped_raw_usage_and_model_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); record = self.raw_fixture(directory)
            p.validate_raw_record(record, directory, 'pinned', Q)
            for field, bad in [('usage', {'prompt_tokens': 0}), ('returnedModel', 'other'), ('finishReason', 'stop'), ('status', 'completed')]:
                changed = copy.deepcopy(record); changed[field] = bad
                with self.assertRaises(RuntimeError): p.validate_raw_record(changed, directory, 'pinned', Q)

    def test_incomplete_output_remains_failed_with_known_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); record = self.raw_fixture(directory, content='{"decisionBasis":')
            self.assertIsNone(record['output']); self.assertEqual(record['status'], 'failed')
            p.validate_raw_record(record, directory, 'pinned', Q)
            self.assertEqual(record['usage']['completion_tokens'], 2048)

    def test_rejections_allow_absent_usage_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); record = self.raw_fixture(directory, rejection=True)
            p.validate_raw_record(record, directory, 'pinned', Q)
            self.assertIsNone(record['usage']); self.assertIsNone(record['returnedModel'])
            record['usage'] = {'prompt_tokens': 0}
            with self.assertRaises(RuntimeError): p.validate_raw_record(record, directory, 'pinned', Q)

    def test_wrong_model_on_failed_call_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); record = self.raw_fixture(directory, model='different')
            with self.assertRaises(RuntimeError): p.validate_raw_record(record, directory, 'pinned', Q)

    def test_success_cannot_be_relabelled_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); record = self.raw_fixture(directory, finish='stop')
            p.validate_raw_record(record, directory, 'pinned', Q)
            record['status'] = 'failed'
            with self.assertRaises(RuntimeError): p.validate_raw_record(record, directory, 'pinned', Q)

    def test_unparseable_response_preserves_missing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp); (directory / 'response.raw').write_bytes(b'Not JSON')
            record = {'status': 'transport_failed', 'output': None, 'rawResponseSha256': p.o.digest(directory / 'response.raw')}
            p.validate_raw_record(record, directory, 'pinned', Q)
            record['returnedModel'] = 'pinned'
            with self.assertRaises(RuntimeError): p.validate_raw_record(record, directory, 'pinned', Q)


if __name__ == '__main__':
    unittest.main()
