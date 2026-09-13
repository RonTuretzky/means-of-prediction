"""One reviewed continuation of 194 unattempted V3 local requests.

All original V3 artifacts remain immutable and incomplete. Four original
in-flight requests remain unscorable, without retries or invented responses.
This module never calls hosted models, starts another method, selects a method,
opens reserved data, or writes original completion/release/summary markers.
"""
import argparse
import collections
import concurrent.futures
import contextlib
import fcntl
import json
import math
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import threading
import time

import qwen_round1 as q
import qwen_final_audit as audit_support

VERSION = 'v3-unattempted-continuation-v1'
ROOT = q.ROOT / VERSION
HERE = Path(__file__).resolve().parent
RECONCILIATION = 'v3-interruption-reconciliation-20260913.private.json'
PROPOSAL = 'v3-unattempted-continuation-proposal-20260913.private.json'
RECONCILIATION_SHA = 'b14373df640efd71dd4edc6ba80aa67e4c1934b4a8c35f1dbea8592f23edee85'
PROPOSAL_SHA = '06ba7c7c613a2ac6b39186f74dd89d17020d4a3bc442491840ade0bdd3c8e7b5'
OLD_PIDS = [86209, 86480, 86481, 39710]
OLD_TREES = ['methods/v3', 'feedback/v3', 'driver/v3']
FORBIDDEN_MARKERS = ['v3-local-released.json', 'driver/v3/judge/completed.json',
    'driver/v3/serial-feedback-v1/completed.json', 'methods/v3/development-summary.json']
SDK = Path('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs')
APP_INFO = Path('/Applications/LM Studio.app/Contents/Info.plist')


def once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def dead(pids):
    if not pids or len(pids) != len(set(pids)):
        raise RuntimeError('Distinct retired process IDs required')
    for pid in pids:
        if type(pid) is not int or pid <= 1:
            raise RuntimeError('Invalid retired process ID')
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise RuntimeError('A prior owner is alive')


def original_path(cid):
    return q.ROOT / 'methods/v3/development' / cid / '1'


def original_inventory():
    return {str(p.relative_to(q.ROOT)): q.r.digest(p) for tree in OLD_TREES
            for p in sorted((q.ROOT/tree).rglob('*')) if p.is_file()}


def verify_originals():
    if q.r.digest(q.ROOT/RECONCILIATION) != RECONCILIATION_SHA or q.r.digest(q.ROOT/PROPOSAL) != PROPOSAL_SHA:
        raise RuntimeError('Reviewed reconciliation/proposal changed')
    rec = q.load(RECONCILIATION)
    if original_inventory() != rec['preservedFileHashes'] or len(rec['preservedFileHashes']) != 11751:
        raise RuntimeError('Original artifacts changed, disappeared or gained a file')
    if any((q.ROOT/p).exists() for p in FORBIDDEN_MARKERS):
        raise RuntimeError('Original incomplete run acquired a completion marker')
    launch = q.load('v3-loop-launch-protocol.json')
    if q.r.digest(q.ROOT/'v3-loop.py') != launch['sourceSha256']:
        raise RuntimeError('Original coordinator source changed')
    for path, sha in launch['additionalSourceHashes'].items():
        if q.r.digest(path) != sha:
            raise RuntimeError('Original launch source changed')
    for info in launch['executables'].values():
        if executable(info['path']) != {k: info[k] for k in ['path','sha256']}:
            raise RuntimeError('Original executable changed')
    dead(OLD_PIDS)
    return rec


def check_unattempted(entry):
    # Any unexpected file or even an existing directory is a reconciliation
    # boundary; never ask local_call to reuse cached or uncertain work.
    if original_path(entry['caseId']).exists() or (ROOT/'responses'/entry['caseId']).exists():
        raise RuntimeError('Target is no longer provably unattempted')


def expected_entries(rec):
    entries = q.load(PROPOSAL)['requests']
    if entries != rec['unattemptedRequests'] or len(entries) != 194:
        raise RuntimeError('Continuation is not exactly the reviewed 194 requests')
    if [e['ordinal'] for e in entries] != list(range(1721, 1915)) or len({e['caseId'] for e in entries}) != 194:
        raise RuntimeError('Duplicate, omitted or reordered targets')
    if any(e['started'] is not None or e['artifactHashes'] for e in entries):
        raise RuntimeError('Previously attempted target included')
    if {e['caseId'] for e in entries} & {e['caseId'] for e in rec['uncertainRequests']}:
        raise RuntimeError('Uncertain original request selected')
    return entries


def source_hashes():
    sources = [Path(__file__), HERE/'test_qwen_v3_unattempted_continuation.py',
               HERE/'qwen_v3_continuation_runtime.mjs', Path(audit_support.__file__), SDK, APP_INFO]
    launch = q.load('v3-loop-launch-protocol.json')
    sources += [Path(p) for p in launch['additionalSourceHashes']]
    sources += [Path(q.__file__), Path(q.semantic.__file__), Path(q.r.__file__)]
    return {str(p): q.r.digest(p) for p in sources}


def executable(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': q.r.digest(path)}


def commands(command):
    return subprocess.check_output(command, text=True, timeout=60)


def assert_idle(models, runtime):
    if len(models) != 1:
        raise RuntimeError('Expected exactly the pinned loaded model')
    info = models[0]
    q.verify_preflight_runtime({'contextLength': info['contextLength'], 'modelInfo': info}, runtime)
    if info.get('status') != 'idle' or info.get('queued') != 0:
        raise RuntimeError('Loaded inference slots are not idle with an empty queue')


def validate_runtime(snapshot, runtime, expected_load=None):
    assert_idle(snapshot['modelsBefore'], runtime)
    assert_idle(snapshot['modelsAfter'], runtime)
    info = snapshot['sdk']['modelInfo']
    q.verify_preflight_runtime({'contextLength': info['contextLength'], 'modelInfo': info}, runtime)
    fields = snapshot['sdk']['loadConfig']['fields']
    config = {f['key']: f['value'] for f in fields}
    if len(config) != len(fields) or config.get('llm.load.numParallelSessions') != 4 or config.get('llm.load.contextLength') != runtime['contextLength']:
        raise RuntimeError('Parallel slots or context differs')
    if config.get('llm.load.llama.acceleration.offloadRatio') != 1:
        raise RuntimeError('Pinned GPU offload differs')
    if expected_load is not None and snapshot['sdk']['loadConfig'] != expected_load:
        raise RuntimeError('Loaded model configuration changed')
    if snapshot['appVersion'] != runtime['lmStudioVersion'] or snapshot['engines'] != runtime['engines']:
        raise RuntimeError('LM Studio version or selected engines changed')
    if snapshot['artifactSha256'] != runtime['artifactSha256'] or snapshot['artifactBytes'] != runtime['artifactBytes']:
        raise RuntimeError('Model artifact bytes differ')
    if snapshot['loadedArtifactSha256'] != runtime['artifactSha256']:
        raise RuntimeError('Loaded-path model artifact differs')


def runtime_snapshot(exes, request_file, expected_load=None):
    runtime = q.load('runtime.json')
    before = json.loads(commands([exes['lms']['path'], 'ps', '--json']))
    assert_idle(before, runtime)
    sdk = json.loads(commands([exes['node']['path'], str(HERE/'qwen_v3_continuation_runtime.mjs'), str(request_file)]))
    # Two explicit idle/empty-queue samples surround read-only model inspection.
    time.sleep(1)
    after = json.loads(commands([exes['lms']['path'], 'ps', '--json']))
    with APP_INFO.open('rb') as stream:
        app = plistlib.load(stream)
    version = app['CFBundleShortVersionString']
    artifact = Path(runtime['artifactPath'])
    loaded_artifact = Path('/Users/wk/.lmstudio/models')/sdk['modelInfo']['path']
    artifact_sha = q.r.digest(artifact)
    loaded_sha = artifact_sha if os.path.samefile(artifact, loaded_artifact) else q.r.digest(loaded_artifact)
    snapshot = {'at': q.r.now(), 'modelsBefore': before, 'modelsAfter': after, 'sdk': sdk,
        'appVersion': version, 'appBuild': app['CFBundleVersion'], 'engines': commands([exes['lms']['path'], 'runtime', 'ls']),
        'artifactSha256': artifact_sha, 'artifactBytes': artifact.stat().st_size, 'loadedArtifactSha256': loaded_sha,
        'slotQualification': 'The loaded instance reports idle and queued=0 twice, with four configured parallel sessions. Combined with exclusive cooperative ownership and the root no-competing-inference attestation; not a hardware lock against unrelated external clients.'}
    validate_runtime(snapshot, runtime, expected_load)
    return snapshot


def requests_for(entries):
    items = {x['caseId']: x for x in q.load(q.ITEMS)}
    rules = {x['marketId']: x for x in q.load('methods/v3/rules.json')}
    prompt = (q.ROOT/'v3-judge.txt').read_text()
    runtime = q.load('runtime.json')
    pre = q.load('methods/v3/semantic-preflight.json')
    expected = {x['caseId']: x['request'] for x in q.load('methods/v3/semantic-preflight-requests.private.json')['requests']}
    if pre['inputSha256'] != q.r.digest(q.ROOT/'methods/v3/semantic-preflight-requests.private.json'):
        raise RuntimeError('Original token preflight changed')
    out = []
    for entry in entries:
        item = items[entry['caseId']]
        if item['marketId'] != entry['marketId'] or item['kind'] != entry['kind']:
            raise RuntimeError('Target identity differs')
        request = q.judge_request(rules[item['marketId']]['output'], q.restore_email(item['email']), prompt, runtime)
        if request != expected[entry['caseId']] or q.r.hash_value(request) != entry['requestSha256']:
            raise RuntimeError('Full frozen V3 request differs')
        out.append({'caseId': entry['caseId'], 'request': request})
    return {'identifier': runtime['identifier'], 'requests': out}


def verify_counts(snapshot, packet):
    original = {x['caseId']: x for x in q.load('methods/v3/semantic-preflight.json')['counts']}
    expected = [original[x['caseId']] for x in packet['requests']]
    if snapshot['sdk']['counts'] != expected or any(x['inputTokens'] + x['outputAllowance'] > q.load('runtime.json')['contextLength'] for x in expected):
        raise RuntimeError('Actual full-input token/template preflight differs')


def prepare():
    os.umask(0o077)
    if ROOT.exists():
        raise RuntimeError('Preparation already exists; no overwrite')
    rec = verify_originals()
    entries = expected_entries(rec)
    for e in entries:
        check_unattempted(e)
    exes = {k: executable(p) for k, p in [('python', sys.executable), ('node', shutil.which('node')), ('lms', shutil.which('lms'))]}
    prior_python = q.load('v3-loop-launch-protocol.json')['executables']['python']
    if exes['python'] != {k: prior_python[k] for k in ['path','sha256']}:
        raise RuntimeError('Use the original Python executable')
    packet = requests_for(entries)
    once(ROOT/'requests.private.json', packet)
    once(ROOT/'runtime-only.private.json', {'identifier': packet['identifier'], 'requests': []})
    sources = source_hashes()
    for path, sha in sources.items():
        dest = ROOT/'source'/Path(path).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(Path(path).read_bytes())
        if q.r.digest(dest) != sha:
            raise RuntimeError('Source copy changed')
    snapshot = runtime_snapshot(exes, ROOT/'requests.private.json')
    verify_counts(snapshot, packet)
    once(ROOT/'prepared-runtime.private.json', snapshot)
    once(ROOT/'plan.private.json', {'at': q.r.now(), 'version': VERSION, 'entries': entries, 'workers': 4,
        'reconciliationSha256': RECONCILIATION_SHA, 'proposalSha256': PROPOSAL_SHA,
        'requestFileSha256': q.r.digest(ROOT/'requests.private.json'),
        'runtimeOnlyFileSha256': q.r.digest(ROOT/'runtime-only.private.json'),
        'runtimeSha256': q.r.digest(q.ROOT/'runtime.json'),
        'preparedRuntimeSha256': q.r.digest(ROOT/'prepared-runtime.private.json'),
        'sourceHashes': sources, 'executables': exes, 'pythonVersion': sys.version,
        'originalRuntimeAndInputHashes': {str(q.ROOT/p): q.r.digest(q.ROOT/p) for p in [q.ITEMS, 'v3-judge.txt', 'runtime.json', 'v3-loop-launch-protocol.json', 'semantic-development-seal.json']},
        'scope': '194 first attempts only. Four interrupted original requests remain unscorable. No old-file mutation, hosted feedback, standard V3 completion, selection, or reserved data.'})
    print(json.dumps({'preparedCalls': 194, 'planSha256': q.r.digest(ROOT/'plan.private.json'), 'modelCalls': 0}), flush=True)


def verify_plan():
    plan = q.r.read(ROOT/'plan.private.json')
    rec = verify_originals()
    if plan['version'] != VERSION or plan['workers'] != 4 or plan['entries'] != expected_entries(rec):
        raise RuntimeError('Prepared cohort/procedure changed')
    if plan['reconciliationSha256'] != RECONCILIATION_SHA or plan['proposalSha256'] != PROPOSAL_SHA:
        raise RuntimeError('Prepared provenance differs')
    if source_hashes() != plan['sourceHashes']:
        raise RuntimeError('Reviewed source changed')
    for path, sha in plan['sourceHashes'].items():
        if q.r.digest(ROOT/'source'/Path(path).name) != sha:
            raise RuntimeError('Source snapshot changed')
    for path, sha in plan['originalRuntimeAndInputHashes'].items():
        if q.r.digest(path) != sha:
            raise RuntimeError('Frozen input/source seal changed')
    for key, path in [('requestFileSha256', ROOT/'requests.private.json'), ('runtimeOnlyFileSha256', ROOT/'runtime-only.private.json'), ('preparedRuntimeSha256', ROOT/'prepared-runtime.private.json'), ('runtimeSha256', q.ROOT/'runtime.json')]:
        if q.r.digest(path) != plan[key]:
            raise RuntimeError('Prepared file differs')
    if q.r.read(ROOT/'requests.private.json') != requests_for(plan['entries']):
        raise RuntimeError('Prepared requests fail reconstruction')
    for info in plan['executables'].values():
        if executable(info['path']) != info:
            raise RuntimeError('Executable changed')
    if executable(sys.executable) != plan['executables']['python'] or sys.version != plan['pythonVersion']:
        raise RuntimeError('Python runtime differs')
    verify_counts(q.r.read(ROOT/'prepared-runtime.private.json'), q.r.read(ROOT/'requests.private.json'))
    return plan


def review_gate(plan):
    review = q.r.read(ROOT/'reviewed.json')
    if review.get('approved') is not True or review.get('planSha256') != q.r.digest(ROOT/'plan.private.json'):
        raise RuntimeError('Exact external source/plan review required')
    if review.get('noCompetingLocalInference') is not True or review.get('preserveOriginalIncompleteRun') is not True:
        raise RuntimeError('External local ownership and preservation attestation required')
    pids = review.get('retiredProcessIds', [])
    if not set(OLD_PIDS).issubset(pids):
        raise RuntimeError('Review omits prior owners')
    dead(pids)
    return review


@contextlib.contextmanager
def ownership():
    with (ROOT/'runner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Cooperate with the already reviewed future-round coordinator too.
        with (q.ROOT/'.future-round-owner.lock').open('a') as shared:
            fcntl.flock(shared, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield


def attempt(entry, request, stop):
    if stop.is_set():
        raise RuntimeError('Continuation stopped before request')
    check_unattempted(entry)
    directory = ROOT/'responses'/entry['caseId']
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    once(directory/'dispatch-started.json', {'at': q.r.now(), 'pid': os.getpid(), 'ordinal': entry['ordinal'], 'requestSha256': entry['requestSha256']})
    if stop.is_set():
        raise RuntimeError('Continuation stopped after reservation, before HTTP request')
    result = q.local_call(request, directory)
    verify_response(directory, request, result)
    return result


def verify_response(directory, request, result):
    directory = Path(directory)
    audit_support.verify_local({'directory': str(directory), **result}, request)
    if (directory/'response.raw').exists():
        try:
            raw = json.loads((directory/'response.raw').read_bytes())
        except (ValueError, UnicodeDecodeError):
            if result['status'] != 'transport_failed':
                raise RuntimeError('Unparseable raw response was not retained as failed')
            return
        if (directory/'response.json').exists() and raw != q.r.read(directory/'response.json'):
            raise RuntimeError('Raw/parsed response differs')
        choice = (raw.get('choices') or [{}])[0]
        message = choice.get('message', {})
        if raw.get('model') is not None and raw['model'] != request['model']:
            raise RuntimeError('Returned model differs, including on a failed call')
        for field, value in [('usage', raw.get('usage')), ('returnedModel', raw.get('model')), ('finishReason', choice.get('finish_reason')), ('reasoningCharacters', len(message.get('reasoning_content', '') or ''))]:
            if result.get(field) != value:
                raise RuntimeError('Response metadata does not bind raw bytes')
        try:
            output = json.loads(message.get('content', ''))
        except (ValueError, TypeError):
            output = None
        valid = q.valid_judgment(output)
        if output != result['output'] or (result['status'] == 'completed') != (result.get('httpStatus') == 200 and choice.get('finish_reason') == 'stop' and valid):
            raise RuntimeError('Recorded output/status differs from raw response')
    elif result['status'] != 'transport_failed':
        raise RuntimeError('Response bytes missing')


def feed(entries, requests, worker, max_workers=4):
    stop = threading.Event()
    todo = iter(entries)
    records, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        pending = {}
        def submit():
            if stop.is_set():
                return
            e = next(todo, None)
            if e is not None:
                pending[pool.submit(worker, e, requests[e['caseId']], stop)] = e
        for _ in range(max_workers):
            submit()
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            # Classify the whole completed batch before any replacement work.
            for f in done:
                e = pending.pop(f)
                try:
                    f.result()
                    records.append(e['caseId'])
                except Exception as exc:
                    stop.set()
                    errors.append({'caseId': e['caseId'], 'type': type(exc).__name__, 'message': str(exc)})
            print(json.dumps({'finalized': len(records), 'planned': len(entries), 'stopped': stop.is_set(), 'errors': len(errors)}), flush=True)
            for _ in done:
                submit()
    return {'finalizedCaseIds': records, 'errors': errors, 'stopped': stop.is_set()}


def run():
    os.umask(0o077)
    plan = verify_plan()
    with ownership():
        review_gate(plan)
        if (ROOT/'started.json').exists():
            raise RuntimeError('Prior/uncertain continuation; no restart')
        for entry in plan['entries']:
            check_unattempted(entry)
        snapshot = runtime_snapshot(plan['executables'], ROOT/'requests.private.json', q.r.read(ROOT/'prepared-runtime.private.json')['sdk']['loadConfig'])
        verify_counts(snapshot, q.r.read(ROOT/'requests.private.json'))
        once(ROOT/'launch-runtime.private.json', snapshot)
        once(ROOT/'started.json', {'at': q.r.now(), 'pid': os.getpid(), 'reviewSha256': q.r.digest(ROOT/'reviewed.json'), 'planSha256': q.r.digest(ROOT/'plan.private.json')})
        requests = {x['caseId']: x['request'] for x in q.r.read(ROOT/'requests.private.json')['requests']}
        result = feed(plan['entries'], requests, attempt)
        once(ROOT/'dispatch-finished.private.json', {'at': q.r.now(), **result})
        verify_originals()
        end = runtime_snapshot(plan['executables'], ROOT/'runtime-only.private.json', snapshot['sdk']['loadConfig'])
        once(ROOT/'post-dispatch-runtime.private.json', end)
        if result['stopped'] or len(result['finalizedCaseIds']) != 194:
            raise RuntimeError('Continuation incomplete; preserved without resubmission')
        derive_owned()


def execution(rows):
    result = {'rows': len(rows)}
    for name, get in [('inputTokens', lambda r: (r.get('usage') or {}).get('prompt_tokens')), ('outputTokens', lambda r: (r.get('usage') or {}).get('completion_tokens')), ('requestSeconds', lambda r: r.get('seconds'))]:
        values = [get(r) for r in rows]
        known = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0]
        result[name] = {'knownTotal': sum(known), 'missing': len(values)-len(known), 'isLowerBound': len(values)!=len(known)}
    return result


def derive_owned():
    plan = verify_plan()
    review_gate(plan)
    finish = q.r.read(ROOT/'dispatch-finished.private.json')
    targets = {x['caseId'] for x in plan['entries']}
    if finish['stopped'] or finish['errors'] or len(finish['finalizedCaseIds']) != 194 or set(finish['finalizedCaseIds']) != targets:
        raise RuntimeError('Incomplete continuation has no full accounting output')
    post = q.r.read(ROOT/'post-dispatch-runtime.private.json')
    validate_runtime(post, q.load('runtime.json'), q.r.read(ROOT/'prepared-runtime.private.json')['sdk']['loadConfig'])
    rec = q.load(RECONCILIATION)
    unknown = {x['caseId'] for x in rec['uncertainRequests']}
    items = {x['caseId']: x for x in q.load(q.ITEMS)}
    reqs = {x['caseId']: x['request'] for x in q.load('methods/v3/semantic-preflight-requests.private.json')['requests']}
    token_counts = {x['caseId']: x['inputTokens'] for x in q.load('methods/v3/semantic-preflight.json')['counts']}
    records, hashes = [], {}
    for e in q.load('methods/v3/development-dispatch.private.json')['plannedRows']:
        cid = e['caseId']
        origin = 'original_interrupted' if cid in unknown else 'continuation' if cid in targets else 'original_finalized'
        d = ROOT/'responses'/cid if cid in targets else original_path(cid)
        if cid in unknown:
            if (d/'result.json').exists():
                raise RuntimeError('Original uncertain request unexpectedly gained a result')
            result = {'status': 'interrupted_unscorable', 'output': None}
        else:
            result = q.r.read(d/'result.json')
            verify_response(d, reqs[cid], result)
            input_tokens = (result.get('usage') or {}).get('prompt_tokens')
            if input_tokens is not None and input_tokens != token_counts[cid]:
                raise RuntimeError('Server input usage differs from full input preflight')
        for p in sorted(d.iterdir()):
            if p.is_file():
                hashes[str(p)] = q.r.digest(p)
        records.append({'caseId': cid, 'marketId': e['marketId'], 'kind': items[cid]['kind'], 'trial': 1, 'origin': origin, 'directory': str(d), **result})
    if len(records)!=1915 or collections.Counter(x['origin'] for x in records) != {'original_finalized':1717, 'original_interrupted':4, 'continuation':194}:
        raise RuntimeError('Derived cohort accounting differs')
    scores = [q.score_record(items[x['caseId']], x) for x in records]
    report = {'at': q.r.now(), 'version': VERSION, 'originalRunState': 'interrupted_incomplete',
        'planSha256': q.r.digest(ROOT/'plan.private.json'), 'reviewSha256': q.r.digest(ROOT/'reviewed.json'),
        'dispatchFinishedSha256': q.r.digest(ROOT/'dispatch-finished.private.json'), 'postDispatchRuntimeSha256': q.r.digest(ROOT/'post-dispatch-runtime.private.json'),
        'records': records, 'scores': scores, 'rawArtifactHashes': hashes,
        'statuses': dict(collections.Counter(x['status'] for x in records)),
        'byKind': {k: audit_support.counts([x for x in scores if x['kind']==k]) for k in sorted({x['kind'] for x in scores})},
        'executionByOrigin': {k: execution([x for x in records if x['origin']==k]) for k in sorted({x['origin'] for x in records})},
        'qualification': 'Derived development accounting only; four original uncertain calls remain unscorable, all failures retained. Original V3 was interrupted and never completed its standard pipeline. No selection or complete-feedback claim. Natural labels are retrospective factual candidates, not strict settlement gold; control factual labels are provisional agreement diagnostics. Missing usage/duration are explicit lower bounds. Interruption and rescheduling may affect cache/latency; no live or on-chain equivalence.'}
    once(ROOT/'derived-accounting.private.json', report)
    print(json.dumps({'derivedRows':1915, 'uncertainOriginals':4, 'sha256':q.r.digest(ROOT/'derived-accounting.private.json')}), flush=True)


def derive():
    # An interrupted reporting step can be audited separately, but never while
    # its original continuation process still owns inference or output writes.
    with ownership():
        dead([q.r.read(ROOT/'started.json')['pid']])
        derive_owned()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare', 'verify', 'run', 'derive'])
    args = parser.parse_args()
    {'prepare':prepare, 'verify':verify_plan, 'run':run, 'derive':derive}[args.command]()
