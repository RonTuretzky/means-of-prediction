"""Prepare only the already reviewed old-development panel; no inference."""
import collections
import copy
import json
import os
import sys
from pathlib import Path
import probe as p


def prepare():
    os.umask(0o077)
    o = p.o
    o.require(not (p.ROOT / 'input-freeze.json').exists(), 'Already prepared')
    old_seal = o.read(p.ORDER / 'input-freeze.json')
    o.require(o.digest(p.ORDER / 'input-freeze.json') == 'f2bd28bf3876c85fa1bce950fc91620a36c766491eb06fe075c7dd073ddeb84b', 'Different panel experiment')
    amendment = o.read(p.ORDER / 'reporting-amendment-v1.json')
    o.require(o.digest(p.ROOT / 'order_support.py') == o.digest(p.ORDER / 'probe.py') == amendment['changes']['probe.py']['currentSha256'], 'Transport helper changed')
    for f in (p.ROOT / 'source').iterdir():
        if f.is_file():
            o.require(o.digest(f) == old_seal['fileHashes']['source/' + f.name], 'Copied source differs')
    for name in ['panel.private.json', 'runtime.json']:
        o.require(o.digest(p.ORDER / name) == old_seal['fileHashes'][name], 'Original prepared input differs')
    q = o.study_module()
    prompt = (p.ROOT / 'judge.txt').read_text()
    panel = copy.deepcopy(o.read(p.ORDER / 'panel.private.json'))
    original_panel_sha = o.digest(p.ORDER / 'panel.private.json')
    o.require(len(panel['cases']) == len({e['item']['caseId'] for e in panel['cases']}) == 12, 'Panel size differs')
    requests = []
    for index, entry in enumerate(panel['cases']):
        entry['executionOrder'] = p.SIDES.copy() if index % 2 == 0 else list(reversed(p.SIDES))
        item = entry['item']
        original = entry['baselineRequest']
        original_packet = json.loads(original['messages'][1]['content'])
        o.require(original_packet['rule'] == entry['rule'], 'Original full rule differs')
        o.require(original_packet['email'] == q.email_packet(q.restore_email(item['email'])), 'Original full email differs')
        for side in p.SIDES:
            request = p.request_for(original, side, prompt)
            directory = p.ROOT / 'calls' / item['caseId'] / side
            o.once(directory / 'request.json', request)
            with (directory / 'request-wire.json').open('xb') as handle:
                handle.write(o.wire(request))
            (directory / 'request-wire.json').chmod(0o600)
            requests.append({'caseId': item['caseId'] + '/' + side, 'request': request})
    panel.update({'preparedAt': o.now(), 'sourcePanelSha256': original_panel_sha})
    o.once(p.ROOT / 'panel.private.json', panel)
    runtime = o.read(p.ORDER / 'runtime.json')
    o.once(p.ROOT / 'runtime.json', runtime)
    o.once(p.ROOT / 'requests.private.json', {'identifier': runtime['identifier'], 'requests': requests})
    o.once(p.ROOT / 'protocol.json', {
        'declaredAt': o.now(), 'purpose': 'Test separate strict settlement A/B calls on the same 12 selected old-development examples.',
        'sourcePanelSha256': original_panel_sha,
        'scope': 'Strict-only diagnostic; no factual prediction, selection eligibility, reserved data or live promotion.',
        'intervention': 'Preserve full original baseline-generated rule, email packet and runtime. Adapt the judge prompt to one targetSettlement and schema to verdict/evidenceQuote/missingConditions. Within the split pair only targetSettlement A versus B changes. Comparison against the prior combined task also changes prompt and output schema; it is not a pure causal ablation.',
        'calls': 24, 'cases': 12, 'workers': 4,
        'schedule': 'Four concurrent case pairs; A/B serial within each pair. Six A-first and six B-first, alternating the original panel order. Each call isolated with no history or other answer. Preserve all attempts; no automatic retry or best-of.',
        'outputOrder': p.FIELDS, 'orderChoice': 'Verdict-first fixed before either probe executes, independently of order-probe results.',
        'combination': 'A YES/B NO => A; A NO/B YES => B; both NO => NEITHER; both YES => CONFLICT and unsettled. Any incomplete/malformed call makes the pair UNSCORABLE. Exact quote is measured separately without silently changing the original strict control criterion.',
        'labels': 'Six positive and four negative synthetic controls retain all existing labels and contingency policy. Two natural examples have no strict settlement gold, so their expected factual labels are never used for strict scoring.',
        'gates': 'Code-only review and exact input freeze; full 1915-row v2 completion; completed and reviewed order-probe summary; coordinator confirmation of local quiescence; full token preflight. Must precede final main selection. No concurrent other local model jobs.',
        'runtime': 'Pinned Qwen3.5-35B-A3B Q4_K_M instance; temp0, seed20260912, max2048 output tokens per call, same original template/grammar defaults. Two calls allow4096 total output tokens per pair, compared with2048 in the combined baseline.',
        'accounting': 'Exact saved request bytes transmitted, full raw responses retained, model/reasoning metadata bound, complete-input token usage reconciled. Independent missing input/output/duration fields. Report24 split calls separately against12 combined calls per variant; never compare per-call cost as if it were per-pair cost.',
        'assessment': 'Report strict positives, false claims, wrong sides, conflicts, malformed/unscorable pairs and exact quote coverage; compare both full and common-completed cases with contemporaneous original and quote-first order-probe outputs. Natural cases are claim/abstention observations only. No automatic adoption or use in the main factual-recall selection gate.',
        'limitations': ['Small selected prior-failure panel, not an independent accuracy estimate.', 'Three baseball controls share one event.', 'Adapted prompt and schema confound causal task-decomposition attribution.', 'Separate runs and cache/scheduling affect observed latency.', 'No factual classifier exists in this diagnostic; further full-method design/evaluation would be required.'],
        'noWeightTraining': True, 'noReservedInputsRead': True, 'noAutomaticAdoption': True,
    })
    external = dict(old_seal['externalFileHashes'])
    for name in ['input-freeze.json', 'reporting-amendment-v1.json', 'probe.py', 'panel.private.json', 'runtime.json', 'control-label-review.private.json']:
        path = p.ORDER / name
        external[str(path)] = o.digest(path)
    for path, sha in external.items():
        o.require(o.digest(path) == sha, 'External original changed: ' + path)
    paths = [f for f in p.ROOT.rglob('*') if f.is_file() and '__pycache__' not in f.parts]
    o.once(p.ROOT / 'input-freeze.json', {'frozenAt': o.now(), 'pythonVersion': sys.version,
        'fileHashes': {str(f.relative_to(p.ROOT)): o.digest(f) for f in paths},
        'externalFileHashes': external, 'newModelCalls': 0, 'reservedInputsRead': False})
    print(json.dumps({'prepared': str(p.ROOT), 'calls': len(requests),
        'firstSide': dict(collections.Counter(e['executionOrder'][0] for e in panel['cases'])),
        'inputFreezeSha256': o.digest(p.ROOT / 'input-freeze.json')}))


if __name__ == '__main__':
    prepare()
