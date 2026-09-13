"""Freeze a diagnostic panel from completed old development only; no inference."""
import collections
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import probe as p

REPO_SOURCE = Path('/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/blind')


def prepare():
    os.umask(0o077)
    p.require(not (p.ROOT / 'input-freeze.json').exists(), 'Probe already prepared')
    sys.path.insert(0, str(REPO_SOURCE))
    q = importlib.import_module('qwen_round1')
    p.require(Path(q.__file__).resolve() == REPO_SOURCE / 'qwen_round1.py', 'Unexpected source import')
    source_dir = p.ROOT / 'source'
    source_dir.mkdir(mode=0o700)
    provenance = {}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            source = Path(name).resolve()
            if source.parent == REPO_SOURCE and source.suffix == '.py':
                target = source_dir / source.name
                shutil.copyfile(source, target)
                target.chmod(0o600)
                provenance[str(source)] = {'copy': str(target.relative_to(p.ROOT)), 'sha256': p.digest(target)}
    shutil.copyfile(REPO_SOURCE / 'qwen_preflight.mjs', source_dir / 'qwen_preflight.mjs')
    (source_dir / 'qwen_preflight.mjs').chmod(0o600)
    provenance[str(REPO_SOURCE / 'qwen_preflight.mjs')] = {'copy': 'source/qwen_preflight.mjs', 'sha256': p.digest(source_dir / 'qwen_preflight.mjs')}

    paths = {name: p.STUDY / path for name, path in {
        'items': q.ITEMS, 'scores': 'methods/baseline/development-scores.private.json',
        'records': 'methods/baseline/development-judgments.private.json', 'rules': 'methods/baseline/rules.json',
        'runtime': 'runtime.json', 'judgePrompt': 'baseline-judge.txt',
    }.items()}
    items = {row['caseId']: row for row in p.read(paths['items'])}
    scores = {row['caseId']: row for row in p.read(paths['scores'])}
    records = {row['caseId']: row for row in p.read(paths['records'])}
    rules = {row['marketId']: row for row in p.read(paths['rules'])}
    p.require(len(items) == len(scores) == len(records) == 1915 and set(items) == set(scores) == set(records), 'Old development coverage differs')
    selected = []
    used = set()

    def take(bucket, candidates, count, sort_key=lambda row: row['caseId']):
        eligible = sorted((row for row in candidates if row['caseId'] not in used and row['valid']), key=sort_key)
        p.require(len(eligible) >= count, 'Insufficient cases for ' + bucket)
        for row in eligible[:count]:
            selected.append((bucket, row['caseId']))
            used.add(row['caseId'])

    for side in ['A', 'B']:
        take('correct-positive-' + side, [x for x in scores.values() if x['kind'] == 'control' and x['expected'] == side and x['strictPass']], 2)
    for side in ['A', 'B']:
        take('wrong-positive-side-expected-' + side, [x for x in scores.values() if x['kind'] == 'control' and x['expected'] == side and x['wrongOutcome']], 1)
    take('negative-false-claim', [x for x in scores.values() if x['kind'] == 'control' and x['falsePositive']], 2)
    take('correct-negative-rejection', [x for x in scores.values() if x['kind'] == 'control' and x['expected'] not in ['A', 'B'] and x['strictPass']], 2)
    natural = [x for x in scores.values() if x['kind'] == 'factual']
    take('short-natural-body', natural, 1, lambda row: (len(q.evidence_text(items[row['caseId']]['email'])), row['caseId']))
    first_natural = items[selected[-1][1]]['metadata']['emailId']
    take('long-natural-body', [x for x in natural if items[x['caseId']]['metadata']['emailId'] != first_natural], 1,
         lambda row: (-len(q.evidence_text(items[row['caseId']]['email'])), row['caseId']))
    p.require(len(selected) == len(used) == 12, 'Wrong panel size')
    runtime = p.read(paths['runtime'])
    prompt = paths['judgePrompt'].read_text()
    panel = []
    requests = []
    source_hashes = {str(path): p.digest(path) for path in paths.values()}
    for index, (bucket, cid) in enumerate(sorted(selected, key=lambda value: value[1])):
        item, old = items[cid], records[cid]
        rule = rules[item['marketId']]
        p.require(old['status'] == rule['status'] == 'completed', 'Unavailable baseline input')
        baseline_request_path = Path(old['directory']) / 'request.json'
        source_hashes[str(baseline_request_path)] = p.digest(baseline_request_path)
        request = p.read(baseline_request_path)
        p.require(p.wire(request) == p.wire(q.judge_request(rule['output'], q.restore_email(item['email']), prompt, runtime)), 'Original request reconstruction differs')
        entry = {'selectionBucket': bucket, 'item': item, 'baselineRecord': old, 'baselineScore': scores[cid],
                 'rule': rule['output'], 'baselineRequest': request, 'executionOrder': p.VARIANTS if index % 2 == 0 else list(reversed(p.VARIANTS))}
        panel.append(entry)
        for variant in p.VARIANTS:
            variant_request = p.reorder(request, variant)
            directory = p.ROOT / 'calls' / cid / variant
            p.once(directory / 'request.json', variant_request)
            with (directory / 'request-wire.json').open('xb') as handle:
                handle.write(p.wire(variant_request))
            (directory / 'request-wire.json').chmod(0o600)
            requests.append({'caseId': cid + '/' + variant, 'request': variant_request})
    p.once(p.ROOT / 'panel.private.json', {'at': p.now(), 'cases': panel, 'selectionSourceHashes': source_hashes})
    p.once(p.ROOT / 'runtime.json', runtime)
    p.once(p.ROOT / 'requests.private.json', {'identifier': runtime['identifier'], 'requests': requests})
    p.once(p.ROOT / 'source-provenance.json', provenance)
    p.once(p.ROOT / 'protocol.json', {
        'declaredAt': p.now(), 'purpose': 'Test quote-first JSON field order as a bounded old-development hypothesis, separate from prompt-only v2.',
        'variants': {'original': p.ORIGINAL_ORDER, 'quote-first': p.QUOTE_ORDER},
        'intervention': 'Reorder only schema properties and required array. Preserve all field names, types, required set, output semantics, full messages, frozen baseline rule, model and sampling settings.',
        'selection': 'Twelve unique completed baseline cases: 2 correct A, 2 correct B, 1 wrong-side expected A, 1 wrong-side expected B, 2 negative false claims, 2 correct negative rejections, shortest and longest natural factual body with distinct email IDs. Case-ID order breaks ties; no v2 outcomes used.',
        'calls': 24, 'workers': 4, 'schedule': 'Four concurrent case pairs. Within each pair run both variants serially; six pairs start with original and six with quote-first, alternating by sorted case ID. Preserve all attempts, no best-of or automatic retry.',
        'runtime': 'Same pinned local Qwen3.5-35B-A3B Q4_K_M, temperature0, seed20260912, 2048 output allowance, original template and grammar. No model/default-setting changes.',
        'gates': 'Code-only review and exact input freeze; then v2 full 1915-row local completion and coordinator confirmation that inference is quiescent; then full-token preflight before any probe call. Must precede final selection. No reserved email or fixture reads.',
        'accounting': 'Transmit the exact saved ordered JSON wire bytes. Hash wire and schema-bearing files, retain original raw HTTP bytes, audit field order and full input token counts. Report missing usage independently. Canonical object hashing is insufficient to distinguish properties-only reorder.',
        'assessment': 'Compare contemporaneous paired strict control correctness, false claims, wrong side, exact grounding, validity, raw output order and observed latency. Also report replay variation versus the earlier baseline. No automatic adoption: any promising change requires separately declared full-cohort evaluation and per-method schema/wire lineage before selection.',
        'limitations': ['Diagnostic panel includes selected prior failures and is not representative or independent.', 'Two natural factual pairs are not strict settlement gold.', 'An exact quote is not proof of entailment or admissibility.', 'No separate reasoning trace is introduced; ordering may help, hurt or have no effect.', 'Balanced order does not make observed concurrent latency a controlled causal benchmark.'],
        'noWeightTraining': True, 'noLivePromotion': True,
    })
    paths_to_seal = [path for path in p.ROOT.rglob('*') if path.is_file() and '__pycache__' not in path.parts]
    p.once(p.ROOT / 'input-freeze.json', {'frozenAt': p.now(), 'pythonVersion': sys.version,
        'fileHashes': {str(path.relative_to(p.ROOT)): p.digest(path) for path in paths_to_seal},
        'externalFileHashes': {str(p.SDK): p.digest(p.SDK), **source_hashes},
        'newModelCalls': 0, 'reservedInputsRead': False})
    print(json.dumps({'prepared': str(p.ROOT), 'cases': len(panel), 'plannedCalls': len(requests),
        'selectionBuckets': dict(collections.Counter(x['selectionBucket'] for x in panel)),
        'executionFirst': dict(collections.Counter(x['executionOrder'][0] for x in panel))}))


if __name__ == '__main__':
    prepare()
