import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import qwen_hierarchical_optimizer as h


def proposal():
    contexts = [{'item': {'caseId': cid}, 'complete': 'whole original body'} for cid in ['a', 'b']]
    return {'input': {'feedbackLessons': {'baseline': [{'lesson': 'one'}, {'lesson': 'two'}]},
        'experimentFocus': 'compact', 'completeDevelopmentSummaries': {}, 'completedPairedComparisons': {},
        'boundedProcedureDiagnostics': {'completeContexts': contexts,
            'orderSummary': {'rows': [{'record': {'caseId': cid, 'variant': variant}} for cid in ['a', 'b'] for variant in ['original', 'quote-first']]},
            'splitSummary': {'rows': [{'score': {'caseId': cid}, 'records': {'A': {}, 'B': {}}} for cid in ['a', 'b']]},
            'scope': 'diagnostic', 'orderProtocol': {}, 'splitProtocol': {}, 'splitJudgePrompt': 'split', 'baselineJudgePrompt': 'baseline'}}}


class HierarchyTests(unittest.TestCase):
    def test_diagnostic_group_preserves_all_four_outputs_and_whole_context(self):
        p = proposal()
        rows = h.diagnostic_items(p)
        self.assertEqual([r['id'] for r in rows], ['a', 'b'])
        self.assertEqual(rows[0]['completeContext'], p['input']['boundedProcedureDiagnostics']['completeContexts'][0])
        self.assertEqual(len(rows[0]['combinedResponses']), 2)
        self.assertEqual(set(rows[0]['splitResponsePair']['records']), {'A', 'B'})
        p['input']['boundedProcedureDiagnostics']['orderSummary']['rows'].pop()
        with self.assertRaises(RuntimeError): h.diagnostic_items(p)

    def test_exact_once_plan_rejects_duplicated_or_missing_lesson(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(h.q, 'ROOT', Path(temp)):
            p = proposal()
            h.q.once('v3-proposed-optimizer-job.private.json', p)
            entries = []
            for index, (kind, items) in enumerate([('lessons', h.lesson_items(p)), ('diagnostics', h.diagnostic_items(p))]):
                name = str(index)
                h.q.once(h.PREFIX + '/jobs/' + name + '.json', h.meta_job(kind, items, p))
                entries.append({'id': name, 'kind': kind, 'itemIds': [x['id'] for x in items], 'jobSha256': h.q.r.digest(h.root()/'jobs'/(name+'.json'))})
            plan = {'sourceProposedJobSha256': h.q.r.digest(h.q.ROOT/'v3-proposed-optimizer-job.private.json'), 'sourceHashes': {}, 'entries': entries}
            h.q.once(h.PREFIX + '/plan.json', plan)
            h.verify_plan()
            duplicate = copy.deepcopy(plan)
            duplicate['entries'].append(entries[0])
            h.q.r.save(h.root()/'plan.json', duplicate)
            with self.assertRaises(RuntimeError): h.verify_plan()
            omitted = copy.deepcopy(plan)
            omitted['entries'] = omitted['entries'][1:]
            h.q.r.save(h.root()/'plan.json', omitted)
            with self.assertRaises(RuntimeError): h.verify_plan()

    def test_fresh_usage_failure_stops_later_hosted_calls(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(h.q, 'ROOT', Path(temp)):
            def failed(job, directory):
                directory.mkdir(parents=True)
                result = {'status': 'transport_failed', 'output': None}
                h.q.r.save(directory/'parsed.json', result)
                h.q.r.save(directory/'transport-result.json', {'serviceErrors': ['{"error":{"type":"usage_limit_reached"}}']})
                return result
            with patch.object(h.q.r, 'safe_call', side_effect=failed) as call:
                with self.assertRaises(RuntimeError): h.single_attempt({}, Path(temp)/'first')
                with self.assertRaises(RuntimeError): h.single_attempt({}, Path(temp)/'second')
                self.assertEqual(call.call_count, 1)

    def test_uncertain_or_failed_attempt_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(h.q, 'ROOT', Path(temp)):
            for marker in ['process.json', 'parsed.json']:
                directory = Path(temp)/marker
                directory.mkdir()
                (directory/marker).write_text('{}')
                with patch.object(h.q.r, 'safe_call') as call:
                    with self.assertRaises(RuntimeError): h.single_attempt({}, directory)
                    call.assert_not_called()

    def test_optimizer_lineage_rejects_unreconstructed_job(self):
        with patch.object(h, 'final_job', return_value={'input': 'expected'}):
            with self.assertRaises(RuntimeError): h.verify_optimizer_lineage({'input': 'different'}, Path('optimization/v3'))
            with self.assertRaises(RuntimeError): h.verify_optimizer_lineage({'input': 'expected'}, Path('optimization/v4'))

    def test_diagnostic_partition_never_splits_an_item(self):
        items = [{'id': str(i), 'size': n} for i, n in enumerate([6, 4, 7])]
        with patch.object(h, 'MAX_KNOWN_TOKENS', 10), patch.object(h, 'meta_job', side_effect=lambda kind, rows, proposed: rows), patch.object(h, 'known_tokens', side_effect=lambda rows, enc: sum(x['size'] for x in rows)):
            groups = h.partition_diagnostics(items, {}, None)
            self.assertEqual(groups, [items[:2], items[2:]])
            with self.assertRaises(RuntimeError): h.partition_diagnostics([{'id': 'too-large', 'size': 11}], {}, None)


if __name__ == '__main__':
    unittest.main()
