"""CLI for the sealed supplemental natural-email comparison.

Preparation reads only existing development rules. Future sources cannot open
until final selection and both independent freezes exist and verify.
"""
import argparse
import concurrent.futures
import importlib
import os
import platform
import subprocess
import sys
from pathlib import Path
import evaluation_core as c


def environment():
    import regex
    return {'python': sys.version, 'pythonExecutable': sys.executable, 'platform': platform.platform(), 'regexVersion': regex.__version__}


def sealed_module(name):
    source = c.QWEN / 'sealed-source'
    sys.path.insert(0, str(source))
    module = importlib.import_module(name)
    for path in source.glob('*.py'):
        if path.stem in sys.modules:
            loaded = getattr(sys.modules[path.stem], '__file__', None)
            c.require(loaded is not None and Path(loaded).resolve() == path.resolve(), 'Loaded study module is not its sealed copy: ' + path.stem)
    c.require(Path(module.__file__).resolve() == (source / (name + '.py')).resolve(), 'Requested module is outside sealed source')
    return module


def qwen_module():
    return sealed_module('qwen_round1')


def validate_preflight(preflight, runtime, requests, q):
    q.verify_preflight_runtime(preflight, runtime)
    c.require(preflight['identifier'] == runtime['identifier'], 'Preflight instance differs')
    counts = {x['caseId']: x for x in preflight['counts']}
    c.require(len(counts) == len(preflight['counts']) and set(counts) == set(requests), 'Preflight coverage differs')
    for case, count in counts.items():
        c.require(type(count['inputTokens']) is int and count['inputTokens'] >= 0, 'Invalid preflight input count')
        c.require(type(count['fits']) is bool, 'Invalid preflight fits flag')
        c.require(count['outputAllowance'] == requests[case]['max_tokens'], 'Preflight output allowance differs')
        c.require(count['fits'] == (count['inputTokens'] + count['outputAllowance'] <= preflight['contextLength']), 'Preflight capacity flag differs')
    c.require(preflight['allFullInputsFit'] is all(x['fits'] for x in counts.values()), 'Preflight aggregate capacity differs')
    return counts


def freeze():
    c.require(not (c.ROOT / 'opened.json').exists(), 'Reserved sources already opened')
    c.require(not (c.ROOT / 'adapter-freeze.json').exists(), 'Adapter already frozen')
    methods = c.method_gates()
    c.require(c.digest(c.QWEN / 'public-inputs.json') == c.PUBLIC_SHA, 'Public question list changed')
    questions = c.read(c.QWEN / 'public-inputs.json')
    mids = {x['marketId'] for x in questions}
    c.require(len(questions) == len(mids) == 241, 'Public coverage differs')
    c.require(all(set(x) == {'marketId', 'question', 'rules', 'outcomeLabels'} and len(x['outcomeLabels']) == 2 for x in questions), 'Nonbinary or malformed public input')
    sources = [c.REGEX / f'methods/baseline/{name}-generations.json' for name in ['development', 'expansion', 'followup']]
    regex_rules = [row for path in sources for row in c.read(path)]
    c.require(len(regex_rules) == 241 and {x['marketId'] for x in regex_rules} == mids, 'Regex rule coverage differs')
    rules = {'regex-baseline': {x['marketId']: {'status': x['status'], 'output': x['output']} for x in regex_rules}}
    for method in methods['qwenMethods']:
        path = c.QWEN / f'methods/{method}/rules.json'
        records = c.read(path)
        c.require(len(records) == 241 and {x['marketId'] for x in records} == mids and all(x['trial'] == 1 for x in records), 'Qwen rule coverage differs')
        sources.append(path)
        rules['qwen-' + method] = {x['marketId']: {'status': x['status'], 'output': x['output']} for x in records}
    links = {'createdAt': c.now(), 'sourceHashes': {str(path): c.digest(path) for path in sources}, 'rules': rules}
    links_path = c.ROOT / 'rule-links.private.json'
    if links_path.exists():
        old = c.read(links_path)
        c.require(old['sourceHashes'] == links['sourceHashes'] and old['rules'] == rules, 'Preexisting rule links differ')
    else:
        c.once(links_path, links)
    sdk = Path('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs')
    files = [p for p in c.ROOT.iterdir() if p.is_file() and p.suffix in {'.py', '.mjs', '.json'}]
    files += list((c.ROOT / 'regex-source').glob('*.py'))
    c.once(c.ROOT / 'adapter-freeze.json', {'frozenAt': c.now(), 'methods': methods, 'environment': environment(),
        'externalFileHashes': {str(sdk): c.digest(sdk)},
        'fileHashes': {str(path.relative_to(c.ROOT)): c.digest(path) for path in files},
        'reservedSourcesOrLabelsRead': False, 'reservationSealSha256': c.SEAL_SHA,
        'inferenceProcedure': 'sealed combined factual and two-settlement-predicate JSON', 'workers': 4})
    print(c.parse_json(c.canonical({'frozen': True, 'methods': list(rules), 'futureSourcesRead': False})))


def gates(phase):
    frozen = c.adapter_gates()
    c.require(frozen['environment'] == environment(), 'Evaluation runtime changed')
    for path, expected in frozen['externalFileHashes'].items():
        c.require(c.digest(path) == expected, 'Pinned SDK bytes changed')
    for path, expected in c.read(c.ROOT / 'rule-links.private.json')['sourceHashes'].items():
        c.require(c.digest(path) == expected, 'Original candidate rule file changed')
    seal = c.reservation_gates()
    marker = c.ROOT / 'opened.json'
    if not marker.exists():
        c.once(marker, {'openedAt': c.now(), 'phase': phase, 'adapterFreezeSha256': c.digest(c.ROOT / 'adapter-freeze.json'), 'reservationSealSha256': c.SEAL_SHA})
    else:
        c.require(c.read(marker)['adapterFreezeSha256'] == c.digest(c.ROOT / 'adapter-freeze.json'), 'Opening marker changed')
    return frozen, seal


def load_sources():
    path = c.RESERVATION / 'sealed/sources/source-manifest.private.json'
    c.require(c.digest(path) == c.SOURCE_MANIFEST_SHA, 'Source manifest differs')
    sources = c.read(path)
    c.require(len(sources) == len({x['rawSha256'] for x in sources}) == len({x['emailKey'] for x in sources}) == 2, 'Source coverage differs')
    for source in sources:
        for path_key, hash_key in [('rawPath', 'rawSha256'), ('decodedTextPath', 'decodedTextSha256')]:
            c.require(c.digest(c.contained(c.RESERVATION, source[path_key])) == source[hash_key], 'Source representation changed')
        if source['mainHtmlPresent']:
            c.require(c.digest(c.contained(c.RESERVATION, source['mainHtmlPath'])) == source['mainHtmlSha256'], 'Full HTML changed')
        for part in source['mimeBodyParts']:
            c.require(c.digest(c.contained(c.RESERVATION, part['path'])) == part['sha256'], 'MIME part changed')
    return sources


def prepare():
    frozen, _ = gates('prepare full sources; annotations still unopened')
    q = qwen_module()
    public_path = c.RESERVATION / 'sealed/sources/public-inputs.json'
    c.require(c.digest(public_path) == c.PUBLIC_SHA, 'Reserved question list differs')
    questions = c.read(public_path)
    sources = load_sources()
    packets, items = {}, []
    for source in sources:
        raw = c.contained(c.RESERVATION, source['rawPath']).read_bytes()
        metadata, audit = c.source_metadata(source, raw)
        html = c.contained(c.RESERVATION, source['mainHtmlPath']).read_bytes().decode('utf-8') if source['mainHtmlPresent'] else None
        semantic, render_audit = q.semantic.render(html) if html is not None else (None, None)
        packets[source['rawSha256']] = {'html': html, 'qwenEmail': q.email_packet({**metadata, 'semanticText': semantic}) if semantic is not None else None,
            'metadataAudit': audit, 'rendererAudit': render_audit, 'source': source}
        for question in questions:
            items.append({'pairId': c.pair_id(source['rawSha256'], question['marketId']), 'marketId': question['marketId'], 'emailSha256': source['rawSha256']})
    c.require(len(items) == len({x['pairId'] for x in items}) == 482, 'Pair coverage differs')
    c.once(c.ROOT / 'email-packets.private.json', packets)
    c.once(c.ROOT / 'items.private.json', items)
    links = c.read(c.ROOT / 'rule-links.private.json')['rules']
    runtime = c.read(c.QWEN / 'runtime.json')
    for method in frozen['methods']['qwenMethods']:
        prompt = (c.QWEN / (method + '-judge.txt')).read_bytes().decode('utf-8')
        requests = []
        for item in items:
            rule = links['qwen-' + method][item['marketId']]
            email_packet = packets[item['emailSha256']]['qwenEmail']
            if rule['status'] == 'completed' and email_packet is not None:
                request = q.judge_request(rule['output'], q.restore_email(email_packet), prompt, runtime)
                requests.append({'caseId': item['pairId'], 'request': request})
        c.once(c.ROOT / f'methods/qwen-{method}/requests.private.json', {'identifier': runtime['identifier'], 'requests': requests})
    paths = [c.ROOT / name for name in ['email-packets.private.json', 'items.private.json']]
    paths += list((c.ROOT / 'methods').glob('*/requests.private.json'))
    c.once(c.ROOT / 'input-freeze.json', {'frozenAt': c.now(), 'adapterFreezeSha256': c.digest(c.ROOT / 'adapter-freeze.json'),
        'fileHashes': {str(p.relative_to(c.ROOT)): c.digest(p) for p in paths}, 'pairs': len(items), 'annotationsRead': False})
    print({'preparedPairsPerMethod': len(items), 'sourceDocuments': len(packets), 'annotationsRead': False})


def inputs(phase):
    gates(phase)
    frozen = c.read(c.ROOT / 'input-freeze.json')
    c.require(frozen['adapterFreezeSha256'] == c.digest(c.ROOT / 'adapter-freeze.json'), 'Input freeze differs')
    c.verify_hashes(c.ROOT, frozen['fileHashes'])
    return c.read(c.ROOT / 'items.private.json'), c.read(c.ROOT / 'email-packets.private.json')


def regex_evaluate():
    items, packets = inputs('regex inference; annotations unopened')
    sys.path.insert(0, str(c.ROOT / 'regex-source'))
    matcher = importlib.import_module('round2_matcher')
    rules = c.read(c.ROOT / 'rule-links.private.json')['rules']['regex-baseline']
    rows = []
    for item in items:
        rule, html = rules[item['marketId']], packets[item['emailSha256']]['html']
        row = {**item, 'valid': False, 'status': 'rule_unavailable', 'factualOutcome': 'UNSCORABLE', 'settlementOutcome': 'UNSCORABLE', 'exactQuote': False}
        if rule['status'] == 'completed' and html is not None:
            compiled = [matcher.compile_pattern(rule['output'].get(k)) for k in ['outcomeARegex', 'outcomeBRegex']]
            hits = [matcher.search(pattern, html) for pattern, error in compiled]
            valid = all(error is None for _, error in compiled) and not any(timeout for _, timeout in hits)
            mask = [match is not None for match, _ in hits]
            value = c.decision(mask) if valid else 'UNSCORABLE'
            row.update(valid=valid, status='completed' if valid else 'invalid_or_timeout', factualOutcome=value, settlementOutcome=value,
                matches=[match for match, _ in hits], errors=[error for _, error in compiled], timeouts=[timeout for _, timeout in hits],
                sourceHtmlSha256=c.sha(html.encode('utf-8')))
        elif html is None:
            row['status'] = 'main_html_unavailable'
        rows.append(row)
    c.once(c.ROOT / 'methods/regex-baseline/predictions.private.json', rows)
    print({'method': 'regex-baseline', 'pairs': len(rows), 'completed': sum(x['valid'] for x in rows)})


def qwen_evaluate(method):
    items, packets = inputs('Qwen inference; annotations unopened')
    frozen = c.read(c.ROOT / 'adapter-freeze.json')
    c.require(method in frozen['methods']['qwenMethods'], 'Unselected supplemental method')
    q = qwen_module()
    directory = c.ROOT / f'methods/qwen-{method}'
    request_path = directory / 'requests.private.json'
    preflight_path = directory / 'preflight.private.json'
    if not preflight_path.exists():
        subprocess.run(['node', str(c.ROOT / 'preflight.mjs'), str(request_path), str(preflight_path)], check=True)
    preflight = c.read(preflight_path)
    c.require(preflight['inputSha256'] == c.digest(request_path), 'Preflight requests changed')
    runtime = c.read(c.QWEN / 'runtime.json')
    requests = {x['caseId']: x['request'] for x in c.read(request_path)['requests']}
    counts = validate_preflight(preflight, runtime, requests, q)
    ordered = sorted(items, key=lambda x: (c.sha(c.canonical(packets[x['emailSha256']]['qwenEmail'])), x['marketId'], x['pairId']))
    dispatch_path = directory / 'dispatch.private.json'
    dispatch = {'workers': 4, 'pairOrder': [x['pairId'] for x in ordered], 'requestFileSha256': c.digest(request_path)}
    if dispatch_path.exists():
        c.require(c.read(dispatch_path) == dispatch, 'Inference dispatch changed')
    else:
        c.once(dispatch_path, dispatch)

    def one(item):
        case = item['pairId']
        if case not in requests:
            result = {'status': 'rule_or_html_unavailable', 'output': None}
        elif not counts[case]['fits']:
            result = {'status': 'full_input_overflow', 'output': None}
        else:
            result = q.local_call(requests[case], directory / 'calls' / case)
        output = result.get('output')
        valid = result['status'] == 'completed' and q.valid_judgment(output)
        body = (packets[item['emailSha256']]['qwenEmail'] or {}).get('completeSemanticText', '')
        if valid:
            actual = (result.get('usage') or {}).get('prompt_tokens')
            c.require(actual == counts[case]['inputTokens'], 'Server input tokens differ from full-input preflight')
        return {**item, **result, 'directory': str(directory / 'calls' / case), 'valid': valid,
            'factualOutcome': output['factualOutcome'] if valid else 'UNSCORABLE',
            'settlementOutcome': q.settlement(output) if valid else 'UNSCORABLE',
            'exactQuote': bool(valid and output['evidenceQuote'] and output['evidenceQuote'] in body)}

    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for future in concurrent.futures.as_completed([pool.submit(one, item) for item in ordered]):
            result = future.result()
            records.append(result)
            print({'method': 'qwen-' + method, 'finished': len(records), 'total': len(items), 'status': result['status']}, flush=True)
    c.once(directory / 'predictions.private.json', records)


def score():
    items, packets = inputs('scorer opening after all predictions complete')
    rules = c.read(c.ROOT / 'rule-links.private.json')['rules']
    predictions = {}
    expected_pairs = {x['pairId'] for x in items}
    for method in rules:
        rows = c.read(c.ROOT / f'methods/{method}/predictions.private.json')
        c.require(len(rows) == 482 and {x['pairId'] for x in rows} == expected_pairs, 'Incomplete or duplicate prediction rows')
        predictions[method] = {x['pairId']: x for x in rows}
        item_index = {x['pairId']: x for x in items}
        for row in rows:
            item = item_index[row['pairId']]
            c.require(all(row[k] == item[k] for k in item), 'Prediction identity differs')
        if method.startswith('qwen-'):
            audit_qwen_predictions(method.removeprefix('qwen-'), rows, items, packets, rules[method])
        else:
            for row in rows:
                html = packets[row['emailSha256']]['html']
                if row.get('matches'):
                    c.require(c.sha(html.encode('utf-8')) == row['sourceHtmlSha256'], 'Regex source changed')
                    for match in row['matches']:
                        if match is not None:
                            chunk = html.encode('utf-8')[match['start']:match['end']]
                            c.require(chunk.decode('utf-8', 'replace') == match['text'] and len(chunk) == match['bytes'], 'Regex source witness changed')
                expected = c.decision([m is not None for m in row['matches']]) if row['valid'] else 'UNSCORABLE'
                c.require(row['factualOutcome'] == row['settlementOutcome'] == expected, 'Regex match decision differs')
    # Label content is not read until every method has all predictions recorded.
    labels_path = c.RESERVATION / 'sealed/annotations.private.jsonl'
    c.require(c.digest(labels_path) == c.ANNOTATIONS_SHA, 'Annotations changed')
    annotations = [c.parse_json(line) for line in labels_path.read_bytes().splitlines() if line.strip()]
    questions = c.read(c.RESERVATION / 'sealed/sources/public-inputs.json')
    c.verify_annotations(annotations, questions, load_sources(), c.read(c.RESERVATION / 'safe/annotation.schema.json'))
    indexed = {x['pairId']: x for x in annotations}
    common = {pair for pair in expected_pairs if all(rows[pair]['valid'] for rows in predictions.values())}
    subsets = {'allPairs': expected_pairs, 'commonCompletedAllMethods': common}
    subsets.update({'email-' + raw_sha: {x['pairId'] for x in items if x['emailSha256'] == raw_sha} for raw_sha in packets})
    summaries = {}
    for method, rows in predictions.items():
        summaries[method] = {}
        for name, ids in subsets.items():
            labels = {key: indexed[key] for key in ids}
            summaries[method][name] = {'pairs': len(ids), 'valid': sum(rows[key]['valid'] for key in ids),
                'coreFact': c.score_layer(rows, labels, 'coreFact', 'factualOutcome'),
                'originalRuleSettlement': c.score_layer(rows, labels, 'originalRuleSettlement', 'settlementOutcome'),
                'interpretation': 'Lexical candidates; original-rule admissibility is not enforced by this method' if method.startswith('regex-') else 'Separate factual and full settlement-predicate judgments'}
        summaries[method]['execution'] = c.execution_summary(list(rows.values()), model_requests=method.startswith('qwen-'))
    paths = list((c.ROOT / 'methods').rglob('*'))
    hashes = {str(p.relative_to(c.ROOT)): c.digest(p) for p in paths if p.is_file()}
    c.once(c.ROOT / 'evaluation.private.json', {'scoredAt': c.now(), 'sourceDocuments': len(packets), 'pairsPerMethod': 482,
        'methods': list(predictions), 'commonCompletedPairs': len(common), 'summaries': summaries,
        'annotationAuthority': c.AUTHORITY, 'annotationSha256': c.ANNOTATIONS_SHA,
        'predictionArtifactHashes': hashes, 'adapterFreezeSha256': c.digest(c.ROOT / 'adapter-freeze.json'),
        'limits': c.read(c.ROOT / 'protocol.json')['limits'], 'livePromotion': False})
    print({'scoredMethods': list(predictions), 'pairsPerMethod': 482, 'commonCompleted': len(common), 'sourceDocuments': len(packets)})


def audit_qwen_predictions(method, rows, items, packets, rules):
    """Offline reconciliation before opening labels; never makes a model call."""
    q = qwen_module()
    audit = sealed_module('qwen_final_audit')
    directory = c.ROOT / f'methods/qwen-{method}'
    requests_path = directory / 'requests.private.json'
    recorded_requests = {x['caseId']: x['request'] for x in c.read(requests_path)['requests']}
    runtime = c.read(c.QWEN / 'runtime.json')
    prompt = (c.QWEN / (method + '-judge.txt')).read_bytes().decode('utf-8')
    expected_requests = {}
    for item in items:
        rule = rules[item['marketId']]
        packet = packets[item['emailSha256']]['qwenEmail']
        if rule['status'] == 'completed' and packet is not None:
            expected_requests[item['pairId']] = q.judge_request(rule['output'], q.restore_email(packet), prompt, runtime)
    c.require(expected_requests == recorded_requests, 'Recorded requests differ from complete blind inputs')
    preflight = c.read(directory / 'preflight.private.json')
    c.require(preflight['inputSha256'] == c.digest(requests_path), 'Token preflight input changed')
    counts = validate_preflight(preflight, runtime, expected_requests, q)
    for row in rows:
        case = row['pairId']
        expected_directory = directory / 'calls' / case
        c.require(row['directory'] == str(expected_directory), 'Local result directory differs')
        if case not in expected_requests:
            c.require(row['status'] == 'rule_or_html_unavailable' and row['output'] is None and not row['valid'], 'Unavailable input received prediction')
        elif not counts[case]['fits']:
            c.require(row['status'] == 'full_input_overflow' and row['output'] is None and not row['valid'], 'Overflow input received prediction')
            c.require(not (expected_directory / 'started.json').exists(), 'Overflow input was sent to inference')
        else:
            audit.verify_local(row, expected_requests[case])
        output = row['output']
        valid = row['status'] == 'completed' and q.valid_judgment(output)
        fact = output['factualOutcome'] if valid else 'UNSCORABLE'
        strict = q.settlement(output) if valid else 'UNSCORABLE'
        body = (packets[row['emailSha256']]['qwenEmail'] or {}).get('completeSemanticText', '')
        quoted = bool(valid and output['evidenceQuote'] and output['evidenceQuote'] in body)
        c.require((row['valid'], row['factualOutcome'], row['settlementOutcome'], row['exactQuote']) == (valid, fact, strict, quoted), 'Prediction normalization differs from raw completion')
        if valid:
            c.require((row.get('usage') or {}).get('prompt_tokens') == counts[case]['inputTokens'], 'Completed call differs from full-input token count')


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['freeze', 'prepare', 'regex', 'qwen', 'score'])
    parser.add_argument('--method')
    args = parser.parse_args()
    if args.mode == 'freeze': freeze()
    elif args.mode == 'prepare': prepare()
    elif args.mode == 'regex': regex_evaluate()
    elif args.mode == 'qwen': qwen_evaluate(args.method)
    elif args.mode == 'score': score()
