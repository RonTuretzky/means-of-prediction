"""Offline final reconciliation; fresh fixture reads require the completed freeze.

This helper never makes a model request. Run the sealed copy after fresh scoring.
"""
import argparse
import collections
import json
import math
from datetime import datetime
from pathlib import Path
import qwen_round1 as q


def verify_local(record, expected):
    directory = Path(record['directory'])
    result = q.r.read(directory / 'result.json')
    if q.r.read(directory / 'request.json') != expected:
        raise RuntimeError('Local request differs from label-blind procedure')
    if result['requestSha256'] != q.r.hash_value(expected):
        raise RuntimeError('Local request hash differs')
    if any(record.get(k) != value for k, value in result.items()):
        raise RuntimeError('Aggregate local record differs from original result')
    for field, name in [('responseSha256', 'response.json'), ('rawResponseSha256', 'response.raw')]:
        if result.get(field) and q.r.digest(directory / name) != result[field]:
            raise RuntimeError('Local response changed')
    if result['status'] == 'completed':
        raw = json.loads((directory / 'response.raw').read_bytes())
        if raw != q.r.read(directory / 'response.json'):
            raise RuntimeError('Raw and parsed HTTP response differ')
        choice = raw['choices'][0]
        if result['httpStatus'] != 200 or choice['finish_reason'] != 'stop':
            raise RuntimeError('Failed HTTP/generation marked completed')
        output = json.loads(choice['message']['content'])
        if not q.valid_judgment(output) or output != result['output']:
            raise RuntimeError('Judgment differs from original completion')
        if result.get('usage') != raw.get('usage'):
            raise RuntimeError('Local usage differs from original completion')
        if result.get('returnedModel') != raw.get('model') or raw.get('model') != expected['model']:
            raise RuntimeError('Returned model differs from requested pinned instance')
        if result.get('reasoningCharacters') != len(choice['message'].get('reasoning_content', '') or ''):
            raise RuntimeError('Reasoning character count differs from original completion')


def counts(rows):
    positives = [x for x in rows if x['expected'] in ['A', 'B']]
    negatives = [x for x in rows if x['kind'] == 'control' and x['expected'] not in ['A', 'B']]
    return {
        'rows': len(rows), 'completed': sum(x['valid'] for x in rows),
        'positiveRows': len(positives), 'negativeRows': len(negatives),
        'factualPasses': sum(x['factualPass'] is True for x in positives),
        'groundedFactualPasses': sum(x['groundedFactualPass'] is True for x in positives),
        'strictPositivePasses': sum(x['strictPass'] is True for x in positives),
        'negativeFalseClaims': sum(x['falsePositive'] is True for x in negatives),
        'scoredNegatives': sum(x['valid'] for x in negatives),
        'negativeRejections': sum(x['strictPass'] is True for x in negatives),
        'wrongOutcomes': sum(x['wrongOutcome'] is True for x in rows),
        'wrongFactualOutcomes': sum(x['wrongFactualOutcome'] is True for x in rows),
        'conflicts': sum(x['conflict'] for x in rows),
        'unscorable': sum(not x['valid'] for x in rows),
        'strictClaimsWithoutExactQuote': sum(x['settlementOutcome'] in ['A', 'B'] and not x['exactQuote'] for x in rows),
    }


def verify_phase(method, phase):
    fresh = phase == 'challenge'
    items = {x['caseId']: x for x in q.load('challenge-items.private.json' if fresh else q.ITEMS)}
    rules = {(x['marketId'], x['trial']): x for x in q.load(f'methods/{method}/' + ('challenge-rules.json' if fresh else 'rules.json'))}
    records = q.load(f'methods/{method}/{phase}-judgments.private.json')
    scores = q.load(f'methods/{method}/{phase}-scores.private.json')
    expected_keys = {(cid, t) for cid in items for t in ([1, 2] if fresh else [1])}
    if len(records) != len(expected_keys) or {(x['caseId'], x['trial']) for x in records} != expected_keys:
        raise RuntimeError('Final judgment cohort differs')
    if len(scores) != len(expected_keys) or {(x['caseId'], x['trial']) for x in scores} != expected_keys:
        raise RuntimeError('Final score cohort differs')
    prompt = (q.ROOT / (method + '-judge.txt')).read_text()
    runtime = q.load('runtime.json')
    stem = 'challenge-semantic-preflight' if fresh else 'semantic-preflight'
    preflight = q.load(f'methods/{method}/{stem}.json')
    preflight_path = q.ROOT / f'methods/{method}/{stem}-requests.private.json'
    if preflight['inputSha256'] != q.r.digest(preflight_path) or not preflight['allFullInputsFit']:
        raise RuntimeError('Final token preflight seal differs')
    q.verify_preflight_runtime(preflight, runtime)
    preflight_requests = {x['caseId']: x['request'] for x in q.r.read(preflight_path)['requests']}
    preflight_tokens = {x['caseId']: x['inputTokens'] for x in preflight['counts']}
    expected_preflight = {(cid + '/' + str(t) if fresh else cid) for cid, t in expected_keys if rules[(items[cid]['marketId'], t)]['status'] == 'completed'}
    if set(preflight_requests) != expected_preflight or set(preflight_tokens) != expected_preflight:
        raise RuntimeError('Final token preflight omitted a case or draw')
    recomputed = []
    for row in records:
        item = items[row['caseId']]
        if row['marketId'] != item['marketId'] or row['kind'] != item['kind']:
            raise RuntimeError('Judgment identity differs')
        rule = rules[(item['marketId'], row['trial'])]
        if rule['status'] == 'completed':
            request = q.judge_request(rule['output'], q.restore_email(item['email']), prompt, runtime)
            request_id = row['caseId'] + '/' + str(row['trial']) if fresh else row['caseId']
            if preflight_requests[request_id] != request:
                raise RuntimeError('Judgment request differs from token preflight')
            verify_local(row, request)
            actual_tokens = (row.get('usage') or {}).get('prompt_tokens')
            if actual_tokens is not None and actual_tokens != preflight_tokens[request_id]:
                raise RuntimeError('Server-accounted input differs from complete rendered input')
        elif row['status'] != 'rule_unavailable' or row['output'] is not None:
            raise RuntimeError('Unavailable rule received a judgment')
        recomputed.append(q.score_record(item, row))
    key = lambda x: (x['caseId'], x['trial'])
    if sorted(recomputed, key=key) != sorted(scores, key=key):
        raise RuntimeError('Cached score differs from independently recomputed score')
    summary = q.load(f'methods/{method}/{phase}-summary.json')
    if summary['statuses'] != dict(collections.Counter(x['status'] for x in records)):
        raise RuntimeError('Summary statuses differ')
    for kind, metrics in summary['metrics'].items():
        subset = [x for x in recomputed if x['kind'] == kind]
        c = counts(subset)
        mapping = {'total': 'rows', 'completed': 'completed', 'positiveTotal': 'positiveRows',
                   'negativeTotal': 'negativeRows', 'factualPasses': 'factualPasses', 'groundedFactualPasses': 'groundedFactualPasses',
                   'strictPositivePasses': 'strictPositivePasses', 'falsePositives': 'negativeFalseClaims',
                   'safeNegativeRejections': 'negativeRejections', 'wrongOutcomes': 'wrongOutcomes',
                   'wrongFactualOutcomes': 'wrongFactualOutcomes', 'conflicts': 'conflicts', 'unscorable': 'unscorable'}
        if any(metrics[k] != c[v] for k, v in mapping.items()):
            raise RuntimeError('Summary metrics differ')
    families = collections.defaultdict(list)
    for row in recomputed:
        if row['kind'] == 'factual': families[row['metadata']['factKey']].append(row)
    macro = sum(sum(x['groundedFactualPass'] for x in xs) / len(xs) for xs in families.values()) / len(families) if families else None
    if macro != summary['factFamilyMacroRecall']:
        raise RuntimeError('Family macro recall differs')
    control = counts([x for x in recomputed if x['kind'] == 'control'])
    utility = (macro or 0) + control['strictPositivePasses'] / max(1, control['positiveRows']) - 3 * control['negativeFalseClaims'] / max(1, control['negativeRows']) - sum(not x['valid'] for x in recomputed) / max(1, len(recomputed))
    if utility != summary['utility']:
        raise RuntimeError('Selection utility differs from raw scores')
    return {
        'counts': counts(recomputed),
        'inputTokenChecks': {
            'preflightedRequests': len(preflight_tokens),
            'serverUsageMatchedFullInput': sum((x.get('usage') or {}).get('prompt_tokens') is not None for x in records),
            'attemptedWithoutServerInputUsage': sum(x['status'] != 'rule_unavailable' and (x.get('usage') or {}).get('prompt_tokens') is None for x in records),
        },
        'byKind': {k: counts([x for x in recomputed if x['kind'] == k]) for k in sorted({x['kind'] for x in recomputed})},
        'byTrial': {str(t): counts([x for x in recomputed if x['trial'] == t]) for t in sorted({x['trial'] for x in recomputed})},
        'byMarket': {mid: counts([x for x in recomputed if x['marketId'] == mid]) for mid in sorted({x['marketId'] for x in recomputed})},
        'sourceHashes': {name: q.r.digest(q.ROOT / f'methods/{method}/{phase}-{name}') for name in ['judgments.private.json', 'scores.private.json', 'summary.json']},
    }


def verify_fresh_source():
    # Keep this guard before any evaluator-only path or fixture content read.
    selection = q.verify_selection()
    freeze = q.load('challenge-freeze.json')
    opened = q.load('fresh-opened.json')
    if freeze['selectionSha256'] != q.r.digest(q.ROOT / 'selection.json') or opened['challengeFreezeSha256'] != q.r.digest(q.ROOT / 'challenge-freeze.json'):
        raise RuntimeError('Fresh freeze lineage differs')
    if not (datetime.fromisoformat(selection['selectedAt']) <= datetime.fromisoformat(freeze['at']) <= datetime.fromisoformat(opened['openedAt'])):
        raise RuntimeError('Fresh fixture opening preceded a required freeze')
    for name, sha in freeze['fileHashes'].items():
        if q.r.digest(q.ROOT / name) != sha:
            raise RuntimeError('Frozen fresh Astra output changed')
    seal = q.load('independent-fixture-seal.json')
    if opened['fixtureSha256'] != seal['sha256'] or q.r.digest(seal['path']) != seal['sha256']:
        raise RuntimeError('Reserved fresh fixture changed')
    fixtures = q.r.read(seal['path'])
    public = {x['marketId']: x for x in q.load('independent-holdout-public.json')}
    if set(fixtures) != set(public) or len(public) != 12:
        raise RuntimeError('Fresh public/fixture coverage differs')
    items = []
    audits = {}
    for mid, cases in sorted(fixtures.items()):
        if len(cases) != 10 or collections.Counter(x['expected'] for x in cases) != {'A': 2, 'B': 2, 'neither': 6}:
            raise RuntimeError('Fresh fixture balance differs')
        for i, case in enumerate(cases):
            cid = q.r.hash_value(['fresh', mid, i])
            body, audits[cid] = q.semantic.render(case['html'])
            items.append({'caseId': cid, 'kind': 'control', 'marketId': mid, 'email': q.email_packet({'semanticText': body}),
                          'expected': case['expected'], 'metadata': {'name': case['name'], 'kind': case.get('kind'), 'index': i}})
    if items != q.load('challenge-items.private.json') or audits != q.load('challenge-render-audits.private.json'):
        raise RuntimeError('Fresh source rendering or scorer labels differ')
    for method in selection['freshMethods']:
        records = q.load(f'methods/{method}/challenge-rules.json')
        if len(records) != 24 or {(x['marketId'], x['trial']) for x in records} != {(mid, t) for mid in public for t in [1, 2]}:
            raise RuntimeError('Fresh Astra draws differ')
        for row in records:
            q.r.verify_model_artifact(row['directory'], q.rule_job(public[row['marketId']], (q.ROOT / (method + '.txt')).read_text(), None, row['trial']), row)
    return selection


def usage():
    groups = collections.defaultdict(collections.Counter)
    def known(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    def account(g, input_tokens=None, output_tokens=None, seconds=None):
        have_input, have_output, have_duration = map(known, [input_tokens, output_tokens, seconds])
        g['missingInputUsage'] += not have_input
        g['missingOutputUsage'] += not have_output
        g['missingDuration'] += not have_duration
        # Retain the aggregate key, now explicitly covering either token field.
        g['missingUsage'] += not (have_input and have_output)
        g['inputTokens'] += input_tokens if have_input else 0
        g['outputTokens'] += output_tokens if have_output else 0
        g['summedRequestSeconds'] += seconds if have_duration else 0
    def category(path, local=False):
        parts = path.relative_to(q.ROOT).parts
        if 'raw-html-interrupted-pilot' in parts: return 'local/raw-html-pilot'
        if parts[0] == 'runtime-probes': return 'local/runtime-probes/' + parts[1]
        if parts[0] == 'repeatability': return 'local/repeatability'
        if parts[0] == 'metadata-diagnostic': return 'local/metadata-diagnostic/' + (parts[2] if len(parts)>2 else 'preparation')
        if parts[0] == 'methods': return ('local/' if local else 'astra/') + '/'.join(parts[1:3])
        return 'astra/' + parts[0] + ('/recovery' if 'teacher-recovery' in parts else '')
    for path in q.ROOT.rglob('transport-result.json'):
        if 'sealed-source' in path.parts: continue
        transport = q.r.read(path)
        _, u, status = q.r.output_from(transport, path.parent)
        u = u or {}
        g = groups[category(path)]
        g['attempts'] += 1; g['completed'] += status == 'completed'
        account(g, u.get('input_tokens'), u.get('output_tokens'), transport.get('seconds'))
        cached = (u.get('input_tokens_details') or {}).get('cached_tokens')
        g['missingCachedInputUsage'] += not known(cached)
        g['cachedInputTokens'] += cached if known(cached) else 0
    for path in q.ROOT.rglob('started.json'):
        if 'sealed-source' in path.parts or not (path.parent / 'request.json').exists(): continue
        request = q.r.read(path.parent / 'request.json')
        if not isinstance(request, dict) or not ('messages' in request or ('input' in request and 'system_prompt' in request) or request.get('api') == 'SDK.complete'): continue
        g = groups[category(path, True)]; g['attempts'] += 1
        result_path = path.parent / 'result.json'
        if not result_path.exists():
            g['interruptedOrUncertain'] += 1; account(g); continue
        result = q.r.read(result_path)
        if request.get('api') == 'SDK.complete':
            stats = result.get('stats') or {}
            g['responsesReceived'] += result['status'] == 'response_received'
            g['completed'] += stats.get('stopReason') in ['eosFound', 'stopStringFound']
            g['failedOrIncomplete'] += stats.get('stopReason') not in ['eosFound', 'stopStringFound']
            g['outputTokensCapped'] += stats.get('stopReason') == 'maxPredictedTokensReached'
            account(g, stats.get('promptTokensCount'), stats.get('predictedTokensCount'), result.get('seconds'))
            continue
        u = result.get('usage') or {}
        g['completed'] += result['status'] == 'completed'; g['failed'] += result['status'] != 'completed'
        account(g, u.get('prompt_tokens'), u.get('completion_tokens'), result.get('seconds'))
    reports = {}
    for name, g in sorted(groups.items()):
        missing = {'inputTokens': 'missingInputUsage', 'outputTokens': 'missingOutputUsage', 'summedRequestSeconds': 'missingDuration'}
        if 'cachedInputTokens' in g: missing['cachedInputTokens'] = 'missingCachedInputUsage'
        reports[name] = {**dict(g), 'knownTotalsAreLowerBounds': {key: bool(g[field]) for key, field in missing.items()}}
    return {'at': q.r.now(), 'accountingVersion': 2, 'groups': reports,
            'qualification': 'Each new Qwen-experiment attempt is counted once. Reused prior regex lessons and model-download traffic are excluded. Input/output tokens and duration have independent missing counters. missingUsage means either token field is missing. Totals sum only known nonnegative finite values; zero with a missing counter is not a claim of zero consumption. Per-field flags identify incomplete lower bounds, including Astra cached-input usage. Concurrent request seconds are not wall time. Raw-HTML pilot, native/SDK capability probes and repeatability are separate from benchmark draws. SDK completed means natural generation termination, not necessarily schema-valid JSON; capped SDK outputs remain incomplete.'}


def main():
    selection = verify_fresh_source()
    result = {'auditedAt': q.r.now(), 'freshFixtureContentsReadOnlyAfterRecordedFreeze': True, 'methods': {}}
    for path in sorted((q.ROOT / 'methods').glob('*/development-summary.json')):
        method = path.parent.name
        result['methods'][method] = {'development': verify_phase(method, 'development')}
    for method in selection['freshMethods']:
        result['methods'][method]['challenge'] = verify_phase(method, 'challenge')
    q.once('final-raw-output-audit.private.json', result)
    q.once('final-usage-audit.json', usage())
    print(json.dumps({'auditedMethods': list(result['methods']), 'freshMethods': selection['freshMethods'], 'fixtureRows': 120, 'freshAstraAttempts': 48}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--usage-only', action='store_true'); args = parser.parse_args()
    if args.usage_only: print(json.dumps(usage()), flush=True)
    else: main()
