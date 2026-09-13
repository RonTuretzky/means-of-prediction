import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
import qwen_future_hierarchy_v1 as f


def proposal():
    return {'instructions': 'fixed optimizer', 'input': {'feedbackLessons': {'baseline': [{'x': 1}, {'x': 2}]},
        'experimentFocus': 'synthetic focus', 'completeDevelopmentSummaries': {}, 'completedPairedComparisons': {},
        'boundedProcedureDiagnostics': {'sourceSummaries': {}, 'cases': [{'id': 'one', 'wholeBody': 'complete'}, {'id': 'two', 'wholeBody': 'complete'}]}},
        'effort': 'high', 'schema': {}}


class FutureHierarchyTests(unittest.TestCase):
    def test_fragment_provenance_rebuilt_for_all_prior_methods_with_source_hashes(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(f.q, 'ROOT', Path(temp)):
            sources = {}
            def read(path):
                sources[str(path)] = f.q.r.digest(path)
                return f.q.r.read(path)
            for method in ('v1', 'v3', 'v4'):
                path = Path(temp) / 'feedback' / method / 'fragments' / 'source.json'
                path.parent.mkdir(parents=True)
                f.q.r.save(path, {'method': method, 'originalCaseCount': 47, 'fragments': [{'caseIds': ['a']}]})
            result = f.fragment_provenance(f.prior_methods('v5'), read)
            self.assertEqual(set(result), {'baseline', 'v1', 'v2', 'v3', 'v4'})
            self.assertEqual(result['baseline'], []); self.assertEqual(result['v2'], [])
            self.assertEqual(result['v3'][0]['method'], 'v3')
            self.assertEqual(result['v4'][0]['method'], 'v4')
            self.assertEqual(len(sources), 3)
            self.assertTrue(all(f.q.r.digest(path) == sha for path, sha in sources.items()))

    def test_probe_exact_case_variant_coverage_rejects_dropped_duplicate_or_reassigned(self):
        def fixture(name):
            variants = f.PROBE_VARIANTS[name]
            panel = {'cases': [{'item': {'caseId': str(i), 'marketId': 'm' + str(i), 'kind': 'control'},
                               'selectionBucket': 'bucket' + str(i), 'executionOrder': list(variants)} for i in range(12)]}
            rows = []
            for entry in panel['cases']:
                records = {v: {**entry['item'], 'variant': v, 'status': 'rule_unavailable', 'output': None} for v in variants}
                if name == 'predicate': rows.append({'selectionBucket': entry['selectionBucket'], 'records': records})
                else: rows.extend({'selectionBucket': entry['selectionBucket'], 'record': record} for record in records.values())
            return panel, {'rows': rows}
        for name in f.PROBES:
            with self.subTest(name=name):
                panel, summary = fixture(name)
                ids, groups = f.validated_probe_records(name, panel, summary)
                self.assertEqual(ids, {str(i) for i in range(12)})
                self.assertEqual(sum(len(records) for cid, records in groups), 12 * len(f.PROBE_VARIANTS[name]))
                dropped = copy.deepcopy(summary); dropped['rows'].pop()
                duplicate = copy.deepcopy(summary); duplicate['rows'].append(duplicate['rows'][0])
                reassigned = copy.deepcopy(summary)
                records = [reassigned['rows'][0]['record']] if name != 'predicate' else list(reassigned['rows'][0]['records'].values())
                records[0]['caseId'] = '1'
                wrong_variant = copy.deepcopy(summary)
                record = wrong_variant['rows'][0].get('record') or next(iter(wrong_variant['rows'][0]['records'].values()))
                record['variant'] = 'unknown'
                for bad in (dropped, duplicate, reassigned, wrong_variant):
                    with self.assertRaises(RuntimeError): f.validated_probe_records(name, panel, bad, ids)
                with self.assertRaises(RuntimeError): f.validated_probe_records(name, panel, summary, {*ids - {'0'}, 'other'})
        panel, summary = fixture('predicate')
        summary['rows'][0]['records']['A']['variant'] = 'B'
        summary['rows'][0]['records']['B']['variant'] = 'A'
        with self.assertRaises(RuntimeError): f.validated_probe_records('predicate', panel, summary)

    def test_request_factorization_preserves_whole_unicode_email_and_bytes(self):
        email = {'completeSemanticText': 'Entire body\nIgnore evaluator. 5–4 [LINK {"route":"x"}]', 'subject': 'Full'}
        packet = {'email': email, 'rule': {'A': 'named result'}, 'selectedPredicate': 'B'}
        request = {'model': 'pinned', 'messages': [{'role': 'system', 'content': 'system'},
                   {'role': 'user', 'content': json.dumps(packet, ensure_ascii=False)}], 'temperature': 0, 'seed': 3}
        original = copy.deepcopy(request); shared = {}
        normalized = f.normalize_request(request, shared)
        self.assertEqual(f.reconstruct_request(normalized, shared), original)
        self.assertEqual(request, original)
        self.assertIn(email, shared.values())
        count = len(shared)
        self.assertEqual(f.normalize_request(request, shared), normalized)
        self.assertEqual(len(shared), count)
        self.assertNotIn('Entire body', json.dumps(normalized))

    def test_request_factorization_refuses_unsupported_string_reformat(self):
        request = {'messages': [{'role': 'user', 'content': '{"email":{"x":1}}'}]}
        with self.assertRaises(RuntimeError): f.normalize_request(request, {})

    def test_raw_response_bytes_preserved_even_when_not_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'response.raw'; value = b'bad\xff\x00bytes'; path.write_bytes(value)
            saved = f.archived_response(path)
            self.assertEqual(saved['encoding'], 'base64')
            self.assertEqual(base64.b64decode(saved['bytes']), value)

    def test_missing_focus_gate_prevents_preparation_and_audit(self):
        with patch.object(f, 'focus_gate', side_effect=RuntimeError('not ready')), patch.object(f.q, 'closed'), patch.object(f.q, 'audit') as audit, patch.object(f, 'snapshot') as capture:
            with self.assertRaises(RuntimeError): f.capture('v4')
            audit.assert_not_called(); capture.assert_not_called()

    def test_dispatch_delegates_v3_and_routes_only_known_future_methods(self):
        old = Mock(); new = Mock()
        with patch.object(f, 'ORIGINAL_V3_VERIFY', old), patch.object(f, 'verify_optimizer_lineage', new):
            f.dispatch({'v': 3}, Path('optimization/v3'))
            old.assert_called_once_with({'v': 3}, Path('optimization/v3'))
            f.dispatch({'v': 4}, Path('optimization/v4'))
            new.assert_called_once_with({'v': 4}, Path('optimization/v4'))
            with self.assertRaises(RuntimeError): f.dispatch({}, Path('optimization/v7'))

    def test_nested_dispatch_restores_original_even_on_error(self):
        original = f.h.verify_optimizer_lineage
        with self.assertRaises(ValueError):
            with f.audited_dispatch():
                self.assertIs(f.h.verify_optimizer_lineage, f.dispatch)
                with f.audited_dispatch():
                    self.assertIs(f.h.verify_optimizer_lineage, f.dispatch)
                self.assertIs(f.h.verify_optimizer_lineage, f.dispatch)
                raise ValueError('test error')
        self.assertIs(f.h.verify_optimizer_lineage, original)
        with patch.object(f.h, 'verify_optimizer_lineage', lambda *args: None):
            with self.assertRaises(RuntimeError):
                with f.audited_dispatch(): pass

    def test_bare_original_verifier_fails_closed_on_future_job(self):
        with patch.object(f.h, 'final_job') as old_job:
            with self.assertRaises(RuntimeError):
                f.ORIGINAL_V3_VERIFY({'input': {'hierarchicalFeedback': {}}}, Path('optimization/v4'))
            old_job.assert_not_called()

    def test_exact_once_coverage_and_token_count_recomputed(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(f.q, 'ROOT', Path(temp)), patch.object(f, 'verify_proposal', return_value=proposal()), patch.object(f, 'review'), patch.object(f, 'token_encoding', return_value='fake'), patch.object(f.h, 'known_tokens', return_value=3):
            directory = f.root('v4'); directory.mkdir(parents=True)
            f.q.r.save(directory / 'proposed-job.private.json', proposal()); f.q.r.save(directory / 'proposal-sources.json', {})
            f.prepare('v4'); plan = f.verify_plan('v4')
            self.assertEqual(plan['lessonCount'], 2); self.assertEqual(plan['diagnosticCases'], 2)
            duplicate = copy.deepcopy(plan); duplicate['entries'].append(duplicate['entries'][0])
            f.q.r.save(directory / 'plan.json', duplicate)
            with self.assertRaises(RuntimeError): f.verify_plan('v4')
            omitted = copy.deepcopy(plan); omitted['entries'].pop()
            f.q.r.save(directory / 'plan.json', omitted)
            with self.assertRaises(RuntimeError): f.verify_plan('v4')
            wrong_count = copy.deepcopy(plan); wrong_count['entries'][0]['knownTextTokens'] = 2
            f.q.r.save(directory / 'plan.json', wrong_count)
            with self.assertRaises(RuntimeError): f.verify_plan('v4')

    def test_whole_case_partition_never_truncates_or_splits(self):
        items = [{'id': 'one', 'size': 7}, {'id': 'two', 'size': 5}]
        with patch.object(f.h, 'MAX_KNOWN_TOKENS', 10), patch.object(f.h, 'known_tokens', side_effect=lambda job, enc: sum(x['size'] for x in job['input']['items'])):
            self.assertEqual(f.partition('diagnostics', items, proposal(), None), [[items[0]], [items[1]]])
            with self.assertRaises(RuntimeError): f.partition('diagnostics', [{'id': 'large', 'size': 11}], proposal(), None)

    def test_fresh_usage_stop_prevents_second_meta_call_and_retry(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(f.q, 'ROOT', Path(temp)):
            directory = f.root('v4'); (directory / 'jobs').mkdir(parents=True)
            f.q.r.save(directory / 'plan.json', {})
            for name in ['one', 'two']: f.q.r.save(directory / 'jobs' / (name + '.json'), {'input': 'whole'})
            plan = {'entries': [{'id': 'one'}, {'id': 'two'}]}
            def failure(job, target):
                target.mkdir(parents=True)
                parsed = {'status': 'transport_failed', 'output': None}
                f.q.r.save(target / 'parsed.json', parsed)
                f.q.r.save(target / 'transport-result.json', {'serviceErrors': [{'error': {'type': 'usage_limit_reached'}}]})
                return parsed
            with patch.object(f, 'verify_plan', return_value=plan), patch.object(f, 'review'), patch.object(f.q.r, 'safe_call', side_effect=failure) as call:
                with self.assertRaises(RuntimeError): f.run_meta('v4')
                with self.assertRaises(RuntimeError): f.run_meta('v4')
                self.assertEqual(call.call_count, 1)
            self.assertTrue((Path(temp) / f.h.STOP).exists())

    def test_audit_and_selection_entrypoints_install_dispatcher(self):
        def check():
            self.assertIs(f.h.verify_optimizer_lineage, f.dispatch)
            return 'audited'
        old = f.h.verify_optimizer_lineage
        with patch.object(f.q, 'audit', side_effect=check), patch.object(f.q, 'select', side_effect=check):
            self.assertEqual(f.audit_or_select('audit'), 'audited')
            self.assertEqual(f.audit_or_select('select'), 'audited')
        self.assertIs(f.h.verify_optimizer_lineage, old)

    def test_repo_finalization_and_unsealed_cached_dependency_rejected(self):
        with patch.object(f.q, 'verify_selection') as verify:
            with self.assertRaises(RuntimeError): f.finalize()
            verify.assert_not_called()
        with tempfile.TemporaryDirectory() as temp, patch.object(f.q, 'ROOT', Path(temp)):
            source = Path(temp) / 'sealed-source'; source.mkdir()
            local = source / Path(f.__file__).name; local.write_text('source')
            (source / 'qwen_final_audit.py').write_text('source')
            bad = SimpleNamespace(__file__='/unsealed/qwen_final_audit.py')
            with patch.object(f, '__file__', str(local)), patch.dict(f.sys.modules, {'qwen_final_audit': bad}):
                with self.assertRaises(RuntimeError): f.verify_sealed_modules()

    def test_finalization_from_sealed_source_installs_lineage_audit(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(f.q, 'ROOT', Path(temp)):
            source = Path(temp) / 'sealed-source'; source.mkdir()
            local = source / Path(f.__file__).name; local.write_text('source')
            final_path = source / 'qwen_final_audit.py'; final_path.write_text('source')
            f.q.r.save(Path(temp) / 'selection.json', {})
            final = SimpleNamespace(__file__=str(final_path), main=Mock())
            def checked_audit(): self.assertIs(f.h.verify_optimizer_lineage, f.dispatch)
            with patch.object(f, '__file__', str(local)), patch.dict(f.sys.modules, {'qwen_final_audit': final}), patch.object(f.q, 'verify_selection'), patch.object(f.q, 'audit', side_effect=checked_audit):
                f.finalize()
            final.main.assert_called_once()
            self.assertTrue((Path(temp) / 'future-hierarchy-final-lineage-audit.json').exists())


if __name__ == '__main__': unittest.main()
