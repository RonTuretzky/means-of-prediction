"""Bounded explicit-evidence-basis diagnostic, without changing final answers."""
import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import order_support as o

ROOT = Path(__file__).resolve().parent
VARIANTS = ['original', 'basis-first']
FIELDS = o.ORIGINAL_ORDER
BASIS_FIELDS = ['sourceQuote', 'entity', 'quantity', 'comparison']
LIMITS = {'sourceQuote': 400, 'entity': 160, 'quantity': 160, 'comparison': 300}
BASIS_SCHEMA = {'type': 'object', 'properties': {
    key: {'type': 'string' if key == 'sourceQuote' else ['string', 'null'], 'maxLength': LIMITS[key]}
    for key in BASIS_FIELDS}, 'required': BASIS_FIELDS.copy(), 'additionalProperties': False}
APPENDIX = '''
Before the five final fields, provide decisionBasis: a compact evidence record, not a narrative explanation. sourceQuote is an exact contiguous quote from the supplied body, or empty if none supports a relevant observation. entity names the reported subject and event; quantity records the relevant observed value with its metric, unit and period. comparison records a brief arithmetic expression, inequality, or named-result/time comparison against the frozen factual predicates. Derive arithmetic only from explicitly reported components and keep the sign and outcome-label mapping exact. Use null for entity, quantity or comparison when unknown or inapplicable; do not invent a numeric value for a nonnumeric event. This record does not itself establish authority, timeliness or finality: apply the original settlement branches independently. Then provide the original five fields with their unchanged meanings, including the original evidenceQuote. Keep every field concise; output only the required JSON.'''


def request_for(original, variant):
    o.require(variant in VARIANTS, 'Unknown variant')
    result = copy.deepcopy(original)
    schema = result['response_format']['json_schema']['schema']
    o.require(list(schema['properties']) == FIELDS and schema['required'] == FIELDS, 'Baseline schema differs')
    o.require(len(result['messages']) == 2 and [x['role'] for x in result['messages']] == ['system', 'user'], 'Baseline messages differ')
    if variant == 'basis-first':
        result['messages'][0]['content'] += APPENDIX
        schema['properties'] = {'decisionBasis': copy.deepcopy(BASIS_SCHEMA), **schema['properties']}
        schema['required'] = ['decisionBasis', *FIELDS]
    # Reversing the declared intervention must recover identical bytes.
    restored = copy.deepcopy(result)
    if variant == 'basis-first':
        restored['messages'][0]['content'] = restored['messages'][0]['content'][:-len(APPENDIX)]
        del restored['response_format']['json_schema']['schema']['properties']['decisionBasis']
        restored['response_format']['json_schema']['schema']['required'] = FIELDS.copy()
    o.require(o.wire(restored) == o.wire(original), 'Another input changed')
    return result


def valid(output, variant, q):
    if variant == 'original':
        return q.valid_judgment(output)
    if variant != 'basis-first' or not isinstance(output, dict) or set(output) != set(FIELDS + ['decisionBasis']):
        return False
    basis = output['decisionBasis']
    if not isinstance(basis, dict) or set(basis) != set(BASIS_FIELDS):
        return False
    for key, value in basis.items():
        if value is None and key != 'sourceQuote':
            continue
        if not isinstance(value, str) or len(value) > LIMITS[key]:
            return False
    return q.valid_judgment({key: output[key] for key in FIELDS})


def scoring_record(record, q):
    # Never repair or override a verdict using the basis. Invalid schemas remain failures.
    result = copy.deepcopy(record)
    if record['status'] == 'completed' and valid(record.get('output'), record['variant'], q):
        result['output'] = {key: record['output'][key] for key in FIELDS}
    else:
        result['status'] = 'failed'
        result['output'] = None
    return result


def order_matches(record):
    fields = FIELDS if record['variant'] == 'original' else ['decisionBasis', *FIELDS]
    if record.get('outputFieldOrder') != fields:
        return False
    return record['variant'] == 'original' or list(record['output']['decisionBasis']) == BASIS_FIELDS


def gate():
    approval = o.execution_gate()  # Also binds complete V2 and all frozen sources.
    judgments = o.STUDY / 'methods/v3/development-judgments.private.json'
    o.require(approval['v3JudgmentsSha256'] == o.digest(judgments), 'Completed V3 differs')
    rows = o.read(judgments)
    o.require(len(rows) == len({x['caseId'] for x in rows}) == 1915, 'V3 incomplete')
    o.require((o.STUDY / 'methods/v3/development-summary.json').exists(), 'V3 summary missing')
    return approval


def validate_preflight(q):
    report = o.read(ROOT / 'preflight.json')
    packet = o.read(ROOT / 'requests.private.json')
    o.require(report['inputSha256'] == o.digest(ROOT / 'requests.private.json'), 'Preflight input changed')
    runtime = o.read(ROOT / 'runtime.json')
    q.verify_preflight_runtime(report, runtime)
    o.require(report['identifier'] == runtime['identifier'] and report['allFullInputsFit'] is True, 'Wrong model or capacity')
    counts = {row['caseId']: row for row in report['counts']}
    requests = {row['caseId']: row['request'] for row in packet['requests']}
    expected = {entry['item']['caseId'] + '/' + variant for entry in o.read(ROOT / 'panel.private.json')['cases'] for variant in VARIANTS}
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
    q = o.study_module()
    validate_preflight(q)
    for marker in (ROOT / 'calls').rglob('started.json'):
        o.require((marker.parent / 'result.json').exists(), 'Uncertain attempt; reconcile before more calls')
    def pair(entry):
        results = []
        for variant in entry['executionOrder']:
            validator = SimpleNamespace(valid_judgment=lambda output: valid(output, variant, q))
            results.append(o.call(entry, variant, validator))
        return results
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(pair, o.read(ROOT / 'panel.private.json')['cases']):
            records.extend(rows)
    o.once(ROOT / 'judgments.private.json', records)
    score()


def summary(rows):
    result = o.summary(rows)
    result['completedOutputOrderMatchesRequested'] = sum(x['record']['status'] == 'completed' and order_matches(x['record']) for x in rows)
    result['completedOutputOrderDiffersFromRequested'] = sum(x['record']['status'] == 'completed' and not order_matches(x['record']) for x in rows)
    basis = [x for x in rows if x['record']['status'] == 'completed' and x['record']['variant'] == 'basis-first']
    result['basisQuoteDiagnostics'] = {'rows': len(basis), 'exactNonempty': sum(x['basisQuoteExact'] is True for x in basis),
        'empty': sum(not x['record']['output']['decisionBasis']['sourceQuote'] for x in basis),
        'nonemptyNotExact': sum(bool(x['record']['output']['decisionBasis']['sourceQuote']) and not x['basisQuoteExact'] for x in basis)}
    return result


def validate_raw_record(record, directory, identifier, q):
    """Reconcile failures and successes; unknown rejection metadata stays unknown."""
    metadata = ['finishReason', 'usage', 'returnedModel', 'reasoningCharacters', 'outputFieldOrder']
    if not record.get('rawResponseSha256'):
        o.require(record['status'] == 'transport_failed' and record.get('output') is None, 'Missing raw bytes for parsed result')
        o.require(all(record.get(key) is None for key in metadata), 'Invented metadata without response bytes')
        return
    o.require(o.digest(directory / 'response.raw') == record['rawResponseSha256'], 'Raw response changed')
    try:
        raw = o.read(directory / 'response.raw')
    except (ValueError, UnicodeDecodeError):
        o.require(record['status'] == 'transport_failed' and record.get('output') is None, 'Unparseable raw response was scored')
        o.require(all(record.get(key) is None for key in metadata), 'Invented metadata for unparseable response')
        o.require(not (directory / 'response.json').exists(), 'Parsed artifact exists for unparseable bytes')
        return
    o.require(isinstance(raw, dict), 'Unexpected response envelope; preserve and reconcile')
    o.require(raw == o.read(directory / 'response.json'), 'Parsed response differs')
    choice = (raw.get('choices') or [{}])[0]
    message = choice.get('message', {})
    try:
        output = json.loads(message.get('content', ''))
    except (ValueError, TypeError):
        output = None
    status = 'completed' if record['httpStatus'] == 200 and choice.get('finish_reason') == 'stop' and valid(output, record['variant'], q) else 'failed'
    o.require(record['status'] == status and record.get('output') == output, 'Raw-bound completion status or output differs')
    expected = {'finishReason': choice.get('finish_reason'), 'usage': raw.get('usage'),
        'returnedModel': raw.get('model'), 'reasoningCharacters': len(message.get('reasoning_content', '') or ''),
        'outputFieldOrder': list(output) if isinstance(output, dict) else None}
    for key, value in expected.items():
        o.require(record.get(key) == value, 'Raw-bound metadata differs: ' + key)
    if raw.get('model') is not None:
        o.require(raw['model'] == identifier, 'Returned model differs from pinned instance')
    if status == 'completed':
        o.require(raw.get('model') == identifier, 'Completed response lacks pinned model identity')


def score():
    gate()
    q = o.study_module()
    counts = validate_preflight(q)
    panel = {x['item']['caseId']: x for x in o.read(ROOT / 'panel.private.json')['cases']}
    records = o.read(ROOT / 'judgments.private.json')
    expected = {(cid, variant) for cid in panel for variant in VARIANTS}
    o.require(len(records) == 24 and {(x['caseId'], x['variant']) for x in records} == expected, 'Output coverage differs')
    rows, replay = [], []
    for record in records:
        entry = panel[record['caseId']]
        directory = ROOT / 'calls' / record['caseId'] / record['variant']
        o.require(Path(record['directory']).resolve() == directory.resolve(), 'Call directory differs')
        o.require(record == o.read(directory / 'result.json'), 'Aggregate result changed')
        request = request_for(entry['baselineRequest'], record['variant'])
        body = (directory / 'request-wire.json').read_bytes()
        o.require(body == o.wire(request) == o.wire(o.read(directory / 'request.json')), 'Request reconstruction differs')
        o.require(hashlib.sha256(body).hexdigest() == record['wireRequestSha256'], 'Wire hash differs')
        validate_raw_record(record, directory, o.read(ROOT / 'runtime.json')['identifier'], q)
        tokens = (record.get('usage') or {}).get('prompt_tokens')
        if tokens is not None:
            o.require(tokens == counts[record['caseId'] + '/' + record['variant']]['inputTokens'], 'Full input token accounting differs')
        normalized = scoring_record(record, q)
        scored = q.score_record(entry['item'], normalized)
        basis = (record.get('output') or {}).get('decisionBasis')
        quote = basis.get('sourceQuote', '') if isinstance(basis, dict) else ''
        rows.append({'selectionBucket': entry['selectionBucket'], 'record': record, 'score': scored,
                     'basisQuoteExact': bool(quote) and quote in q.evidence_text(entry['item']['email']) if basis else None})
        if record['variant'] == 'original':
            replay.append(o.replay_agreement(normalized, entry['baselineRecord'], q))
    common = {cid for cid in panel if all(next(x for x in rows if x['record']['caseId'] == cid and x['record']['variant'] == variant)['score']['valid'] for variant in VARIANTS)}
    result = {'at': o.now(), 'inputFreezeSha256': o.digest(ROOT / 'input-freeze.json'), 'protocolSha256': o.digest(ROOT / 'protocol.json'),
        'variantSummaries': {v: summary([x for x in rows if x['record']['variant'] == v]) for v in VARIANTS},
        'commonCompletedPairs': len(common), 'commonCompletedSummaries': {v: summary([x for x in rows if x['record']['variant'] == v and x['record']['caseId'] in common]) for v in VARIANTS},
        'originalReplayVsEarlierBaseline': replay, 'rows': rows,
        'qualification': 'Twelve selected old-development cases reused from earlier diagnostics, including three baseball controls from one event. No independent accuracy estimate. Prompt appendix and schema both change; extra basis fields are reported but never repair final verdicts or grant quote-grounding credit. Two natural labels are factual diagnostics, not strict settlement gold. Concurrent latency is observational. No automatic adoption.'}
    o.once(ROOT / 'summary.private.json', result)
    print(json.dumps({'summary': str(ROOT / 'summary.private.json'), 'variantSummaries': result['variantSummaries']}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['preflight', 'run', 'score'])
    args = parser.parse_args()
    {'preflight': preflight, 'run': run, 'score': score}[args.phase]()
