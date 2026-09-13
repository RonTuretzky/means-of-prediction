"""Bounded fresh public-rule draws, executed only from selected sealed sources.

This module never reads evaluation email bodies or labels. It preserves the
original two draws per public question and the standard challenge artifacts.
Run the two selected methods sequentially so four requests is the global bound.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import sys
import qwen_round1 as q
import qwen_guarded_rules as g

MAX_WORKERS = 4


def sealed_only():
    source = q.ROOT / 'sealed-source'
    if Path(__file__).resolve() != (source / Path(__file__).name).resolve():
        raise RuntimeError('Fresh generation must run from the selected sealed-source copy')
    for path in source.glob('*.py'):
        if path.stem in sys.modules:
            actual = getattr(sys.modules[path.stem], '__file__', None)
            if actual is None or Path(actual).resolve() != path.resolve():
                raise RuntimeError('Unsealed imported module: ' + path.stem)


def root(method):
    if method not in ['baseline', *['v' + str(i) for i in range(1, 7)]]:
        raise ValueError('Unknown study method')
    return q.ROOT / 'methods' / method / 'guarded-challenge-v1'


def selection_gate(method):
    sealed_only()
    selected = q.verify_selection()
    if len(selected['freshMethods']) != 2 or len(set(selected['freshMethods'])) != 2 or method not in selected['freshMethods']:
        raise RuntimeError('Method is not in the frozen two-method fresh comparison')
    if (q.ROOT / 'fresh-opened.json').exists() or (q.ROOT / 'challenge-items.private.json').exists():
        raise RuntimeError('Fresh fixture opening already occurred; no more rule draws')
    return selected


def public_jobs(method):
    public = q.load('independent-holdout-public.json')
    if len(public) != 12 or len({p['marketId'] for p in public}) != 12:
        raise RuntimeError('Expected twelve frozen public questions')
    prompt = (q.ROOT / (method + '.txt')).read_text()
    return [{'marketId': p['marketId'] + '/' + str(trial), 'publicMarketId': p['marketId'], 'trial': trial,
             'job': q.rule_job(p, prompt, None, trial)} for p in public for trial in [1, 2]]


def prepare(method, workers=MAX_WORKERS):
    selection_gate(method)
    if g.stopped() or not 1 <= workers <= MAX_WORKERS:
        raise RuntimeError('Usage stop active or invalid worker count')
    directory = root(method)
    if directory.exists() or (directory.parent / 'challenge-rules').exists() or (directory.parent / 'challenge-rules.json').exists():
        raise RuntimeError('Prior fresh generation requires reconciliation, never resampling')
    entries = []
    for row in public_jobs(method):
        name = row['publicMarketId'] + '-' + str(row['trial']) + '.json'
        path = directory / 'inputs' / name
        q.once(str(path.relative_to(q.ROOT)), row['job'])
        entries.append({k: v for k, v in row.items() if k != 'job'} | {'inputFile': name, 'jobSha256': q.r.digest(path)})
    q.once(str((directory / 'plan.json').relative_to(q.ROOT)), {
        'at': q.r.now(), 'method': method, 'workers': workers, 'entries': entries,
        'selectionSha256': q.r.digest(q.ROOT / 'selection.json'),
        'publicSha256': q.r.digest(q.ROOT / 'independent-holdout-public.json'),
        'promptSha256': q.r.digest(q.ROOT / (method + '.txt')),
        'procedure': 'Exactly two unchanged public-only q.rule_job draws for each of twelve questions; no public-context supplement. At most four in flight. Stop new submissions on a fresh usage limit, drain current attempts, retain failed/uncertain outputs without retry, and never fabricate unattempted records. No fixture or evaluation body reads. Global challenge freeze remains a separate original q.freeze step after both complete methods.'})
    verify_plan(method)
    print(json.dumps({'freshMethod': method, 'draws': len(entries), 'planSha256': q.r.digest(directory / 'plan.json')}))


def verify_plan(method):
    selection_gate(method)
    directory = root(method)
    plan = q.r.read(directory / 'plan.json')
    if plan['method'] != method or not 1 <= plan['workers'] <= MAX_WORKERS:
        raise RuntimeError('Fresh dispatch plan differs')
    for key, filename in [('selectionSha256', 'selection.json'), ('publicSha256', 'independent-holdout-public.json'), ('promptSha256', method + '.txt')]:
        if plan[key] != q.r.digest(q.ROOT / filename):
            raise RuntimeError('Frozen fresh input changed: ' + filename)
    jobs = public_jobs(method)
    if len(plan['entries']) != 24:
        raise RuntimeError('Fresh draw budget differs')
    for entry, row in zip(plan['entries'], jobs):
        if any(entry[key] != row[key] for key in ['marketId', 'publicMarketId', 'trial']):
            raise RuntimeError('Fresh draw identity or order changed')
        expected_name = row['publicMarketId'] + '-' + str(row['trial']) + '.json'
        if entry['inputFile'] != expected_name:
            raise RuntimeError('Fresh input path differs')
        path = directory / 'inputs' / expected_name
        if q.r.digest(path) != entry['jobSha256'] or q.r.read(path) != row['job']:
            raise RuntimeError('Fresh public-only request differs')
    return plan


def one(method, entry, gate):
    directory = root(method)
    target = directory.parent / 'challenge-rules' / entry['publicMarketId'] / str(entry['trial'])
    job = q.r.read(directory / 'inputs' / entry['inputFile'])
    with gate.lock:
        if g.stopped() or gate.stop_event.is_set():
            return None
        if target.exists():
            gate.halt('existing_or_uncertain_draw')
            raise RuntimeError('Fresh draw already exists; no retry')
        gate.started.append(entry['marketId'])
    try:
        try:
            parsed = q.r.safe_call(job, target)
        except RuntimeError:
            if not (target / 'parsed.json').exists():
                raise
            parsed = q.r.read(target / 'parsed.json')
        if g.usage_limited(target):
            gate.stop_event.set()
            with gate.lock:
                gate.halt('usage_limit_reached', target)
        q.r.verify_model_artifact(target, job, parsed)
        return {'marketId': entry['publicMarketId'], 'trial': entry['trial'], 'directory': str(target), **parsed}
    except BaseException:
        gate.stop_event.set()
        with gate.lock:
            gate.halt('uncertain_or_unreconciled_draw')
        raise


def run(method):
    plan = verify_plan(method)
    directory = root(method)
    review = q.r.read(directory / 'reviewed.json')
    if review.get('approved') is not True or review['planSha256'] != q.r.digest(directory / 'plan.json'):
        raise RuntimeError('Exact fresh dispatch review required')
    if g.stopped() or (directory.parent / 'challenge-rules').exists():
        raise RuntimeError('Usage stop or prior fresh artifacts require reconciliation')
    with (directory / 'started.json').open('x') as stream:
        json.dump({'at': q.r.now(), 'pid': os.getpid(), 'planSha256': q.r.digest(directory / 'plan.json')}, stream)
    result = g.feed(method, plan['entries'], plan['workers'], one)
    q.once(str((directory / 'dispatch-result.json').relative_to(q.ROOT)), result)
    records = result['records']
    expected = {(entry['publicMarketId'], entry['trial']) for entry in plan['entries']}
    complete = len(records) == 24 and {(row['marketId'], row['trial']) for row in records} == expected and not result['errors'] and not result['unattemptedMarketIds']
    if complete:
        q.once('methods/' + method + '/challenge-rules.json', records)
        files = [path for path in (directory.parent / 'challenge-rules').rglob('*') if path.is_file()]
        q.once('methods/' + method + '/challenge-rules-freeze.json', {
            'at': q.r.now(), 'recordsSha256': q.r.digest(directory.parent / 'challenge-rules.json'),
            'fileHashes': {str(path.relative_to(q.ROOT)): q.r.digest(path) for path in files}})
    summary = {'at': q.r.now(), 'method': method, 'completeCohort': complete, 'actualRecords': len(records),
        'attempted': len(result['attemptedMarketIds']), 'unattempted': len(result['unattemptedMarketIds']),
        'statuses': dict(collections.Counter(row['status'] for row in records)), 'stopReason': result['stopReason']}
    q.once(str((directory / 'completed.json').relative_to(q.ROOT)), summary)
    print(json.dumps(summary), flush=True)
    if not complete:
        raise RuntimeError('Partial fresh generation retained; no complete cohort or fixture opening')


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'run'])
    parser.add_argument('--method', required=True)
    parser.add_argument('--workers', type=int, default=MAX_WORKERS)
    args = parser.parse_args()
    prepare(args.method, args.workers) if args.phase == 'prepare' else run(args.method)
