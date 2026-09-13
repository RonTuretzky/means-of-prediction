"""Frozen 2x2 rule/judge attribution diagnostic on twelve old development cases."""
import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import basis_audit_support as audit
import order_support as o

ROOT = Path(__file__).resolve().parent
METHODS = ['baseline', 'v3']
VARIANTS = [rule + '-rule_' + judge + '-judge' for rule in METHODS for judge in METHODS]


def components(variant):
    o.require(variant in VARIANTS, 'Unknown crossed variant')
    rule, judge = variant.split('_')
    return rule.removesuffix('-rule'), judge.removesuffix('-judge')


def request_for(entry, variant, inputs):
    rule_method, judge_method = components(variant)
    rule = inputs['rules'][rule_method][entry['item']['marketId']]
    if rule['status'] != 'completed':
        return None
    original = entry['baselineRequest']
    request = copy.deepcopy(original)
    o.require([x['role'] for x in request['messages']] == ['system', 'user'], 'Message structure differs')
    o.require(list(request['response_format']['json_schema']['schema']['properties']) == o.ORIGINAL_ORDER, 'Schema order differs')
    packet = json.loads(request['messages'][1]['content'])
    o.require(set(packet) == {'email', 'rule'}, 'Unexpected baseline payload')
    packet['rule'] = rule['output']
    request['messages'][1]['content'] = json.dumps(packet, ensure_ascii=False)
    request['messages'][0]['content'] = inputs['prompts'][judge_method]
    if variant == VARIANTS[0]:
        o.require(o.wire(request) == o.wire(original), 'Original frozen baseline replay differs')
    return request


def verify_panel():
    seal = o.read(ROOT / 'panel-freeze.json')
    o.require(o.digest(ROOT / 'panel.private.json') == seal['panelSha256'], 'Panel changed')
    rows = o.read(ROOT / 'panel.private.json')['cases']
    o.require(len(rows) == len({x['item']['caseId'] for x in rows}) == 12, 'Panel coverage differs')
    for i, row in enumerate(rows):
        o.require(row['executionOrder'] == VARIANTS[i % 4:] + VARIANTS[:i % 4], 'Frozen cyclic order changed')
    return rows


def prepare():
    o.require(not (ROOT / 'input-freeze.json').exists(), 'Inputs already frozen')
    o.require(not (o.STUDY / 'selection.json').exists(), 'Development already closed')
    rows = verify_panel()
    q = o.study_module()
    external = {}
    inputs = {'rules': {}, 'prompts': {}}
    for method in METHODS:
        directory = o.STUDY / 'methods' / method
        freeze = o.read(directory / 'rules-freeze.json')
        o.require(o.digest(directory / 'rules.json') == freeze['recordsSha256'], 'Rule aggregate changed')
        for name, sha in freeze['fileHashes'].items():
            o.require(o.digest(o.STUDY / name) == sha, 'Frozen rule artifact changed')
        rules = o.read(directory / 'rules.json')
        o.require(len(rules) == len({r['marketId'] for r in rules}) == 241, 'Incomplete rule cohort')
        index = {r['marketId']: r for r in rules}
        inputs['rules'][method] = {row['item']['marketId']: index[row['item']['marketId']] for row in rows}
        inputs['prompts'][method] = (o.STUDY / (method + '-judge.txt')).read_text()
        for path in [directory / 'rules.json', directory / 'rules-freeze.json', o.STUDY / (method + '-judge.txt')]:
            external[str(path)] = o.digest(path)
        for record in inputs['rules'][method].values():
            path = Path(record['directory'])
            q.r.verify_model_artifact(path, o.read(path / 'job.json'), record)
            for source in path.iterdir():
                if source.is_file(): external[str(source)] = o.digest(source)
    o.once(ROOT / 'inputs.private.json', inputs)
    requests = []
    unavailable = []
    for entry in rows:
        for variant in VARIANTS:
            request = request_for(entry, variant, inputs)
            cid = entry['item']['caseId']
            if request is None:
                unavailable.append({'caseId': cid, 'variant': variant})
                continue
            directory = ROOT / 'calls' / cid / variant
            o.once(directory / 'request.json', request)
            (directory / 'request-wire.json').write_bytes(o.wire(request))
            requests.append({'caseId': cid + '/' + variant, 'request': request})
    o.once(ROOT / 'requests.private.json', {'identifier': o.read(ROOT / 'runtime.json')['identifier'], 'requests': requests})
    o.once(ROOT / 'protocol.json', {'at': o.now(), 'plannedRows': 48, 'plannedCalls': len(requests),
        'unavailableRules': unavailable, 'methods': METHODS, 'variants': VARIANTS, 'workers': 4,
        'procedure': 'One fresh isolated call for each available crossed cell. Four concurrent case blocks, four variants serial within each block. Each cyclic starting position occurs three times. Identical schema, full email, metadata, model, sampling and cap. Only frozen rule and judge prompt vary. Failed rules remain unavailable, no substitution or resampling. No answer repair or automatic selection.',
        'qualification': 'Selected twelve old-development cases and single frozen rule draws support within-panel attribution only. Replays can vary, including at temperature zero. Cyclic position balance does not balance all carryover; timing remains observational. No independent accuracy or all-market settlement coverage claim. Prepare reads no V3 judgments; execute only after full V3 and basis completion, local release and separate review.'})
    files = {str(p.relative_to(ROOT)): o.digest(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    o.once(ROOT / 'input-freeze.json', {'at': o.now(), 'fileHashes': files, 'externalFileHashes': external, 'pythonVersion': sys.version})
    o.frozen()
    print(json.dumps({'plannedRows': 48, 'plannedCalls': len(requests), 'inputFreezeSha256': o.digest(ROOT / 'input-freeze.json')}))


def gate():
    approval = o.execution_gate()
    for filename, key in [('methods/v3/development-judgments.private.json', 'v3JudgmentsSha256'), ('v3-local-released.json', 'v3LocalReleaseSha256')]:
        o.require(o.digest(o.STUDY / filename) == approval[key], 'V3 completion/release changed')
    rows = o.read(o.STUDY / 'methods/v3/development-judgments.private.json')
    o.require(len(rows) == len({x['caseId'] for x in rows}) == 1915, 'V3 not complete')
    basis = ROOT.parent / 'qwen-basis-probe-20260913/summary.private.json'
    o.require(o.digest(basis) == approval['basisSummarySha256'], 'Basis diagnostic not complete or changed')
    return approval


def validate_preflight(q):
    report = o.read(ROOT / 'preflight.json')
    packet = o.read(ROOT / 'requests.private.json')
    runtime = o.read(ROOT / 'runtime.json')
    q.verify_preflight_runtime(report, runtime)
    o.require(report['identifier'] == runtime['identifier'] and report['allFullInputsFit'] is True, 'Wrong model or capacity')
    o.require(report['inputSha256'] == o.digest(ROOT / 'requests.private.json'), 'Preflight input changed')
    counts = {row['caseId']: row for row in report['counts']}
    requests = {row['caseId']: row['request'] for row in packet['requests']}
    inputs = o.read(ROOT / 'inputs.private.json')
    expected = {row['item']['caseId'] + '/' + variant: request_for(row, variant, inputs)
                for row in verify_panel() for variant in VARIANTS if request_for(row, variant, inputs) is not None}
    o.require(len(counts) == len(report['counts']) == len(requests) == len(packet['requests']) == len(expected), 'Preflight coverage differs')
    o.require(requests == expected and set(counts) == set(expected), 'Exact full requests differ')
    for cid, count in counts.items():
        o.require(type(count['inputTokens']) is int and count['inputTokens'] >= 0, 'Invalid token count')
        o.require(count['outputAllowance'] == requests[cid]['max_tokens'] == 2048, 'Output cap differs')
        o.require(count['inputTokens'] + count['outputAllowance'] <= report['contextLength'], 'Truncated input')
    return counts


def preflight():
    gate()
    o.require(not (ROOT / 'preflight.json').exists(), 'Preflight already exists')
    subprocess.run(['node', str(ROOT / 'source/qwen_preflight.mjs'), str(ROOT / 'requests.private.json'), str(ROOT / 'preflight.json')], check=True)
    validate_preflight(o.study_module())


def run():
    gate()
    q = o.study_module()
    validate_preflight(q)
    o.once(ROOT / 'run-started.json', {'at': o.now(), 'pid': os.getpid()})
    for marker in (ROOT / 'calls').rglob('started.json'):
        o.require((marker.parent / 'result.json').exists(), 'Uncertain attempt; reconcile before calls')
    inputs = o.read(ROOT / 'inputs.private.json')
    def block(entry):
        records = []
        for variant in entry['executionOrder']:
            if request_for(entry, variant, inputs) is None:
                records.append({'caseId': entry['item']['caseId'], 'marketId': entry['item']['marketId'],
                    'kind': entry['item']['kind'], 'trial': 1, 'variant': variant, 'status': 'rule_unavailable', 'output': None})
            else:
                records.append(o.call(entry, variant, q))
        return records
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(block, verify_panel()): records.extend(rows)
    o.once(ROOT / 'judgments.private.json', records)
    score()


def summarize(rows):
    result = o.summary(rows)
    actual = [x for x in rows if x['record']['status'] != 'rule_unavailable']
    result['usage'] = o.summary(actual)['usage']
    result['completedOutputOrderMatchesRequested'] = sum(x['record']['status'] == 'completed' and x['record'].get('outputFieldOrder') == o.ORIGINAL_ORDER for x in rows)
    result['completedOutputOrderDiffersFromRequested'] = sum(x['record']['status'] == 'completed' and x['record'].get('outputFieldOrder') != o.ORIGINAL_ORDER for x in rows)
    result['ruleUnavailable'] = sum(x['record']['status'] == 'rule_unavailable' for x in rows)
    result['actualCalls'] = len(rows) - result['ruleUnavailable']
    return result


def score():
    gate()
    q = o.study_module()
    counts = validate_preflight(q)
    inputs = o.read(ROOT / 'inputs.private.json')
    panel = {row['item']['caseId']: row for row in verify_panel()}
    records = o.read(ROOT / 'judgments.private.json')
    expected = {(cid, variant) for cid in panel for variant in VARIANTS}
    o.require(len(records) == 48 and {(r['caseId'], r['variant']) for r in records} == expected, 'Output coverage differs')
    # Completed V3 benchmark outputs are read only after the execution gate;
    # they never enter the panel, frozen requests, or preparation.
    v3_records = {r['caseId']: r for r in o.read(o.STUDY / 'methods/v3/development-judgments.private.json')}
    rows, replay, v3_replay = [], [], []
    for record in records:
        entry = panel[record['caseId']]
        request = request_for(entry, record['variant'], inputs)
        if request is None:
            o.require(record['status'] == 'rule_unavailable' and record['output'] is None and 'directory' not in record, 'Unavailable rule was judged')
        else:
            directory = ROOT / 'calls' / record['caseId'] / record['variant']
            o.require(str(directory) == record['directory'] and o.read(directory / 'result.json') == record, 'Aggregate identity differs')
            body = (directory / 'request-wire.json').read_bytes()
            o.require(body == o.wire(request) == o.wire(o.read(directory / 'request.json')), 'Exact request differs')
            o.require(hashlib.sha256(body).hexdigest() == record['wireRequestSha256'], 'Wire hash differs')
            # All crossed cells use the unchanged original schema. This selects
            # the original-schema validator, without changing stored outputs.
            audit.validate_raw_record({**record, 'variant': 'original'}, directory, o.read(ROOT / 'runtime.json')['identifier'], q)
            tokens = (record.get('usage') or {}).get('prompt_tokens')
            if tokens is not None: o.require(tokens == counts[record['caseId'] + '/' + record['variant']]['inputTokens'], 'Full input token accounting differs')
        rows.append({'selectionBucket': entry['selectionBucket'], 'record': record, 'score': q.score_record(entry['item'], record)})
        if record['variant'] == VARIANTS[0]: replay.append(o.replay_agreement(record, entry['baselineRecord'], q))
        if record['variant'] == VARIANTS[3]: v3_replay.append(o.replay_agreement(record, v3_records[record['caseId']], q))
    common = {cid for cid in panel if all(r['status'] == 'completed' for r in records if r['caseId'] == cid)}
    result = {'at': o.now(), 'protocolSha256': o.digest(ROOT / 'protocol.json'), 'inputFreezeSha256': o.digest(ROOT / 'input-freeze.json'),
        'runApprovalSha256': o.digest(ROOT / 'run-approved.json'),
        'variantSummaries': {v: summarize([r for r in rows if r['record']['variant'] == v]) for v in VARIANTS},
        'commonCompletedCases': len(common),
        'commonCompletedSummaries': {v: summarize([r for r in rows if r['record']['variant'] == v and r['record']['caseId'] in common]) for v in VARIANTS},
        'baselineReplayAgreement': replay, 'v3ReplayAgreement': v3_replay,
        'rows': rows, 'qualification': o.read(ROOT / 'protocol.json')['qualification']}
    o.once(ROOT / 'summary.private.json', result)
    print(json.dumps({'variantSummaries': result['variantSummaries'], 'commonCompletedCases': len(common)}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['prepare', 'preflight', 'run', 'score'])
    phase = parser.parse_args().phase
    globals()[phase]()
