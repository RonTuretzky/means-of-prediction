"""Bounded public-only rule draws with a persistent hosted usage stop.

This changes dispatch only. It never retries a scored draw, creates a rule for
an unattempted question, or seals a partial cohort as a complete method.
"""
import argparse
import collections
import concurrent.futures
import json
import os
import re
import threading
from pathlib import Path
import qwen_round1 as q
from qwen_capacity_recovery import usage_limited

STOP = 'hosted-training-usage-stop.json'
MAX_WORKERS = 10


def stopped():
    return any((q.ROOT / name).exists() for name in [STOP, 'v2-teacher-capacity-stop.json'])


def directory(method):
    if not re.fullmatch(r'v[3-6]', method):
        raise ValueError('Guarded development runner accepts revisions V3 through V6')
    return q.ROOT / 'methods' / method / 'guarded-generation-v1'


def sources():
    return {str(Path(__file__).with_name(name)): q.r.digest(Path(__file__).with_name(name)) for name in
            ['qwen_guarded_rules.py', 'qwen_round1.py', 'qwen_capacity_recovery.py', 'round4.py',
             'improve.py', 'experiment.py', 'astra_transport.py']}


def prompt_review(method):
    review = q.load('prompt-reviewed-' + method + '.json')
    if review.get('approved') is not True or any(review[key] != q.r.digest(q.ROOT / name) for key, name in
            [('generatorSha256', method + '.txt'), ('judgeSha256', method + '-judge.txt')]):
        raise RuntimeError('Complete prompt review does not match current prompts')


def prepare(method, workers=MAX_WORKERS):
    q.closed()
    prompt_review(method)
    if stopped() or not 1 <= workers <= MAX_WORKERS:
        raise RuntimeError('Usage stop active or invalid bounded worker count')
    root = directory(method)
    if root.exists() or (root.parent / 'rules').exists() or (root.parent / 'rules.json').exists():
        raise RuntimeError('Existing generation requires explicit reconciliation, not resampling')
    public = q.load('public-inputs.json')
    if len(public) != 241 or len({p['marketId'] for p in public}) != 241:
        raise RuntimeError('Public cohort differs')
    prompt = (q.ROOT / (method + '.txt')).read_text()
    contexts = q.r.load('public-contexts.json')
    entries = []
    for p in public:
        job = q.rule_job(p, prompt, contexts.get(p['marketId']))
        path = root / 'inputs' / (p['marketId'] + '.json')
        q.once(str(path.relative_to(q.ROOT)), job)
        entries.append({'marketId': p['marketId'], 'jobSha256': q.r.digest(path)})
    inputs = [q.ROOT / 'public-inputs.json', q.r.ROOT / 'public-contexts.json',
              q.ROOT / (method + '.txt'), q.ROOT / (method + '-judge.txt'),
              q.ROOT / ('prompt-reviewed-' + method + '.json')]
    plan = {'at': q.r.now(), 'method': method, 'workers': workers, 'sourceHashes': sources(),
            'inputHashes': {str(p): q.r.digest(p) for p in inputs}, 'entries': entries,
            'procedure': 'Unchanged q.rule_job public-only medium-effort single draw. At most workers submitted concurrently; first observed usage_limit_reached blocks further submissions and persists a global stop. Already running draws are retained. Unattempted questions receive no fabricated record. No automatic restart or retry. Complete standard rules.json/freeze only if all241 actual records reconcile.'}
    q.once(str((root / 'plan.json').relative_to(q.ROOT)), plan)
    verify_plan(method)
    print(json.dumps({'method': method, 'questions': len(entries), 'workers': workers,
                      'planSha256': q.r.digest(root / 'plan.json')}))


def verify_plan(method):
    root = directory(method)
    plan = q.r.read(root / 'plan.json')
    if plan['method'] != method or not 1 <= plan['workers'] <= MAX_WORKERS:
        raise RuntimeError('Generation plan changed')
    for path, sha in {**plan['sourceHashes'], **plan['inputHashes']}.items():
        if q.r.digest(path) != sha:
            raise RuntimeError('Frozen generation source or input changed')
    public = q.load('public-inputs.json')
    if [x['marketId'] for x in plan['entries']] != [p['marketId'] for p in public]:
        raise RuntimeError('Generation dispatch cohort differs')
    contexts = q.r.load('public-contexts.json')
    prompt = (q.ROOT / (method + '.txt')).read_text()
    for entry, p in zip(plan['entries'], public):
        path = root / 'inputs' / (entry['marketId'] + '.json')
        if q.r.digest(path) != entry['jobSha256'] or q.r.read(path) != q.rule_job(p, prompt, contexts.get(p['marketId'])):
            raise RuntimeError('Frozen public-only request differs')
    return plan


class Gate:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.reason = None
        self.started = []

    def halt(self, reason, path=None):
        # Callers hold lock: submissions and observed stops have one order.
        self.stop_event.set()
        if self.reason is None:
            self.reason = reason
        if reason == 'usage_limit_reached' and not (q.ROOT / STOP).exists():
            q.once(STOP, {'at': q.r.now(), 'directory': str(path),
                         'transportResultSha256': q.r.digest(path / 'transport-result.json'),
                         'reason': 'Fresh usage_limit_reached; no new hosted submissions.'})


def one(method, entry, gate):
    mid = entry['marketId']
    target = directory(method).parent / 'rules' / mid / '1'
    job = q.r.read(directory(method) / 'inputs' / (mid + '.json'))
    with gate.lock:
        if stopped() or gate.stop_event.is_set():
            return None
        if target.exists():
            gate.halt('existing_or_uncertain_draw')
            raise RuntimeError('A rule draw already exists; no automatic retry')
        gate.started.append(mid)
    try:
        try:
            parsed = q.r.safe_call(job, target)
        except RuntimeError:
            if not (target / 'parsed.json').exists():
                raise
            parsed = q.r.read(target / 'parsed.json')
        # Check capacity before the slower raw audit or completion collection.
        if usage_limited(target):
            gate.stop_event.set()
            with gate.lock:
                gate.halt('usage_limit_reached', target)
        q.r.verify_model_artifact(target, job, parsed)
        return {'marketId': mid, 'trial': 1, 'directory': str(target), **parsed}
    except BaseException:
        gate.stop_event.set()
        with gate.lock:
            gate.halt('uncertain_or_unreconciled_draw')
        raise


def feed(method, entries, workers, worker=one):
    gate = Gate()
    records, errors, submitted = [], [], []
    iterator = iter(entries)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}
        def fill():
            with gate.lock:
                while len(pending) < workers and not gate.stop_event.is_set() and not stopped():
                    entry = next(iterator, None)
                    if entry is None:
                        break
                    future = pool.submit(worker, method, entry, gate)
                    pending[future] = entry['marketId']
                    submitted.append(entry['marketId'])
        fill()
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                mid = pending.pop(future)
                try:
                    record = future.result()
                    if record is not None:
                        records.append(record)
                        print(json.dumps({'qwenRuleMethod': method, 'finished': len(records), 'total': len(entries), 'status': record['status']}), flush=True)
                except BaseException as error:
                    with gate.lock:
                        gate.halt('uncertain_or_unreconciled_draw')
                    errors.append({'marketId': mid, 'errorType': type(error).__name__, 'rawArtifactsRetained': True})
            fill()
    attempted = set(gate.started)
    return {'records': records, 'errors': errors, 'submittedMarketIds': submitted,
            'attemptedMarketIds': gate.started, 'unattemptedMarketIds': [e['marketId'] for e in entries if e['marketId'] not in attempted],
            'stopReason': gate.reason or ('persistent_usage_stop' if stopped() else None)}


def run(method):
    q.closed()
    prompt_review(method)
    plan = verify_plan(method)
    root = directory(method)
    review = q.r.read(root / 'reviewed.json')
    if review.get('approved') is not True or review['planSha256'] != q.r.digest(root / 'plan.json'):
        raise RuntimeError('Exact generation procedure review required')
    if stopped() or (root.parent / 'rules').exists():
        raise RuntimeError('Usage stop or prior rule artifacts require explicit reconciliation')
    # Exclusive creation also blocks two coordinators racing past read checks.
    with (root / 'started.json').open('x') as stream:
        json.dump({'at': q.r.now(), 'pid': os.getpid(), 'planSha256': q.r.digest(root / 'plan.json')}, stream)
    result = feed(method, plan['entries'], plan['workers'])
    q.once(str((root / 'dispatch-result.json').relative_to(q.ROOT)), result)
    records = result['records']
    complete = len(records) == len(plan['entries']) and not result['errors'] and not result['unattemptedMarketIds']
    if complete:
        q.once('methods/' + method + '/rules.json', records)
        files = [p for p in (root.parent / 'rules').rglob('*') if p.is_file()]
        q.once('methods/' + method + '/rules-freeze.json', {'frozenAt': q.r.now(),
            'recordsSha256': q.r.digest(root.parent / 'rules.json'),
            'fileHashes': {str(p.relative_to(q.ROOT)): q.r.digest(p) for p in files},
            'generationPromptSha256': q.r.digest(q.ROOT / (method + '.txt')), 'targetEmailSeen': False})
    summary = {'at': q.r.now(), 'completeCohort': complete, 'actualRecords': len(records),
               'attempted': len(result['attemptedMarketIds']), 'unattempted': len(result['unattemptedMarketIds']),
               'statuses': dict(collections.Counter(r['status'] for r in records)), 'stopReason': result['stopReason']}
    q.once(str((root / 'completed.json').relative_to(q.ROOT)), summary)
    print(json.dumps(summary), flush=True)
    if not complete:
        raise RuntimeError('Partial generation retained; no complete cohort or retry authorized')


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('--method', required=True)
    parser.add_argument('--workers', type=int, default=MAX_WORKERS)
    args = parser.parse_args()
    prepare(args.method, args.workers) if args.action == 'prepare' else run(args.method)
