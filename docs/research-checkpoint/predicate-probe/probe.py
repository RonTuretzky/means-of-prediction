"""Strict-only, two-call diagnostic; no candidate selection or reserved data."""
import argparse
import collections
import concurrent.futures
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import order_support as o

ROOT = Path(__file__).resolve().parent
ORDER = ROOT.parent / 'qwen-order-probe-20260913'
SIDES = ['A', 'B']
FIELDS = ['verdict', 'evidenceQuote', 'missingConditions']
SCHEMA = {'type': 'object', 'properties': {
    'verdict': {'type': 'string', 'enum': ['YES', 'NO']},
    'evidenceQuote': {'type': 'string'},
    'missingConditions': {'type': 'array', 'items': {'type': 'string'}},
}, 'required': FIELDS.copy(), 'additionalProperties': False}


def valid(output):
    return (isinstance(output, dict) and set(output) == set(FIELDS)
            and output['verdict'] in ['YES', 'NO']
            and isinstance(output['evidenceQuote'], str)
            and isinstance(output['missingConditions'], list)
            and all(isinstance(x, str) for x in output['missingConditions']))


class Validator:
    valid_judgment = staticmethod(valid)


def request_for(baseline, side, prompt):
    o.require(side in SIDES, 'Unknown settlement side')
    result = copy.deepcopy(baseline)
    o.require(len(result['messages']) == 2, 'Unexpected message count')
    o.require([x['role'] for x in result['messages']] == ['system', 'user'], 'Unexpected message roles')
    packet = json.loads(result['messages'][1]['content'])
    o.require(set(packet) == {'email', 'rule'}, 'Unexpected original packet fields')
    o.require(set(packet['rule']) == {'factualA', 'factualB', 'settlementA', 'settlementB', 'abstainWhen', 'limitations'}, 'Full frozen rule missing')
    original = copy.deepcopy(packet)
    packet['targetSettlement'] = side
    result['messages'][0]['content'] = prompt
    result['messages'][1]['content'] = json.dumps(packet, ensure_ascii=False)
    result['response_format'] = {'type': 'json_schema', 'json_schema': {
        'name': 'selected_settlement_judgment', 'strict': True, 'schema': copy.deepcopy(SCHEMA)}}
    o.require({k: packet[k] for k in ['email', 'rule']} == original, 'Full email/rule changed')
    for key in baseline:
        if key not in ['messages', 'response_format']:
            o.require(o.wire(result[key]) == o.wire(baseline[key]), 'Runtime changed: ' + key)
    return result


def gate():
    approval = o.execution_gate()
    path = ORDER / 'summary.private.json'
    o.require(approval['orderSummarySha256'] == o.digest(path), 'Completed order-probe summary differs')
    summary = o.read(path)
    rows = summary['rows']
    expected = {(e['item']['caseId'], v) for e in o.read(ROOT / 'panel.private.json')['cases'] for v in ['original', 'quote-first']}
    o.require(len(rows) == 24 and {(x['record']['caseId'], x['record']['variant']) for x in rows} == expected, 'Order probe incomplete or different panel')
    return approval


def validate_preflight(q):
    report = o.read(ROOT / 'preflight.json')
    packet = o.read(ROOT / 'requests.private.json')
    o.require(report['inputSha256'] == o.digest(ROOT / 'requests.private.json'), 'Preflight input changed')
    runtime = o.read(ROOT / 'runtime.json')
    q.verify_preflight_runtime(report, runtime)
    o.require(report['identifier'] == runtime['identifier'] and report['allFullInputsFit'] is True, 'Wrong model or capacity')
    counts = {r['caseId']: r for r in report['counts']}
    requests = {r['caseId']: r['request'] for r in packet['requests']}
    expected = {e['item']['caseId'] + '/' + side for e in o.read(ROOT / 'panel.private.json')['cases'] for side in SIDES}
    o.require(len(report['counts']) == len(packet['requests']) == len(counts) == len(requests) == 24 and set(counts) == set(requests) == expected, 'Preflight coverage differs')
    for cid, row in counts.items():
        o.require(type(row['inputTokens']) is int and row['inputTokens'] >= 0, 'Invalid input count')
        o.require(row['outputAllowance'] == requests[cid]['max_tokens'] == 2048, 'Output allowance differs')
        o.require(row['inputTokens'] + row['outputAllowance'] <= report['contextLength'], 'Input would be truncated')
    return counts


def preflight():
    gate()
    o.require(not (ROOT / 'preflight.json').exists(), 'Preflight already exists')
    subprocess.run(['node', str(ROOT / 'source/qwen_preflight.mjs'), str(ROOT / 'requests.private.json'), str(ROOT / 'preflight.json')], check=True)
    validate_preflight(o.study_module())


def run():
    gate()
    validate_preflight(o.study_module())
    for marker in (ROOT / 'calls').rglob('started.json'):
        o.require((marker.parent / 'result.json').exists(), 'Uncertain attempt; reconcile before any more calls')
    def pair(entry):
        return [o.call(entry, side, Validator) for side in entry['executionOrder']]
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(pair, o.read(ROOT / 'panel.private.json')['cases']):
            records.extend(rows)
    o.once(ROOT / 'judgments.private.json', records)
    score()


def outcome_from(records):
    if set(records) != set(SIDES) or any(r['status'] != 'completed' or not valid(r.get('output')) for r in records.values()):
        return 'UNSCORABLE'
    a, b = (records[s]['output']['verdict'] == 'YES' for s in SIDES)
    return 'CONFLICT' if a and b else 'A' if a else 'B' if b else 'NEITHER'


def strict_score(item, outcome):
    complete = outcome != 'UNSCORABLE'
    control = item['kind'] == 'control'
    expected = item['expected']
    positive = control and expected in SIDES
    negative = control and not positive
    return {'caseId': item['caseId'], 'marketId': item['marketId'], 'kind': item['kind'],
            'expected': expected if control else None, 'valid': complete, 'settlementOutcome': outcome,
            'strictPass': complete and outcome == expected if positive else complete and outcome == 'NEITHER' if negative else None,
            'falsePositive': complete and outcome in ['A', 'B', 'CONFLICT'] if negative else None,
            'wrongOutcome': complete and outcome in SIDES and outcome != expected if positive else None,
            'conflict': complete and outcome == 'CONFLICT'}


def usage(records):
    values = {'inputTokens': [(r.get('usage') or {}).get('prompt_tokens') for r in records],
              'outputTokens': [(r.get('usage') or {}).get('completion_tokens') for r in records],
              'summedRequestSeconds': [r.get('seconds') for r in records]}
    return {'attempts': len(records), 'completedCalls': sum(r['status'] == 'completed' for r in records),
            **{k: {'knownTotal': sum(x for x in xs if o.known(x)),
                   'missing': sum(not o.known(x) for x in xs),
                   'knownTotalIsLowerBound': any(not o.known(x) for x in xs)} for k, xs in values.items()}}


def counts(scores):
    controls = [r for r in scores if r['kind'] == 'control']
    positives = [r for r in controls if r['expected'] in SIDES]
    negatives = [r for r in controls if r['expected'] not in SIDES]
    return {'pairs': len(scores), 'completedPairs': sum(r['valid'] for r in scores),
            'positiveControls': len(positives), 'negativeControls': len(negatives),
            'completedPositiveControls': sum(r['valid'] for r in positives),
            'completedNegativeControls': sum(r['valid'] for r in negatives),
            'strictPositivePasses': sum(r['strictPass'] is True for r in positives),
            'negativeRejections': sum(r['strictPass'] is True for r in negatives),
            'falseClaims': sum(r['falsePositive'] is True for r in negatives),
            'wrongPositiveSide': sum(r['wrongOutcome'] is True for r in positives),
            'conflicts': sum(r['conflict'] for r in scores)}


def verify_record(record, request, validator, token_count=None):
    directory = Path(record['directory'])
    o.require(record == o.read(directory / 'result.json'), 'Aggregate result differs')
    body = (directory / 'request-wire.json').read_bytes()
    o.require(body == o.wire(request) == o.wire(o.read(directory / 'request.json')), 'Wire reconstruction differs')
    o.require(hashlib.sha256(body).hexdigest() == record['wireRequestSha256'], 'Wire hash differs')
    if record.get('rawResponseSha256'):
        o.require(o.digest(directory / 'response.raw') == record['rawResponseSha256'], 'Raw response changed')
    if record['status'] == 'completed':
        raw = o.read(directory / 'response.raw')
        o.require(raw == o.read(directory / 'response.json'), 'Parsed response differs')
        choice = raw['choices'][0]
        output = json.loads(choice['message']['content'])
        o.require(record['httpStatus'] == 200 and choice['finish_reason'] == 'stop' and validator(output) and output == record['output'], 'Completed output differs')
        o.require(record['usage'] == raw.get('usage') and record['outputFieldOrder'] == list(output), 'Response metadata differs')
        o.validate_response_metadata(record, raw, request['model'])
    tokens = (record.get('usage') or {}).get('prompt_tokens')
    if tokens is not None and token_count is not None:
        o.require(tokens == token_count, 'Full input token accounting differs')


def score():
    gate()
    q = o.study_module()
    token_counts = validate_preflight(q)
    panel = {e['item']['caseId']: e for e in o.read(ROOT / 'panel.private.json')['cases']}
    records = o.read(ROOT / 'judgments.private.json')
    expected = {(cid, side) for cid in panel for side in SIDES}
    o.require(len(records) == 24 and {(r['caseId'], r['variant']) for r in records} == expected, 'Output coverage differs')
    prompt = (ROOT / 'judge.txt').read_text()
    for r in records:
        entry = panel[r['caseId']]
        directory = ROOT / 'calls' / r['caseId'] / r['variant']
        o.require(Path(r['directory']) == directory, 'Unexpected output directory')
        o.require(r['marketId'] == entry['item']['marketId'] and r['kind'] == entry['item']['kind'], 'Output identity differs')
        verify_record(r, request_for(entry['baselineRequest'], r['variant'], prompt), valid,
                      token_counts[r['caseId'] + '/' + r['variant']]['inputTokens'])
    index = {(r['caseId'], r['variant']): r for r in records}
    rows = []
    for cid, entry in panel.items():
        item = entry['item']
        sides = {s: index[(cid, s)] for s in SIDES}
        scored = strict_score(item, outcome_from(sides))
        exact = {s: bool(r.get('output', {}).get('evidenceQuote')) and r['output']['evidenceQuote'] in q.evidence_text(item['email'])
                 if r['status'] == 'completed' else False for s, r in sides.items()}
        scored['selectedSideExactQuote'] = exact[scored['settlementOutcome']] if scored['settlementOutcome'] in SIDES else None
        scored['yesPredicatesWithoutExactQuote'] = sum(r['status'] == 'completed' and r['output']['verdict'] == 'YES' and not exact[s] for s, r in sides.items())
        rows.append({'selectionBucket': entry['selectionBucket'], 'score': scored, 'sideExactQuotes': exact, 'records': sides})
    comparisons = {}
    order_rows = o.read(ORDER / 'summary.private.json')['rows']
    for variant in ['original', 'quote-first']:
        group = [row for row in order_rows if row['record']['variant'] == variant]
        baseline_scores = []
        for row in group:
            r = row['record']; entry = panel[r['caseId']]
            o.require(Path(r['directory']) == ORDER / 'calls' / r['caseId'] / variant, 'Unexpected comparison directory')
            verify_record(r, o.reorder(entry['baselineRequest'], variant), q.valid_judgment)
            actual = q.score_record(entry['item'], r)
            o.require(actual == row['score'], 'Order comparison cached score differs')
            baseline_scores.append(strict_score(entry['item'], actual['settlementOutcome']))
        common = {r['caseId'] for r in baseline_scores if r['valid']} & {r['score']['caseId'] for r in rows if r['score']['valid']}
        comparisons[variant] = {'combinedCallCounts': counts(baseline_scores),
            'combinedCallUsage': usage([r['record'] for r in group]),
            'commonCompletedPairs': len(common),
            'commonCombinedCallCounts': counts([r for r in baseline_scores if r['caseId'] in common]),
            'commonSplitCounts': counts([r['score'] for r in rows if r['score']['caseId'] in common]),
            'pairedOutcomes': [{'caseId': r['caseId'], 'combined': r['settlementOutcome'],
                               'split': next(x['score']['settlementOutcome'] for x in rows if x['score']['caseId'] == r['caseId'])} for r in baseline_scores]}
    result = {'at': o.now(), 'inputFreezeSha256': o.digest(ROOT / 'input-freeze.json'),
              'protocolSha256': o.digest(ROOT / 'protocol.json'), 'orderSummarySha256': o.digest(ORDER / 'summary.private.json'),
              'strictOnly': True, 'factualRecall': None, 'selectionEligible': False,
              'splitCounts': counts([r['score'] for r in rows]), 'splitUsage': usage(records),
              'yesPredicatesWithoutExactQuote': sum(r['score']['yesPredicatesWithoutExactQuote'] for r in rows),
              'exclusiveClaimsWithoutExactQuote': sum(r['score']['settlementOutcome'] in SIDES and not r['score']['selectedSideExactQuote'] for r in rows),
              'completedOutputOrderMatchesRequested': sum(r['status'] == 'completed' and r['outputFieldOrder'] == FIELDS for r in records),
              'completedOutputOrderDiffersFromRequested': sum(r['status'] == 'completed' and r['outputFieldOrder'] != FIELDS for r in records),
              'comparisons': comparisons, 'rows': rows,
              'qualification': 'Selected 12-case old-development diagnostic: six positive and four negative synthetic controls; two natural cases have no strict gold. Full original frozen rules and emails are preserved. Splitting the task also changes the system prompt and output schema, so this is not a pure causal ablation. Two model calls and up to 4096 total output tokens per pair, versus one call and 2048 for a combined judgment. Quote order is fixed verdict-first before either probe runs. No factual diagnostic is produced, no main selection gate can be satisfied by this probe, and no automatic adoption is permitted. Compared runs are sequential with different concurrent scheduling/cache histories; timings are observational.'}
    o.once(ROOT / 'summary.private.json', result)
    print(json.dumps({'summary': str(ROOT / 'summary.private.json'), 'counts': result['splitCounts'], 'usage': result['splitUsage']}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['preflight', 'run', 'score'])
    args = parser.parse_args()
    {'preflight': preflight, 'run': run, 'score': score}[args.phase]()
