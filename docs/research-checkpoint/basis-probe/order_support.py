"""Bounded paired order diagnostic on old development inputs only."""
import argparse
import collections
import concurrent.futures
import copy
import datetime
import hashlib
import http.client
import importlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent / 'astra-qwen-nyt-round1-20260912'
SDK = Path('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs')
VARIANTS = ['original', 'quote-first']
ORIGINAL_ORDER = ['factualOutcome', 'outcomeA', 'outcomeB', 'evidenceQuote', 'missingConditions']
QUOTE_ORDER = ['evidenceQuote', 'factualOutcome', 'outcomeA', 'outcomeB', 'missingConditions']


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def wire(value):
    # This is exactly the baseline local_call serializer, preserving order.
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


def once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    path.chmod(0o600)


def study_module():
    source = ROOT / 'source'
    sys.path.insert(0, str(source))
    module = importlib.import_module('qwen_round1')
    for path in source.glob('*.py'):
        if path.stem in sys.modules:
            actual = getattr(sys.modules[path.stem], '__file__', None)
            require(actual is not None and Path(actual).resolve() == path.resolve(), 'Unsealed module loaded: ' + path.stem)
    require(Path(module.__file__).resolve() == (source / 'qwen_round1.py').resolve(), 'Wrong study module')
    return module


def reorder(request, variant):
    require(variant in VARIANTS, 'Unknown variant')
    result = copy.deepcopy(request)
    schema = result['response_format']['json_schema']['schema']
    require(list(schema['properties']) == ORIGINAL_ORDER and schema['required'] == ORIGINAL_ORDER, 'Unexpected baseline order')
    if variant == 'quote-first':
        properties = schema['properties']
        schema['properties'] = {key: properties[key] for key in QUOTE_ORDER}
        schema['required'] = QUOTE_ORDER.copy()
    # Same field types, required set, schema semantics and every other input.
    expected = copy.deepcopy(request)
    schema_back = copy.deepcopy(schema)
    schema_back['properties'] = {key: schema_back['properties'][key] for key in ORIGINAL_ORDER}
    schema_back['required'] = ORIGINAL_ORDER.copy()
    result_back = copy.deepcopy(result)
    result_back['response_format']['json_schema']['schema'] = schema_back
    require(wire(result_back) == wire(expected), 'Order variant changed another input')
    return result


def frozen():
    seal = read(ROOT / 'input-freeze.json')
    amendments = {}
    amendment_path = ROOT / 'reporting-amendment-v1.json'
    if amendment_path.exists():
        amendment = read(amendment_path)
        require(amendment['inputFreezeSha256'] == digest(ROOT / 'input-freeze.json'), 'Reporting amendment has a different input freeze')
        amendments = amendment['changes']
        require(set(amendments) == {'probe.py', 'test_probe.py'}, 'Unexpected reporting amendment targets')
        for name, change in amendments.items():
            require(change['originalSha256'] == seal['fileHashes'][name], 'Original reporting source hash differs')
            original = (ROOT / change['originalCopy']).resolve()
            require(original.is_relative_to(ROOT) and digest(original) == change['originalSha256'], 'Preserved original reporting source differs')
    for name, expected in seal['fileHashes'].items():
        if name in amendments:
            expected = amendments[name]['currentSha256']
        require(digest(ROOT / name) == expected, 'Frozen probe file changed: ' + name)
    for name, expected in seal['externalFileHashes'].items():
        require(digest(name) == expected, 'Frozen external input changed: ' + name)
    require(sys.version == seal['pythonVersion'], 'Python runtime differs')
    return seal


def execution_gate():
    frozen()
    approval = read(ROOT / 'reviewed.json')
    require(approval['approved'] is True and approval['inputFreezeSha256'] == digest(ROOT / 'input-freeze.json'), 'Probe review differs')
    amendment = ROOT / 'reporting-amendment-v1.json'
    require(approval.get('reportingAmendmentSha256') == (digest(amendment) if amendment.exists() else None), 'Review does not cover reporting amendment')
    gate = read(ROOT / 'run-approved.json')
    require(gate['inputFreezeSha256'] == digest(ROOT / 'input-freeze.json'), 'Run gate differs')
    require(gate['reviewSha256'] == digest(ROOT / 'reviewed.json'), 'Run gate does not cover final review')
    judgments = STUDY / 'methods/v2/development-judgments.private.json'
    require(gate['v2JudgmentsSha256'] == digest(judgments), 'Completed v2 input differs')
    rows = read(judgments)
    require(len(rows) == len({x['caseId'] for x in rows}) == 1915, 'V2 not fully completed')
    require((STUDY / 'methods/v2/development-summary.json').exists(), 'V2 report missing')
    require(not (STUDY / 'selection.json').exists(), 'Study selection already closed')
    # The human-readable coordination gate additionally confirms no local jobs.
    require(gate['localInferenceQuiescent'] is True, 'Local model is not released for the probe')
    return gate


def validate_preflight(q):
    preflight = read(ROOT / 'preflight.json')
    packet = read(ROOT / 'requests.private.json')
    runtime = read(ROOT / 'runtime.json')
    require(preflight['inputSha256'] == digest(ROOT / 'requests.private.json'), 'Preflight input changed')
    q.verify_preflight_runtime(preflight, runtime)
    require(preflight['identifier'] == runtime['identifier'] and preflight['allFullInputsFit'] is True, 'Wrong preflight model or capacity')
    counts = {row['caseId']: row for row in preflight['counts']}
    requests = {row['caseId']: row['request'] for row in packet['requests']}
    require(len(counts) == len(preflight['counts']) == len(requests) == 24 and set(counts) == set(requests), 'Preflight coverage differs')
    for case_id, count in counts.items():
        require(type(count['inputTokens']) is int and count['inputTokens'] >= 0, 'Invalid token count')
        require(count['outputAllowance'] == requests[case_id]['max_tokens'] == 2048, 'Output allowance changed')
        require(count['inputTokens'] + count['outputAllowance'] <= preflight['contextLength'], 'Input would be truncated')
    for row in read(ROOT / 'panel.private.json')['cases']:
        cid = row['item']['caseId']
        require(counts[cid + '/original']['inputTokens'] == counts[cid + '/quote-first']['inputTokens'], 'Paired template input counts differ')
    return counts


def preflight():
    execution_gate()
    require(not (ROOT / 'preflight.json').exists(), 'Preflight already exists')
    subprocess.run(['node', str(ROOT / 'source/qwen_preflight.mjs'), str(ROOT / 'requests.private.json'), str(ROOT / 'preflight.json')], check=True)
    validate_preflight(study_module())


def call(entry, variant, q):
    item = entry['item']
    directory = ROOT / 'calls' / item['caseId'] / variant
    body = (directory / 'request-wire.json').read_bytes()
    request = read(directory / 'request.json')
    require(body == wire(request), 'Ordered wire request changed')
    if (directory / 'result.json').exists():
        return read(directory / 'result.json')
    once(directory / 'started.json', {'at': now(), 'pid': os.getpid(), 'wireRequestSha256': hashlib.sha256(body).hexdigest()})
    start = time.time()
    connection = http.client.HTTPConnection('127.0.0.1', 1234, timeout=2700)
    result = {'status': 'transport_failed', 'output': None}
    try:
        # Transmit the exact saved bytes, without JSON reserialization.
        connection.request('POST', '/v1/chat/completions', body=body, headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read()
        (directory / 'response.raw').write_bytes(raw)
        result.update({'httpStatus': response.status, 'rawResponseSha256': hashlib.sha256(raw).hexdigest()})
        data = json.loads(raw)
        once(directory / 'response.json', data)
        choice = (data.get('choices') or [{}])[0]
        message = choice.get('message', {})
        try:
            output = json.loads(message.get('content', ''))
        except (ValueError, TypeError):
            output = None
        result.update({'status': 'completed' if response.status == 200 and choice.get('finish_reason') == 'stop' and q.valid_judgment(output) else 'failed',
                       'output': output, 'finishReason': choice.get('finish_reason'), 'usage': data.get('usage'),
                       'returnedModel': data.get('model'), 'reasoningCharacters': len(message.get('reasoning_content', '') or ''),
                       'outputFieldOrder': list(output) if isinstance(output, dict) else None})
    except Exception as exc:
        result['exceptionType'] = type(exc).__name__
    finally:
        connection.close()
    result.update({'seconds': time.time() - start, 'wireRequestSha256': hashlib.sha256(body).hexdigest(),
                   'caseId': item['caseId'], 'marketId': item['marketId'], 'kind': item['kind'], 'trial': 1,
                   'variant': variant, 'directory': str(directory)})
    once(directory / 'result.json', result)
    print(json.dumps({'variant': variant, 'status': result['status'], 'seconds': result['seconds']}), flush=True)
    return result


def run():
    execution_gate()
    q = study_module()
    validate_preflight(q)
    panel = read(ROOT / 'panel.private.json')
    # Refuse uncertain attempts before sending any new call on a resumed run.
    for marker in (ROOT / 'calls').rglob('started.json'):
        require((marker.parent / 'result.json').exists(), 'Uncertain attempt; reconcile before resuming: ' + str(marker.parent))
    def pair(entry):
        return [call(entry, variant, q) for variant in entry['executionOrder']]
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(pair, panel['cases']):
            records.extend(rows)
    once(ROOT / 'judgments.private.json', records)
    score()


def known(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def validate_response_metadata(record, raw, identifier):
    message = raw['choices'][0]['message']
    require(record['returnedModel'] == raw.get('model') == identifier, 'Returned model differs from pinned instance')
    require(record['reasoningCharacters'] == len(message.get('reasoning_content', '') or ''), 'Reasoning character count differs from raw response')


def requested_order_matches(record):
    return record.get('outputFieldOrder') == (ORIGINAL_ORDER if record['variant'] == 'original' else QUOTE_ORDER)


def replay_agreement(record, old, q):
    both = record['status'] == old['status'] == 'completed'
    return {'caseId': record['caseId'], 'sameStatus': record['status'] == old['status'], 'bothCompleted': both,
            'sameCanonicalJson': record['output'] == old['output'] if both else None,
            'sameFactualOutcome': record['output']['factualOutcome'] == old['output']['factualOutcome'] if both else None,
            'sameSettlement': q.settlement(record['output']) == q.settlement(old['output']) if both else None}


def summary(rows):
    scores = [row['score'] for row in rows]
    pos = [row for row in scores if row['kind'] == 'control' and row['expected'] in ['A', 'B']]
    neg = [row for row in scores if row['kind'] == 'control' and row['expected'] not in ['A', 'B']]
    facts = [row for row in scores if row['kind'] == 'factual']
    result = {'rows': len(rows), 'completed': sum(x['valid'] for x in scores), 'positiveControls': len(pos),
              'strictPositivePasses': sum(x['strictPass'] is True for x in pos), 'negativeControls': len(neg),
              'falseClaims': sum(x['falsePositive'] is True for x in neg), 'wrongPositiveSide': sum(x['wrongOutcome'] is True for x in pos),
              'factualPairs': len(facts), 'groundedFactualPasses': sum(x['groundedFactualPass'] is True for x in facts),
              'factualPasses': sum(x['factualPass'] is True for x in facts), 'strictConflicts': sum(x['conflict'] for x in scores),
              'strictClaimsWithoutExactQuote': sum(x['settlementOutcome'] in ['A', 'B'] and not x['exactQuote'] for x in scores),
              'completedOutputOrderMatchesRequested': sum(x['record']['status'] == 'completed' and requested_order_matches(x['record']) for x in rows),
              'completedOutputOrderDiffersFromRequested': sum(x['record']['status'] == 'completed' and not requested_order_matches(x['record']) for x in rows),
              'outputFieldOrders': [{'keys': list(order), 'count': count} for order, count in collections.Counter(tuple(x['record'].get('outputFieldOrder') or []) for x in rows).items()]}
    measures = {'inputTokens': [(x['record'].get('usage') or {}).get('prompt_tokens') for x in rows],
                'outputTokens': [(x['record'].get('usage') or {}).get('completion_tokens') for x in rows],
                'summedRequestSeconds': [x['record'].get('seconds') for x in rows]}
    result['usage'] = {key: {'knownTotal': sum(x for x in values if known(x)), 'missing': sum(not known(x) for x in values),
                            'knownTotalIsLowerBound': any(not known(x) for x in values)} for key, values in measures.items()}
    durations = [x for x in measures['summedRequestSeconds'] if known(x)]
    result['medianRequestSeconds'] = statistics.median(durations) if durations else None
    return result


def score():
    execution_gate()
    q = study_module()
    counts = validate_preflight(q)
    panel = {row['item']['caseId']: row for row in read(ROOT / 'panel.private.json')['cases']}
    records = read(ROOT / 'judgments.private.json')
    keys = {(cid, variant) for cid in panel for variant in VARIANTS}
    require(len(records) == 24 and {(x['caseId'], x['variant']) for x in records} == keys, 'Probe output coverage differs')
    rows = []
    replay = []
    for record in records:
        entry = panel[record['caseId']]
        item = entry['item']
        directory = Path(record['directory'])
        require(record == read(directory / 'result.json'), 'Aggregate result changed')
        request = reorder(entry['baselineRequest'], record['variant'])
        body = (directory / 'request-wire.json').read_bytes()
        require(body == wire(request) == wire(read(directory / 'request.json')), 'Ordered request reconstruction differs')
        require(hashlib.sha256(body).hexdigest() == record['wireRequestSha256'], 'Wire hash differs')
        if record.get('rawResponseSha256'):
            require(digest(directory / 'response.raw') == record['rawResponseSha256'], 'Raw response changed')
        if record['status'] == 'completed':
            raw = read(directory / 'response.raw')
            require(raw == read(directory / 'response.json'), 'Parsed response differs')
            choice = raw['choices'][0]
            output = json.loads(choice['message']['content'])
            require(output == record['output'] and q.valid_judgment(output) and choice['finish_reason'] == 'stop' and record['httpStatus'] == 200, 'Completed response differs')
            require(record['usage'] == raw.get('usage') and record['outputFieldOrder'] == list(output), 'Response metadata differs')
            validate_response_metadata(record, raw, read(ROOT / 'runtime.json')['identifier'])
        tokens = (record.get('usage') or {}).get('prompt_tokens')
        if tokens is not None:
            require(tokens == counts[record['caseId'] + '/' + record['variant']]['inputTokens'], 'Full input token accounting differs')
        scored = q.score_record(item, record)
        rows.append({'selectionBucket': entry['selectionBucket'], 'record': record, 'score': scored})
        if record['variant'] == 'original':
            old = entry['baselineRecord']
            replay.append(replay_agreement(record, old, q))
    result = {'at': now(), 'protocolSha256': digest(ROOT / 'protocol.json'), 'inputFreezeSha256': digest(ROOT / 'input-freeze.json'),
              'variantSummaries': {variant: summary([row for row in rows if row['record']['variant'] == variant]) for variant in VARIANTS},
              'originalReplayVsEarlierBaseline': replay, 'rows': rows,
              'qualification': 'Twelve selected old-development cases, including known baseline failures, are a diagnostic panel and not an independent accuracy estimate. Two variants share the same full input and frozen baseline rules; only properties/required field order changes. Execution order is balanced but concurrent cache effects make latency observational. No automatic method selection or benchmark replacement.'}
    once(ROOT / 'summary.private.json', result)
    print(json.dumps({'summary': str(ROOT / 'summary.private.json'), 'variantSummaries': result['variantSummaries']}), flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['preflight', 'run', 'score'])
    phase = parser.parse_args().phase
    {'preflight': preflight, 'run': run, 'score': score}[phase]()
