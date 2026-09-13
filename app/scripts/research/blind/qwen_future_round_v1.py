"""Reviewed V4–V6 full-cohort coordinator; no selection or reserved-data reads.

Prepare only after a completed optimizer, prompt review, guarded generation plan
and predecessor round. Run requires a separate exact source/runtime/plan review
and local-quiescence attestation. Existing attempts are never resumed implicitly.
Use uv with the pinned Python 3.14.6 and tiktoken 0.14.0 environment.
"""
import argparse
import concurrent.futures
import contextlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import qwen_round1 as q
import qwen_autorun as d
import qwen_guarded_rules as g
import qwen_hierarchical_optimizer as h
import qwen_future_hierarchy_v1 as f

VERSION = 'future-round-v1'
HERE = Path(__file__).resolve().parent


def directory(method):
    if method not in f.METHODS:
        raise RuntimeError('Only reviewed future revisions V4 through V6 are supported')
    return q.ROOT / VERSION / method


def exclusive(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def require_dead(pids):
    if not pids or len(pids) != len(set(pids)):
        raise RuntimeError('Explicit distinct retired process IDs are required')
    for pid in pids:
        if type(pid) is not int or pid <= 1:
            raise RuntimeError('Invalid retired process ID')
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise RuntimeError('A prior inference or coordinator process is still alive')


def predecessor(method):
    directory(method)
    prior = 'v' + str(int(method[1:]) - 1)
    hashes, pids = {}, []
    def read(path):
        hashes[str(path)] = q.r.digest(path)
        return q.r.read(path)
    for phase in ('judge', 'serial-feedback-v1', 'audit', 'report'):
        root = q.ROOT / 'driver' / prior / phase
        completion = read(root / 'completed.json')
        if completion['returncode'] != 0:
            raise RuntimeError('Prior round has a failed or incomplete stage')
        if completion['logSha256'] != q.r.digest(root / 'output.log'):
            raise RuntimeError('Prior completed stage log changed')
        hashes[str(root / 'output.log')] = completion['logSha256']
        pids.append(read(root / 'process.json')['pid'])
    release = read(q.ROOT / (prior + '-local-released.json'))
    summary_path = q.ROOT / 'methods' / prior / 'development-summary.json'
    read(summary_path)
    if (release['summarySha256'] != q.r.digest(summary_path) or
            release['judgeCompletionSha256'] != q.r.digest(q.ROOT / 'driver' / prior / 'judge/completed.json')):
        raise RuntimeError('Prior local release does not bind completed evaluation')
    manifest = read(q.ROOT / 'feedback' / prior / 'manifest.json')
    expected = {x['caseId'] for x in q.load(q.ITEMS)}
    if len(expected) != 1915 or len(manifest['caseIds']) != 1915 or set(manifest['caseIds']) != expected:
        raise RuntimeError('Prior full feedback cohort is incomplete')
    if prior in f.METHODS:
        root = directory(prior)
        if read(root / 'completed.json')['returncode'] != 0:
            raise RuntimeError('Prior future coordinator did not complete')
        pids.append(read(root / 'started.json')['pid'])
    require_dead(pids)
    return {'method': prior, 'fileHashes': hashes, 'retiredProcessIds': pids}


def source_hashes():
    result = f.source_hashes()
    for name in [Path(__file__).name, 'qwen_autorun.py', 'qwen_guarded_rules.py', 'qwen_preflight.mjs',
                 'prepare_dataset.py', 'matcher.py']:
        path = HERE / name
        result[str(path)] = q.r.digest(path)
    return result


def executable(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': q.r.digest(path)}


def prepare(method):
    q.closed()
    if g.stopped():
        raise RuntimeError('Persistent hosted usage stop; no new round preparation')
    root = directory(method)
    if root.exists():
        raise RuntimeError('Existing launch preparation requires explicit reconciliation')
    g.prompt_review(method)
    generation = g.verify_plan(method)
    f.verify_optimizer_lineage(q.r.read(q.ROOT / 'optimization' / method / 'job.json'), q.ROOT / 'optimization' / method)
    previous = predecessor(method)
    # Dependency presence/version is part of preparation, not deferred to hours
    # into the eventual full run's audit or feedback child.
    f.token_encoding()
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node executable unavailable')
    sources = source_hashes()
    for path, sha in sources.items():
        target = root / 'source' / Path(path).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(Path(path).read_bytes())
        if q.r.digest(target) != sha:
            raise RuntimeError('Launch source snapshot changed while copying')
    protocol = {'at': q.r.now(), 'version': VERSION, 'method': method,
        'sourceHashes': sources, 'runtimeSha256': q.r.digest(q.ROOT / 'runtime.json'),
        'generationPlanSha256': q.r.digest(g.directory(method) / 'plan.json'),
        'hierarchyPlanSha256': q.r.digest(f.root(method) / 'plan.json'),
        'optimizerJobSha256': q.r.digest(q.ROOT / 'optimization' / method / 'job.json'),
        'promptReviewSha256': q.r.digest(q.ROOT / ('prompt-reviewed-' + method + '.json')),
        'executables': {'python': executable(sys.executable), 'node': executable(node)},
        'pythonVersion': sys.version, 'nodeVersion': subprocess.check_output([node, '--version'], text=True).strip(),
        'tokenizer': {'packageVersion': f.TOKENIZER_VERSION, 'encoding': 'o200k_base'},
        'predecessor': previous, 'ruleWorkers': generation['workers'], 'judgeWorkers': 4, 'teacherWorkers': 1,
        'procedure': 'Guarded 241 unchanged public-only rule draws; scoped future lineage audit; complete semantic input token preflight; four-worker unchanged local judge concurrently with serial complete-evidence q.distill using h.single_attempt. The isolated feedback child checks an immutable stop marker and failed judge completion before and after each hosted call and during bounded wait sleeps, without changing global time.sleep; in-flight requests drain and preserve artifacts. Every failure retained. Fresh usage stop blocks new hosted submissions; an already started judge finishes independently. Local release only after successful judge process exit and full cohort. No automatic next round, selection, probe, or reserved-data reads.'}
    exclusive(root / 'protocol.json', protocol)
    verify_protocol(method)
    print(json.dumps({'method': method, 'protocolSha256': q.r.digest(root / 'protocol.json')}))


def verify_protocol(method):
    root = directory(method)
    protocol = q.r.read(root / 'protocol.json')
    if protocol['version'] != VERSION or protocol['method'] != method:
        raise RuntimeError('Future launch version or method differs')
    if protocol['judgeWorkers'] != 4 or protocol['teacherWorkers'] != 1:
        raise RuntimeError('Frozen judge/teacher concurrency changed')
    if protocol['sourceHashes'] != source_hashes():
        raise RuntimeError('Reviewed orchestration source changed')
    for path, sha in protocol['sourceHashes'].items():
        if q.r.digest(root / 'source' / Path(path).name) != sha:
            raise RuntimeError('Launch source snapshot changed')
    bound = {'runtimeSha256': q.ROOT / 'runtime.json', 'generationPlanSha256': g.directory(method) / 'plan.json',
             'hierarchyPlanSha256': f.root(method) / 'plan.json',
             'optimizerJobSha256': q.ROOT / 'optimization' / method / 'job.json',
             'promptReviewSha256': q.ROOT / ('prompt-reviewed-' + method + '.json')}
    if any(protocol[key] != q.r.digest(path) for key, path in bound.items()):
        raise RuntimeError('Frozen runtime, prompts or generation/optimizer plan changed')
    for info in protocol['executables'].values():
        if q.r.digest(info['path']) != info['sha256']:
            raise RuntimeError('Pinned orchestration executable changed')
    if executable(sys.executable) != protocol['executables']['python'] or sys.version != protocol['pythonVersion']:
        raise RuntimeError('Future coordinator uses a different Python runtime')
    if protocol['tokenizer'] != {'packageVersion': f.TOKENIZER_VERSION, 'encoding': 'o200k_base'}:
        raise RuntimeError('Future tokenizer changed')
    f.token_encoding()
    if predecessor(method) != protocol['predecessor']:
        raise RuntimeError('Predecessor completion or quiescence changed')
    g.prompt_review(method)
    if g.verify_plan(method)['workers'] != protocol['ruleWorkers']:
        raise RuntimeError('Guarded rule dispatch concurrency changed')
    f.verify_optimizer_lineage(q.r.read(bound['optimizerJobSha256']), q.ROOT / 'optimization' / method)
    return protocol


def run_review(method, protocol):
    root = directory(method)
    review = q.r.read(root / 'reviewed.json')
    if (review.get('approved') is not True or review.get('localQuiescenceConfirmed') is not True or
            review.get('protocolSha256') != q.r.digest(root / 'protocol.json') or
            review.get('predecessorCompletionHashes') != protocol['predecessor']['fileHashes']):
        raise RuntimeError('Exact launch review and local-quiescence attestation required')
    pids = review.get('retiredProcessIds', [])
    if not set(protocol['predecessor']['retiredProcessIds']).issubset(pids):
        raise RuntimeError('Launch review omits prior stage processes')
    if method == 'v4' and 86209 not in pids:
        raise RuntimeError('V4 launch review must bind the known V3 coordinator PID 86209')
    require_dead(pids)
    generation = q.r.read(g.directory(method) / 'reviewed.json')
    if generation.get('approved') is not True or generation['planSha256'] != protocol['generationPlanSha256']:
        raise RuntimeError('Exact guarded generation review required')


@contextlib.contextmanager
def coordinator_lock():
    path = q.ROOT / '.future-round-owner.lock'
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another future round coordinator owns execution') from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def guard_new_stage():
    if g.stopped():
        raise RuntimeError('Persistent hosted usage stop; preserve completed stages without new dispatch')


def feedback_script(method):
    directory(method)
    return f"import qwen_future_round_v1 as c; c.feedback_worker({method!r})"


def check_feedback_stop(method):
    completion = q.ROOT / 'driver' / method / 'judge/completed.json'
    if ((directory(method) / 'feedback-stop.json').exists() or g.stopped() or
            (completion.exists() and q.r.read(completion)['returncode'] != 0)):
        raise RuntimeError('Feedback stopped after failed local judge or hosted usage stop; retain all attempts')


class FeedbackClock:
    """Only q.time in the isolated feedback child changes; stdlib time is intact."""
    def __init__(self, method, original):
        self.method, self.original = method, original

    def __getattr__(self, name):
        return getattr(self.original, name)

    def sleep(self, seconds):
        check_feedback_stop(self.method)
        remaining = seconds
        while remaining > 0:
            interval = min(1.0, remaining)
            self.original.sleep(interval)
            check_feedback_stop(self.method)
            remaining -= interval


def feedback_worker(method):
    directory(method)
    f.verify_plan(method)
    check_feedback_stop(method)
    original_clock, original_teacher = q.time, q.teacher_call
    def teacher(job, path):
        check_feedback_stop(method)
        result = h.single_attempt(job, path)
        # A running request always drains and preserves its raw/effective files.
        # Stop before another shard or a falsely complete feedback manifest.
        check_feedback_stop(method)
        return result
    q.time, q.teacher_call = FeedbackClock(method, original_clock), teacher
    try:
        q.distill(method, workers=1, stream=True)
    finally:
        q.time, q.teacher_call = original_clock, original_teacher


def stop_feedback(method, error):
    completion = q.ROOT / 'driver' / method / 'judge/completed.json'
    exclusive(directory(method) / 'feedback-stop.json', {'at': q.r.now(),
        'reason': 'Local judge stage failed; stop waiting for missing results and stop new teacher requests.',
        'errorType': type(error).__name__,
        'judgeCompletionSha256': q.r.digest(completion) if completion.exists() else None,
        'inFlightPolicy': 'Drain any already running single_attempt and retain its artifacts; no subsequent request.'})


def local_release(method):
    completion_path = q.ROOT / 'driver' / method / 'judge/completed.json'
    if q.r.read(completion_path)['returncode'] != 0:
        raise RuntimeError('Failed local judge cannot release successful evaluation')
    require_dead([q.load('driver/' + method + '/judge/process.json')['pid']])
    records = q.load('methods/' + method + '/development-judgments.private.json')
    expected = {x['caseId'] for x in q.load(q.ITEMS)}
    if len(expected) != 1915 or len(records) != 1915 or {x['caseId'] for x in records} != expected:
        raise RuntimeError('Local release requires the entire unchanged development cohort')
    summary_path = q.ROOT / 'methods' / method / 'development-summary.json'
    summary = q.r.read(summary_path)
    if sum(summary['statuses'].values()) != 1915:
        raise RuntimeError('Local summary cohort incomplete')
    exclusive(q.ROOT / (method + '-local-released.json'), {'at': q.r.now(),
        'judgeCompletionSha256': q.r.digest(completion_path), 'summarySha256': q.r.digest(summary_path),
        'scope': 'Entire local judge process completed. This coordinator has no remaining local inference. Serial hosted feedback may still be active.'})


def evaluate(method):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        judge = pool.submit(d.command, 'judge', method,
            [sys.executable, 'qwen_round1.py', 'judge', '--method', method, '--workers', '4'])
        feedback = pool.submit(d.command, 'serial-feedback-v1', method,
            [sys.executable, '-c', feedback_script(method)])
        try:
            judge.result()
            local_release(method)
        except BaseException as error:
            stop_feedback(method, error)
            raise
        d.status('local-complete-serial-feedback-may-continue', method)
        feedback.result()


def execute(method, protocol):
    guard_new_stage()
    d.command('lineage-audit', method, [sys.executable, 'qwen_future_hierarchy_v1.py', 'audit'])
    guard_new_stage()
    d.command('guarded-rules-v1', method, [sys.executable, 'qwen_guarded_rules.py', 'run', '--method', method])
    guard_new_stage()
    d.command('rules-audit', method, [sys.executable, 'qwen_round1.py', 'audit-rules', '--method', method])
    d.command('preflight-inputs', method, [sys.executable, 'qwen_round1.py', 'preflight', '--method', method])
    d.command('preflight-tokens', method, [protocol['executables']['node']['path'], 'qwen_preflight.mjs',
        str(q.ROOT / 'methods' / method / 'semantic-preflight-requests.private.json'),
        str(q.ROOT / 'methods' / method / 'semantic-preflight.json')])
    preflight = q.load('methods/' + method + '/semantic-preflight.json')
    q.verify_preflight_runtime(preflight, q.load('runtime.json'))
    if not preflight['allFullInputsFit'] or preflight['inputSha256'] != q.r.digest(q.ROOT / 'methods' / method / 'semantic-preflight-requests.private.json'):
        raise RuntimeError('Complete local input preflight does not fit or changed')
    guard_new_stage()
    evaluate(method)
    d.command('audit', method, [sys.executable, 'qwen_future_hierarchy_v1.py', 'audit'])
    d.command('report', method, [sys.executable, 'qwen_round1.py', 'report'])


def run(method):
    q.closed()
    guard_new_stage()
    with coordinator_lock():
        protocol = verify_protocol(method)
        run_review(method, protocol)
        root = directory(method)
        exclusive(root / 'started.json', {'at': q.r.now(), 'pid': os.getpid(),
            'protocolSha256': q.r.digest(root / 'protocol.json'), 'reviewSha256': q.r.digest(root / 'reviewed.json'),
            'pythonInvocationPath': sys.executable})
        try:
            execute(method, protocol)
        except BaseException as error:
            exclusive(root / 'completed.json', {'at': q.r.now(), 'returncode': 1,
                'errorType': type(error).__name__, 'usageStopActive': g.stopped(),
                'localReleased': (q.ROOT / (method + '-local-released.json')).exists(),
                'policy': 'All stage attempts retained. No automatic restart, retry or next round.'})
            raise
        exclusive(root / 'completed.json', {'at': q.r.now(), 'returncode': 0,
            'summarySha256': q.r.digest(q.ROOT / 'methods' / method / 'development-summary.json'),
            'feedbackManifestSha256': q.r.digest(q.ROOT / 'feedback' / method / 'manifest.json')})
        d.status('future-round-complete-awaiting-paired-review', method)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--method', required=True, choices=f.METHODS)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else run)(args.method)
