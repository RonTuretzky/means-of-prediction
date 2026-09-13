"""Synthetic unit fixtures only; no reserved or candidate data is opened."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from types import SimpleNamespace
import evaluation_core as c
import evaluate


def metadata_source():
    sig = {'domain': 'publisher.example', 'selector': 'news', 'algorithm': 'rsa-sha256', 'format': 'relaxed/relaxed',
           'result': 'pass', 'signedHeaders': 'from:subject:date', 'bodyLengthLimited': False, 'checkedAt': '2030-01-01T13:00:00Z'}
    return {'subject': 'Synthetic test', 'messageDate': '2030-01-01T12:00:00Z', 'receivedAt': '2030-01-01T13:00:00Z',
        'intakeMetadata': {'signatures': [sig]},
        'signedHeaderMetadata': [{'domain': sig['domain'], 'selector': sig['selector'], 'signedHeaderNames': ['from', 'subject', 'date'], 'bodyLengthLimited': False, 'bodyHashMatches': True}],
        'cryptographicVerification': {'rawHashMatchesIntake': True, 'decodedBodyReproduced': True, 'offlineDkimBodyHashRecomputed': True, 'recordedSignatures': [copy.deepcopy(sig)]}}


RAW = b'DKIM-Signature: v=1; a=rsa-sha256; d=publisher.example; s=news; h=from:subject:date; b=synthetic\r\nFrom: writer@publisher.example\r\nDate: Tue, 1 Jan 2030 12:00:00 +0000\r\nSubject: Synthetic test\r\n\r\nBody\r\n'


class EvaluationTests(unittest.TestCase):
    def test_execution_counts_distinguish_missing_usage_from_skipped_calls(self):
        rows = [{'status': 'completed', 'seconds': 1.5, 'usage': {'prompt_tokens': 10, 'completion_tokens': 0}},
                {'status': 'transport_failed', 'seconds': None, 'usage': {}},
                {'status': 'rule_or_html_unavailable'}, {'status': 'full_input_overflow'}]
        summary = c.execution_summary(rows, model_requests=True)
        self.assertEqual(summary['modelRequests'], 2)
        self.assertEqual(summary['attemptedWithoutPromptUsage'], 1)
        self.assertEqual(summary['attemptedWithoutCompletionUsage'], 1)
        self.assertEqual(summary['requestsWithCompletionUsage'], 1)
        self.assertEqual(summary['attemptedWithoutRecordedSeconds'], 1)
        self.assertEqual(summary['knownPromptTokens'], 10)

    def test_execution_invalid_measurements_do_not_become_known_zero(self):
        rows = [{'status': 'failed', 'seconds': True, 'usage': {'prompt_tokens': True, 'completion_tokens': -1}},
                {'status': 'failed', 'seconds': float('nan'), 'usage': None}]
        summary = c.execution_summary(rows, model_requests=True)
        self.assertEqual(summary['attemptedWithoutPromptUsage'], 2)
        self.assertEqual(summary['attemptedWithoutCompletionUsage'], 2)
        self.assertEqual(summary['attemptedWithoutRecordedSeconds'], 2)
        self.assertIsNone(summary['medianRequestSeconds'])

    def test_regex_duration_is_unmeasured_not_a_zero_latency_model_call(self):
        summary = c.execution_summary([{'status': 'completed'}], model_requests=False)
        self.assertEqual(summary['modelRequests'], 0)
        self.assertFalse(summary['matcherDurationMeasured'])
        self.assertNotIn('recordedRequestSeconds', summary)

    def test_duplicate_json_and_nonfinite_are_rejected(self):
        for text in ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.assertRaises(ValueError): c.parse_json(text)

    def test_json_schema_boolean_is_not_integer_or_numeric_enum(self):
        for schema in [{'type': 'integer'}, {'enum': [1]}, {'const': 1}]:
            with self.assertRaises(ValueError): c.validate_schema(True, schema)
        c.validate_schema(None, {'type': ['integer', 'null'], 'minimum': 0})
        with self.assertRaises(ValueError): c.validate_schema(-1, {'type': 'integer', 'minimum': 0})

    def test_schema_refs_required_and_extra_fields(self):
        schema = {'type': 'object', 'properties': {'x': {'$ref': '#/$defs/n'}}, 'required': ['x'], 'additionalProperties': False, '$defs': {'n': {'type': 'integer'}}}
        c.validate_schema({'x': 2}, schema)
        for value in [{}, {'x': '2'}, {'x': 2, 'y': 3}]:
            with self.assertRaises(ValueError): c.validate_schema(value, schema)
        with self.assertRaises(ValueError): c.validate_schema('x', {'pattern': 'x'})

    def test_containment_rejects_traversal_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'root'; root.mkdir()
            (root / 'link').symlink_to(Path(directory))
            for value in ['../outside', '/tmp/outside', 'link/outside', '.']:
                with self.assertRaises(ValueError): c.contained(root, value)
            self.assertEqual(c.contained(root, 'nested/file'), (root / 'nested/file').resolve())

    def test_missing_adapter_prevents_any_reservation_access(self):
        with mock.patch.object(c, 'adapter_gates', side_effect=FileNotFoundError), mock.patch.object(c, 'reservation_gates') as reservation:
            with self.assertRaises(FileNotFoundError): evaluate.gates('test')
            reservation.assert_not_called()

    def test_hash_seal_detects_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'artifact'
            path.write_bytes(b'frozen'); hashes = {'artifact': c.digest(path)}
            c.verify_hashes(root, hashes)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): c.verify_hashes(root, hashes)

    def test_metadata_pass_needs_linked_full_body_verification(self):
        source = metadata_source()
        packet, audit = c.source_metadata(source, RAW)
        self.assertEqual(packet['domain'], 'publisher.example')
        self.assertEqual(packet['signedDate'], '2030-01-01T12:00:00Z')
        self.assertFalse(audit['newRsaVerificationPerformedByEvaluator'])
        for field in ['bodyHashMatches', 'bodyLengthLimited']:
            changed = copy.deepcopy(source)
            changed['signedHeaderMetadata'][0][field] = field == 'bodyLengthLimited'
            self.assertEqual(c.source_metadata(changed, RAW)[0]['domain'], '')

    def test_metadata_duplicate_selector_is_unresolved(self):
        source = metadata_source()
        source['signedHeaderMetadata'].append(copy.deepcopy(source['signedHeaderMetadata'][0]))
        packet, audit = c.source_metadata(source, RAW)
        self.assertEqual(packet['domain'], '')
        self.assertTrue(any('Ambiguous' in x for x in audit['issues']))

    def test_multiple_validated_domains_not_arbitrarily_chosen(self):
        source = metadata_source()
        second = copy.deepcopy(source['intakeMetadata']['signatures'][0]); second['domain'] = 'other.example'
        source['intakeMetadata']['signatures'].append(second)
        source['cryptographicVerification']['recordedSignatures'].append(copy.deepcopy(second))
        meta = copy.deepcopy(source['signedHeaderMetadata'][0]); meta['domain'] = 'other.example'
        source['signedHeaderMetadata'].append(meta)
        raw = b'DKIM-Signature: v=1; a=rsa-sha256; d=other.example; s=news; h=from:subject:date; b=synthetic\r\n' + RAW
        self.assertEqual(c.source_metadata(source, raw)[0]['domain'], '')

    def test_duplicate_date_cannot_be_exposed_as_verified_date(self):
        raw = RAW.replace(b'Subject:', b'Date: Tue, 1 Jan 2030 12:00:00 +0000\r\nSubject:')
        self.assertEqual(c.source_metadata(metadata_source(), raw)[0]['signedDate'], '')
        source = metadata_source(); source['messageDate'] = '2030-01-02T12:00:00Z'
        with self.assertRaises(ValueError): c.source_metadata(source, RAW)

    def test_unsupported_is_not_the_opposite_index(self):
        self.assertEqual(c.layer_expected({'status': 'unsupported', 'outcomeIndex': None}, True), 'NEITHER')
        for status in ['ambiguous', 'unreviewed', 'nonbinary']:
            self.assertIsNone(c.layer_expected({'status': status, 'outcomeIndex': None}))
        with self.assertRaises(ValueError): c.layer_expected({'status': 'unsupported', 'outcomeIndex': 1})
        with self.assertRaises(ValueError): c.layer_expected({'status': 'admissible', 'outcomeIndex': True})

    def test_failures_uncertainty_and_conflicts_remain_visible(self):
        labels = {
            'a': {'coreFact': {'status': 'supported_direct', 'outcomeIndex': 0}},
            'b': {'coreFact': {'status': 'unsupported', 'outcomeIndex': None}},
            'c': {'coreFact': {'status': 'ambiguous', 'outcomeIndex': None}},
            'd': {'coreFact': {'status': 'unsupported', 'outcomeIndex': None}},
        }
        predictions = {'a': {'valid': False}, 'b': {'valid': True, 'factualOutcome': 'CONFLICT'},
                       'c': {'valid': True, 'factualOutcome': 'A'}, 'd': {'valid': True, 'factualOutcome': 'NEITHER'}}
        result = c.score_layer(predictions, labels, 'coreFact', 'factualOutcome')
        self.assertEqual(result['supported_direct']['unscorable'], 1)
        self.assertEqual(result['supported_direct']['fullEligibleDenominator'], 1)
        self.assertEqual(result['supported_direct']['correctFullEligibleNumerator'], 0)
        self.assertEqual(result['ambiguous']['fullEligibleDenominator'], 0)
        self.assertEqual(result['ambiguous']['exclusiveClaims'], 1)
        self.assertEqual(result['unsupported']['anyPredicateClaimIncludingConflict'], 1)
        self.assertEqual(result['unsupported']['correctFullEligibleNumerator'], 1)

    def test_four_predicate_masks(self):
        self.assertEqual([c.decision(x) for x in [[True, False], [False, True], [False, False], [True, True]]], ['A', 'B', 'NEITHER', 'CONFLICT'])
        with self.assertRaises(ValueError): c.decision([1, False])

    def test_unicode_canonical_hash_preserves_original_bytes_and_order(self):
        question = {'marketId': 'test', 'question': 'Café?', 'rules': 'Full\r\nrule', 'outcomeLabels': ['Y', 'N']}
        self.assertNotEqual(c.sha(c.canonical(question)), c.sha(c.canonical({**question, 'rules': 'Full\nrule'})))
        self.assertNotEqual(c.sha(c.canonical(question)), c.sha(c.canonical({**question, 'outcomeLabels': ['N', 'Y']})))
        self.assertEqual(c.pair_id('raw', 'market'), c.sha(b'raw\0market'))

    def test_annotation_binding_and_unicode_evidence_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text = 'A🦊B\r\nCafé'; (root / 'text.txt').write_bytes(text.encode('utf-8'))
            question = {'marketId': 'test-only', 'question': 'Synthetic?', 'rules': 'Synthetic rule', 'outcomeLabels': ['First', 'Second']}
            source = {'rawSha256': c.sha(b'raw test email'), 'emailKey': 'synthetic', 'decodedTextPath': 'text.txt'}
            row = {'pairId': c.pair_id(source['rawSha256'], question['marketId']), 'emailSha256': source['rawSha256'],
                'emailKey': source['emailKey'], 'marketId': question['marketId'], 'questionOrdinal': 1,
                'questionSha256': c.sha(c.canonical(question)), 'ruleSha256': c.sha(question['rules'].encode()),
                'annotationAuthority': c.AUTHORITY, 'noCandidateExecution': True, 'noOldFixtureLabelsUsed': True,
                'coreFact': {'status': 'supported_direct', 'outcomeIndex': 0, 'evidence': [{'sourcePath': 'text.txt', 'startCharacter': 1, 'endCharacter': 2, 'text': '🦊', 'textSha256': c.sha('🦊'.encode())}]},
                'originalRuleSettlement': {'status': 'unsupported', 'outcomeIndex': None, 'nonbinaryOutcome': None}, 'reviewStatus': 'reviewed'}
            check = lambda rows: c.verify_annotations(rows, [question], [source], {'type': 'object'}, root)
            check([row])
            changed = copy.deepcopy(row); changed['coreFact']['evidence'][0]['endCharacter'] = 5
            with self.assertRaises(ValueError): check([changed])
            changed = copy.deepcopy(row); changed['questionSha256'] = c.sha(b'wrong question')
            with self.assertRaises(ValueError): check([changed])
            with self.assertRaises(ValueError): check([])
            with self.assertRaises(ValueError): check([row, row])

    def test_unreviewed_and_nonbinary_annotations_require_explicit_mapping(self):
        layer = {'status': 'nonbinary', 'outcomeIndex': None}
        self.assertIsNone(c.layer_expected(layer))
        with self.assertRaises(ValueError): c.layer_expected({**layer, 'outcomeIndex': 0})
        with self.assertRaises(ValueError): c.layer_expected(layer, core=True)

    def test_preflight_rejects_changed_allowance_and_overflow_flag(self):
        q = SimpleNamespace(verify_preflight_runtime=lambda p, r: None)
        runtime = {'identifier': 'synthetic-instance'}
        requests = {'test': {'max_tokens': 20}}
        preflight = {'identifier': 'synthetic-instance', 'contextLength': 100, 'allFullInputsFit': True,
            'counts': [{'caseId': 'test', 'inputTokens': 80, 'outputAllowance': 20, 'fits': True}]}
        evaluate.validate_preflight(preflight, runtime, requests, q)
        for field, value in [('inputTokens', 81), ('outputAllowance', 19), ('fits', 1)]:
            changed = copy.deepcopy(preflight); changed['counts'][0][field] = value
            with self.assertRaises(ValueError): evaluate.validate_preflight(changed, runtime, requests, q)
        overflow = copy.deepcopy(preflight)
        overflow['counts'][0].update(inputTokens=81, fits=False); overflow['allFullInputsFit'] = False
        self.assertFalse(evaluate.validate_preflight(overflow, runtime, requests, q)['test']['fits'])
        changed = copy.deepcopy(preflight); changed['counts'].append(changed['counts'][0])
        with self.assertRaises(ValueError): evaluate.validate_preflight(changed, runtime, requests, q)

    def test_cached_live_module_cannot_replace_sealed_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'sealed-source').mkdir()
            (root / 'sealed-source/qwen_round1.py').write_text('# synthetic module\n')
            cached = SimpleNamespace(__file__=str(root / 'live/qwen_round1.py'))
            with mock.patch.object(c, 'QWEN', root), mock.patch.dict(evaluate.sys.modules, {'qwen_round1': cached}), mock.patch.object(evaluate.sys, 'path', list(evaluate.sys.path)):
                with self.assertRaises(ValueError): evaluate.qwen_module()

    def test_absent_oversigned_headers_differ_from_selected_intake_list(self):
        source = metadata_source()
        names = ['from', 'subject', 'date', 'from', 'subject', 'to', 'to']
        source['signedHeaderMetadata'][0]['signedHeaderNames'] = names
        raw = RAW.replace(b'h=from:subject:date;', b'h=from:subject:date:from:subject:to:to;')
        packet, audit = c.source_metadata(source, raw)
        self.assertEqual(packet['domain'], 'publisher.example')
        self.assertEqual(packet['signedDate'], '2030-01-01T12:00:00Z')
        self.assertEqual(audit['priorRecordedSignaturePassesLinked'], 1)
        changed = raw.replace(b'\r\nFrom:', b'\r\nSubject: Added field\r\nFrom:')
        self.assertEqual(c.source_metadata(source, changed)[0]['domain'], '')

    def test_current_signature_is_excluded_from_h_occurrence_consumption(self):
        headers = c.email.parser.BytesHeaderParser(policy=c.email.policy.default).parsebytes(RAW)
        self.assertEqual(c.selected_signed_headers(['dkim-signature', 'subject', 'subject'], headers), ['subject'])
        with self.assertRaises(ValueError): c.dkim_tags('d=one.example; d=two.example')


if __name__ == '__main__':
    unittest.main()
