import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import qwen_future_round_v1 as c


class FutureRoundTests(unittest.TestCase):
    def test_only_future_methods_and_exclusive_marker(self):
        for bad in ('v3', 'v7', '../../outside'):
            with self.assertRaises(RuntimeError): c.directory(bad)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'nested' / 'started.json'
            c.exclusive(path, {'first': True})
            with self.assertRaises(FileExistsError): c.exclusive(path, {'replacement': True})
            self.assertEqual(json.loads(path.read_text()), {'first': True})

    def test_global_coordinator_lock_rejects_overlap_and_releases_on_error(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)):
            with self.assertRaises(ValueError):
                with c.coordinator_lock():
                    with self.assertRaises(RuntimeError):
                        with c.coordinator_lock(): pass
                    raise ValueError('stop')
            with c.coordinator_lock(): pass

    def test_dead_process_check_never_accepts_live_or_invalid_pids(self):
        with patch.object(c.os, 'kill', side_effect=ProcessLookupError): c.require_dead([123, 456])
        with patch.object(c.os, 'kill', return_value=None):
            with self.assertRaises(RuntimeError): c.require_dead([123])
        for pids in ([], [True], [0], [123, 123]):
            with self.assertRaises(RuntimeError): c.require_dead(pids)

    def test_predecessor_requires_all_completed_stages_full_feedback_and_dead_processes(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c.os, 'kill', side_effect=ProcessLookupError):
            root = Path(temp)
            for i, phase in enumerate(('judge', 'serial-feedback-v1', 'audit', 'report')):
                stage = root / 'driver/v3' / phase
                stage.mkdir(parents=True); (stage / 'output.log').write_text('complete')
                c.exclusive(stage / 'completed.json', {'returncode': 0, 'logSha256': c.q.r.digest(stage / 'output.log')})
                c.exclusive(stage / 'process.json', {'pid': 100 + i})
            c.exclusive(root / 'methods/v3/development-summary.json', {'complete': True})
            c.exclusive(root / 'v3-local-released.json', {'summarySha256': c.q.r.digest(root / 'methods/v3/development-summary.json'), 'judgeCompletionSha256': c.q.r.digest(root / 'driver/v3/judge/completed.json')})
            items = [{'caseId': str(i)} for i in range(1915)]
            c.exclusive(root / c.q.ITEMS, items)
            manifest = root / 'feedback/v3/manifest.json'
            c.exclusive(manifest, {'caseIds': [x['caseId'] for x in items]})
            value = c.predecessor('v4')
            self.assertEqual(value['retiredProcessIds'], [100, 101, 102, 103])
            with patch.object(c.os, 'kill', return_value=None):
                with self.assertRaises(RuntimeError): c.predecessor('v4')
            manifest.write_text(json.dumps({'caseIds': [x['caseId'] for x in items[:-1]]}))
            with self.assertRaises(RuntimeError): c.predecessor('v4')

    def test_protocol_rejects_changed_runtime_or_source_before_execution(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c, 'source_hashes', return_value={}), patch.object(c, 'predecessor', return_value={'complete': True}), patch.object(c.g, 'prompt_review'), patch.object(c.g, 'verify_plan', return_value={'workers': 10}), patch.object(c.f, 'verify_optimizer_lineage'), patch.object(c.f, 'token_encoding'):
            root = c.directory('v4')
            paths = {'runtimeSha256': Path(temp) / 'runtime.json', 'generationPlanSha256': c.g.directory('v4') / 'plan.json', 'hierarchyPlanSha256': c.f.root('v4') / 'plan.json', 'optimizerJobSha256': Path(temp) / 'optimization/v4/job.json', 'promptReviewSha256': Path(temp) / 'prompt-reviewed-v4.json'}
            for path in paths.values(): c.exclusive(path, {})
            protocol = {'version': c.VERSION, 'method': 'v4', 'judgeWorkers': 4, 'teacherWorkers': 1, 'ruleWorkers': 10, 'sourceHashes': {}, 'predecessor': {'complete': True}, 'executables': {'python': c.executable(c.sys.executable)}, 'pythonVersion': c.sys.version, 'tokenizer': {'packageVersion': c.f.TOKENIZER_VERSION, 'encoding': 'o200k_base'}, **{key: c.q.r.digest(path) for key, path in paths.items()}}
            c.exclusive(root / 'protocol.json', protocol)
            self.assertEqual(c.verify_protocol('v4'), protocol)
            with patch.object(c, 'source_hashes', return_value={'changed-source': 'sha'}):
                with self.assertRaises(RuntimeError): c.verify_protocol('v4')
            paths['runtimeSha256'].write_text('{"changed":true}')
            with self.assertRaises(RuntimeError): c.verify_protocol('v4')

    def test_usage_stop_blocks_prepare_and_run_before_mutation(self):
        with patch.object(c.q, 'closed'), patch.object(c.g, 'stopped', return_value=True), patch.object(c, 'verify_protocol') as verify, patch.object(c, 'exclusive') as write, patch.object(c.g, 'prompt_review') as review:
            with self.assertRaises(RuntimeError): c.prepare('v4')
            with self.assertRaises(RuntimeError): c.run('v4')
            verify.assert_not_called(); write.assert_not_called(); review.assert_not_called()

    def test_fresh_rule_usage_stop_prevents_preflight_and_local_teacher_launch(self):
        halted = False; calls = []
        def command(phase, method, args):
            nonlocal halted
            calls.append((phase, args))
            if phase == 'guarded-rules-v1': halted = True
        with patch.object(c.g, 'stopped', side_effect=lambda: halted), patch.object(c.d, 'command', side_effect=command), patch.object(c, 'evaluate') as evaluate:
            with self.assertRaises(RuntimeError): c.execute('v4', {})
            evaluate.assert_not_called()
        self.assertEqual([x[0] for x in calls], ['lineage-audit', 'guarded-rules-v1'])
        self.assertEqual(calls[0][1][-2:], ['qwen_future_hierarchy_v1.py', 'audit'])

    def test_serial_feedback_uses_future_lineage_and_single_attempt_callback(self):
        original_clock, original_teacher = c.q.time, c.q.teacher_call
        def distill(method, **kwargs):
            self.assertEqual((method, kwargs), ('v5', {'workers': 1, 'stream': True}))
            self.assertIsInstance(c.q.time, c.FeedbackClock)
            return c.q.teacher_call({'whole': 'job'}, Path('test-shard'))
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c.f, 'verify_plan') as verify, patch.object(c.h, 'single_attempt', return_value={'status': 'completed'}) as call, patch.object(c.q, 'distill', side_effect=distill):
            exec(c.feedback_script('v5'), {})
            verify.assert_called_once_with('v5')
            call.assert_called_once_with({'whole': 'job'}, Path('test-shard'))
        self.assertIs(c.q.time, original_clock); self.assertIs(c.q.teacher_call, original_teacher)

    def test_local_release_precedes_feedback_completion_and_no_new_inference_follows(self):
        feedback_started = threading.Event(); finish_feedback = threading.Event(); released = threading.Event()
        calls = []
        def command(phase, method, args):
            calls.append((phase, args))
            if phase == 'judge':
                if not feedback_started.wait(2): raise RuntimeError('feedback never started')
            else:
                feedback_started.set()
                if not finish_feedback.wait(2): raise RuntimeError('test feedback timeout')
        def release(method): released.set()
        errors = []
        def run():
            try: c.evaluate('v4')
            except BaseException as error: errors.append(error)
        with patch.object(c.d, 'command', side_effect=command), patch.object(c, 'local_release', side_effect=release), patch.object(c.d, 'status'):
            worker = threading.Thread(target=run); worker.start()
            self.assertTrue(released.wait(2)); self.assertTrue(worker.is_alive())
            finish_feedback.set(); worker.join(2)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors, [])
        self.assertEqual(sorted(x[0] for x in calls), ['judge', 'serial-feedback-v1'])
        judge = next(args for phase, args in calls if phase == 'judge')
        self.assertEqual(judge[-2:], ['--workers', '4'])

    def test_judge_failure_waits_existing_feedback_without_successful_release(self):
        feedback_done = threading.Event()
        def command(phase, method, args):
            if phase == 'judge': raise RuntimeError('preserved failed local stage')
            feedback_done.set()
        with patch.object(c.d, 'command', side_effect=command), patch.object(c, 'local_release') as release, patch.object(c, 'stop_feedback') as stop:
            with self.assertRaises(RuntimeError): c.evaluate('v4')
            release.assert_not_called()
            stop.assert_called_once()
        self.assertTrue(feedback_done.is_set())

    def test_actual_distill_wait_for_missing_output_exits_after_judge_failure(self):
        waiting = threading.Event()
        def short_sleep(seconds):
            waiting.set(); time.sleep(min(seconds, 0.01))
        clock = SimpleNamespace(sleep=short_sleep, time=time.time)
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c.q, 'time', clock), patch.object(c.f, 'verify_plan'), patch.object(c.h, 'single_attempt') as hosted:
            root = Path(temp)
            item = {'caseId': 'missing', 'marketId': 'market', 'kind': 'control', 'expected': 'A', 'metadata': {}, 'email': {'completeSemanticText': 'Entire test body'}}
            for name, value in [(c.q.ITEMS, [item]), ('development-items.private.json', [item]), ('public-inputs.json', [{'marketId': 'market'}]), ('methods/v4/rules.json', [{'marketId': 'market', 'status': 'completed', 'output': {}}])]:
                c.exclusive(root / name, value)
            def command(phase, method, args):
                if phase == 'judge':
                    if not waiting.wait(2): raise AssertionError('Real distill never waited for missing output')
                    c.exclusive(root / 'driver/v4/judge/completed.json', {'returncode': 1})
                    raise RuntimeError('judge died with missing output')
                c.feedback_worker(method)
            start = time.monotonic()
            with patch.object(c.d, 'command', side_effect=command), patch.object(c, 'local_release') as release:
                with self.assertRaises(RuntimeError): c.evaluate('v4')
                release.assert_not_called()
            self.assertLess(time.monotonic() - start, 3)
            self.assertTrue((c.directory('v4') / 'feedback-stop.json').exists())
            self.assertFalse((root / 'feedback/v4/manifest.json').exists())
            hosted.assert_not_called()
            self.assertIs(c.q.time, clock)

    def test_inflight_teacher_drains_preserves_artifact_and_stops_before_next_request(self):
        started, finish = threading.Event(), threading.Event(); errors = []
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c.f, 'verify_plan'):
            root = Path(temp)
            def hosted(job, path):
                started.set()
                if not finish.wait(2): raise AssertionError('Test did not release in-flight request')
                c.exclusive(path / 'teacher-effective.json', {'status': 'completed'})
                return {'status': 'completed'}
            def distill(method, **kwargs):
                c.q.teacher_call({'first': True}, root / 'first')
                c.q.teacher_call({'second': True}, root / 'second')
            def run():
                try: c.feedback_worker('v4')
                except RuntimeError as error: errors.append(str(error))
            original_clock, original_teacher = c.q.time, c.q.teacher_call
            with patch.object(c.h, 'single_attempt', side_effect=hosted) as call, patch.object(c.q, 'distill', side_effect=distill):
                worker = threading.Thread(target=run); worker.start()
                self.assertTrue(started.wait(2))
                c.stop_feedback('v4', RuntimeError('judge failed'))
                self.assertTrue(worker.is_alive())
                finish.set(); worker.join(2)
                self.assertFalse(worker.is_alive()); self.assertEqual(call.call_count, 1)
            self.assertEqual(len(errors), 1)
            self.assertTrue((root / 'first/teacher-effective.json').exists())
            self.assertFalse((root / 'second').exists())
            self.assertIs(c.q.time, original_clock); self.assertIs(c.q.teacher_call, original_teacher)

    def test_failed_feedback_retains_finished_judge_release(self):
        def command(phase, method, args):
            if phase == 'serial-feedback-v1': raise RuntimeError('fresh hosted usage stop')
        with patch.object(c.d, 'command', side_effect=command), patch.object(c, 'local_release') as release, patch.object(c.d, 'status'):
            with self.assertRaises(RuntimeError): c.evaluate('v6')
            release.assert_called_once_with('v6')

    def test_nominal_judge_with_invalid_release_stops_waiting_feedback_before_shutdown(self):
        stop_seen = threading.Event()
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)):
            def command(phase, method, args):
                if phase == 'judge': return
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if (c.directory(method) / 'feedback-stop.json').exists():
                        stop_seen.set(); return
                    time.sleep(0.01)
                raise AssertionError('Feedback was never stopped after invalid local release')
            with patch.object(c.d, 'command', side_effect=command), patch.object(c, 'local_release', side_effect=RuntimeError('Incomplete nominally successful cohort')):
                with self.assertRaises(RuntimeError): c.evaluate('v4')
            self.assertTrue(stop_seen.is_set())
            marker = c.q.r.read(c.directory('v4') / 'feedback-stop.json')
            self.assertEqual(marker['errorType'], 'RuntimeError')
            self.assertFalse((Path(temp) / 'v4-local-released.json').exists())

    def test_final_audit_uses_future_dispatcher_and_no_selection(self):
        calls = []
        with patch.object(c, 'guard_new_stage'), patch.object(c.d, 'command', side_effect=lambda phase, method, args: calls.append((phase, args))), patch.object(c.q, 'load', side_effect=lambda name: {'allFullInputsFit': True, 'inputSha256': 'sha'} if name.endswith('semantic-preflight.json') else {}), patch.object(c.q, 'verify_preflight_runtime'), patch.object(c.q.r, 'digest', return_value='sha'), patch.object(c, 'evaluate') as evaluate:
            c.execute('v4', {'executables': {'node': {'path': '/pinned/node'}}})
            evaluate.assert_called_once_with('v4')
        self.assertEqual([phase for phase, _ in calls], ['lineage-audit', 'guarded-rules-v1', 'rules-audit', 'preflight-inputs', 'preflight-tokens', 'audit', 'report'])
        audit = next(args for phase, args in calls if phase == 'audit')
        self.assertEqual(audit[-2:], ['qwen_future_hierarchy_v1.py', 'audit'])
        self.assertFalse(any('select' in args for _, args in calls))

    def test_launch_review_binds_exact_plan_and_prior_processes(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c, 'require_dead') as dead:
            root = c.directory('v4'); c.exclusive(root / 'protocol.json', {})
            protocol = {'generationPlanSha256': 'generation', 'predecessor': {'fileHashes': {'prior': 'sha'}, 'retiredProcessIds': [123]}}
            review = {'approved': True, 'localQuiescenceConfirmed': True, 'protocolSha256': c.q.r.digest(root / 'protocol.json'), 'predecessorCompletionHashes': {'prior': 'sha'}, 'retiredProcessIds': [123, 456, 86209]}
            c.exclusive(root / 'reviewed.json', review)
            c.exclusive(c.g.directory('v4') / 'reviewed.json', {'approved': True, 'planSha256': 'generation'})
            c.run_review('v4', protocol); dead.assert_called_once_with([123, 456, 86209])
            for field, bad in [('localQuiescenceConfirmed', False), ('retiredProcessIds', [456]), ('retiredProcessIds', [123, 456]), ('protocolSha256', 'different'), ('predecessorCompletionHashes', {})]:
                changed = {**review, field: bad}; (root / 'reviewed.json').write_text(json.dumps(changed))
                with self.assertRaises(RuntimeError): c.run_review('v4', protocol)

    def test_local_release_requires_dead_judge_and_full_unchanged_cohort(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c, 'require_dead') as dead:
            completion = Path(temp) / 'driver/v4/judge/completed.json'
            c.exclusive(completion, {'returncode': 0})
            c.exclusive(Path(temp) / 'driver/v4/judge/process.json', {'pid': 123})
            items = [{'caseId': str(i)} for i in range(1915)]
            c.exclusive(Path(temp) / c.q.ITEMS, items)
            records_path = Path(temp) / 'methods/v4/development-judgments.private.json'
            c.exclusive(records_path, items[:-1])
            c.exclusive(Path(temp) / 'methods/v4/development-summary.json', {'statuses': {'completed': 1915}})
            with self.assertRaises(RuntimeError): c.local_release('v4')
            records_path.write_text(json.dumps(items))
            c.local_release('v4')
            dead.assert_called_with([123])
            with self.assertRaises(FileExistsError): c.local_release('v4')

    def test_run_failure_is_retained_and_cannot_restart(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(c.q, 'ROOT', Path(temp)), patch.object(c.q, 'closed'), patch.object(c, 'guard_new_stage'), patch.object(c, 'verify_protocol', return_value={}), patch.object(c, 'run_review'), patch.object(c, 'execute', side_effect=RuntimeError('stage failed')) as execute, patch.object(c.g, 'stopped', return_value=False):
            root = c.directory('v4')
            c.exclusive(root / 'protocol.json', {}); c.exclusive(root / 'reviewed.json', {})
            with self.assertRaises(RuntimeError): c.run('v4')
            self.assertEqual(c.q.r.read(root / 'completed.json')['returncode'], 1)
            with self.assertRaises(FileExistsError): c.run('v4')
            self.assertEqual(execute.call_count, 1)


if __name__ == '__main__': unittest.main()
