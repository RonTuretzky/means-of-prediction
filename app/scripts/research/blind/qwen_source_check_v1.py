"""Paired, exposed-development source-check diagnostic; never opens reserved data.

Frozen baseline rules and complete emails; only the system prompt differs.
No retries, generation calls, weight updates or method promotion.
"""
import argparse
import concurrent.futures
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import urllib.request

import qwen_round1 as q
import qwen_v3_unattempted_continuation as c
import real_answerability_score_v1 as scoring

ROOT = q.ROOT/'source-check-v1'
PANEL = scoring.a.ROOT
VARIANTS = ('baseline', 'source_check')
ADDENDUM = '''
Before setting either settlement predicate to YES, check the source route explicitly, separately from whether the reported fact sounds true. A reputable NYT report is one publisher. Its credibility alone does not establish an exclusively required official result, or a consensus of independent reports. A link, photo credit, sender domain or a reporter's uncorroborated assertion is not that missing evidence. For an official-source route, the email must actually identify and report the relevant official result with the required metric/event; do not invent attribution. For a reporting-consensus route, the supplied body must establish the required corroboration; do not assume unseen articles agree. If the rule instead expressly permits ordinary credible reporting as an alternative, apply that alternative without adding an official-source or consensus requirement. Apply fallback requirements only when their trigger occurs. Keep date/event, metric, finality and exceptions checks separate. Do not repair missing market metadata using remembered results.
When no permitted source route is established, keep factualOutcome as the reported core fact if supported, set both outcomeA and outcomeB to NO, and name the missing source condition in missingConditions. An exact factual quote does not waive a source condition. Source sufficiency alone does not waive any other settlement condition. Return the same concise final JSON schema, without reasoning prose.'''
PINS = {
    PANEL/'plan.private.json': 'bf5ae169adbae28b430c516c85b368041e0eb47d70adb7969a7a6df73dd53474',
    PANEL/'adjudicated-labels.private.json': 'f5a89076ae95dc93c0adbac4e7b3725dd525abb8db38d4c8da87811c34c446fa',
    PANEL/'adjudicated-labels-seal.json': '3fdbfd9c9756ff21bba09c58c16b4258d9a7be86beb98f342e09fc7bcba6686f',
}
SUPPLEMENT = c.ROOT/'runtime-supplement-v1/audit.py'


def check_pins(pins):
    for path, sha in pins.items():
        if q.r.digest(path) != sha:
            raise RuntimeError('Frozen dependency changed: '+str(path))


def plan_path():
    final=ROOT/'plan-amended-v2.private.json'
    if final.exists():
        return final
    amended=ROOT/'plan-amended.private.json'
    return amended if amended.exists() else ROOT/'plan.private.json'


def amend():
    if (ROOT/'started.json').exists() or (ROOT/'responses').exists():
        raise RuntimeError('Audit amendment is pre-launch only')
    plan=q.r.read(ROOT/'plan.private.json')
    saved=q.r.read(ROOT/'initial-draft-source-manifest.private.json')
    for original,record in saved.items():
        if q.r.digest(record['path']) != plan['pins'][original] or record['sha256'] != plan['pins'][original]:
            raise RuntimeError('Original draft source not preserved')
    changed={str(Path(__file__)),str(Path(__file__).with_name('test_qwen_source_check_v1.py'))}
    check_pins({p:h for p,h in plan['pins'].items() if p not in changed})
    extra=[Path(c.audit_support.__file__),Path(scoring.a.__file__),Path(scoring.auditor.__file__)]
    plan['pins'].update({p:q.r.digest(p) for p in changed})
    plan['pins'].update({str(p):q.r.digest(p) for p in extra})
    plan['initialDraft']={'planSha256':q.r.digest(ROOT/'plan.private.json'),
        'sourceManifestSha256':q.r.digest(ROOT/'initial-draft-source-manifest.private.json')}
    plan['amendment']='Pre-launch review: pin full local source closure; audit all parseable response metadata, malformed outputs and missing usage. Request bytes, labels, scoring decisions and preflight remain unchanged.'
    c.once(ROOT/'plan-amended.private.json',plan)
    print(json.dumps({'amendedPlanSha256':q.r.digest(plan_path()),'requestFileSha256':plan['requestsSha256']}))


def build(selected, items, rules, runtime, baseline):
    if len(selected) != 60 or len({s['caseId'] for s in selected}) != 60:
        raise ValueError('Exactly the full unique 60-pair panel is required')
    entries = []
    for ordinal, sel in enumerate(selected):
        item, rule = items[sel['caseId']], rules[sel['marketId']]
        if item['kind'] != 'factual' or item['marketId'] != sel['marketId']:
            raise ValueError('Panel identity differs')
        available = rule['status'] == 'completed' and rule.get('output') is not None
        # Alternating within-pair order controls simple dispatch-order imbalance.
        variants = VARIANTS if ordinal % 2 == 0 else tuple(reversed(VARIANTS))
        for variant in variants:
            prompt = baseline if variant == 'baseline' else baseline + ADDENDUM
            request = q.judge_request(rule['output'], q.restore_email(item['email']), prompt, runtime) if available else None
            if request is not None:
                packet = json.loads(request['messages'][1]['content'])
                if packet['email'] != item['email'] or set(packet) != {'email', 'rule'}:
                    raise ValueError('Full blinded email packet differs')
            entries.append({'name':variant+'/'+sel['caseId'], 'variant':variant,
                'caseId':sel['caseId'], 'marketId':sel['marketId'], 'request':request,
                'unavailableReason':None if available else 'Frozen baseline rule unavailable: '+rule['status']})
    return entries


def prepare():
    if ROOT.exists():
        raise RuntimeError('Study already prepared; no overwrite')
    check_pins(PINS)
    selected = q.r.read(PANEL/'plan.private.json')['selected']
    entries = build(selected, {i['caseId']:i for i in q.load(q.ITEMS)},
        {r['marketId']:r for r in q.load('methods/baseline/rules.json')},
        q.load('runtime.json'), (q.ROOT/'baseline-judge.txt').read_text())
    deps = [Path(__file__), Path(__file__).with_name('test_qwen_source_check_v1.py'),
        Path(q.__file__), Path(q.r.__file__), Path(q.semantic.__file__), Path(c.__file__),
        Path(scoring.__file__), c.HERE/'qwen_v3_continuation_runtime.mjs', SUPPLEMENT,
        q.ROOT/'runtime.json', q.ROOT/'baseline-judge.txt', q.ROOT/q.ITEMS,
        q.ROOT/'methods/baseline/rules.json', q.ROOT/'methods/baseline/rules-freeze.json']
    pins = {str(p):sha for p,sha in PINS.items()}
    pins.update({str(p):q.r.digest(p) for p in deps})
    for name, sha in q.load('methods/baseline/rules-freeze.json')['fileHashes'].items():
        pins[str(q.ROOT/name)] = sha
    check_pins(pins)
    c.once(ROOT/'requests.private.json', {'identifier':q.load('runtime.json')['identifier'],
        'requests':[{'caseId':e['name'], 'request':e['request']} for e in entries if e['request'] is not None]})
    c.once(ROOT/'runtime-only.private.json', {'identifier':q.load('runtime.json')['identifier'], 'requests':[]})
    c.once(ROOT/'plan.private.json', {'at':q.r.now(), 'entries':entries, 'pins':pins,
        'requestsSha256':q.r.digest(ROOT/'requests.private.json'), 'workers':4,
        'executables':q.load('v3-unattempted-continuation-v1/plan.private.json')['executables'],
        'scope':'All 60 exposed model-adjudicated development pairs; paired prompt diagnostic, not independent accuracy, new rule generation, V4, or promotion. Unavailable rules and execution failures remain in the denominator. No reserved inputs. One attempt per variant/case; interrupted calls remain unknown.'})
    print(json.dumps({'prepared':str(ROOT), 'planSha256':q.r.digest(ROOT/'plan.private.json'),
        'rows':len(entries), 'calls':sum(e['request'] is not None for e in entries)}))


def verify():
    plan = q.r.read(plan_path())
    if 'initialDraft' in plan:
        if plan['initialDraft']['planSha256'] != q.r.digest(ROOT/'plan.private.json') or plan['initialDraft']['sourceManifestSha256'] != q.r.digest(ROOT/'initial-draft-source-manifest.private.json'):
            raise RuntimeError('Initial draft lineage changed')
        saved=q.r.read(ROOT/'initial-draft-source-manifest.private.json')
        for record in saved.values():
            check_pins({record['path']:record['sha256']})
        if plan['entries'] != q.r.read(ROOT/'plan.private.json')['entries']:
            raise RuntimeError('Audit amendment altered requests')
    for path, sha in plan.get('amendmentHistory',{}).items():
        check_pins({path:sha})
    check_pins(plan['pins'])
    if q.r.digest(ROOT/'requests.private.json') != plan['requestsSha256']:
        raise RuntimeError('Preflight requests changed')
    expected = build(q.r.read(PANEL/'plan.private.json')['selected'], {i['caseId']:i for i in q.load(q.ITEMS)},
        {r['marketId']:r for r in q.load('methods/baseline/rules.json')}, q.load('runtime.json'), (q.ROOT/'baseline-judge.txt').read_text())
    if expected != plan['entries']:
        raise RuntimeError('Frozen blinded requests differ')
    for info in plan['executables'].values():
        if c.executable(info['path']) != {k:info[k] for k in ['path','sha256']}:
            raise RuntimeError('Runtime executable changed')
    return plan


def runtime_audit(plan, phase, full=False, expected=None):
    snapshot = c.runtime_snapshot(plan['executables'], ROOT/('requests.private.json' if full else 'runtime-only.private.json'), expected)
    spec = importlib.util.spec_from_file_location('source_check_runtime_supplement', SUPPLEMENT)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    with urllib.request.urlopen('http://127.0.0.1:1234/api/v1/models', timeout=15) as response:
        api = json.loads(response.read())
    snapshot['supplement'] = mod.validate(q.load('runtime.json'), api, snapshot['appVersion'], snapshot['appBuild'], q.r.digest(c.SDK))
    if full:
        wanted = {r['caseId'] for r in q.r.read(ROOT/'requests.private.json')['requests']}
        counts = snapshot['sdk']['counts']
        if len(counts) != len(wanted) or {r['caseId'] for r in counts} != wanted or any(r['inputTokens']+r['outputAllowance'] > q.load('runtime.json')['contextLength'] for r in counts):
            raise RuntimeError('Incomplete or oversized full-input preflight')
    c.once(ROOT/(phase+'.private.json'), snapshot)
    return snapshot


def preflight():
    plan = verify()
    if (ROOT/'started.json').exists():
        raise RuntimeError('Preflight is not a resume')
    runtime_audit(plan, 'preflight', full=True)
    print(json.dumps({'preflightSha256':q.r.digest(ROOT/'preflight.private.json')}))


def review_gate(plan):
    review = q.r.read(ROOT/'launch-review.json')
    if review.get('approved') is not True or review.get('localOwnershipReleased') is not True or review.get('noCompetingLocalInference') is not True:
        raise RuntimeError('Explicit reviewed local ownership required')
    if review['planSha256'] != q.r.digest(plan_path()) or review['preflightSha256'] != q.r.digest(ROOT/'preflight.private.json'):
        raise RuntimeError('Launch review hashes differ')


def run():
    plan = verify(); review_gate(plan)
    with (q.ROOT/'local-inference-owner.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (ROOT/'responses').exists() or (ROOT/'started.json').exists():
            raise RuntimeError('Existing attempts require reconciliation, never automatic retry')
        runtime_audit(plan, 'pre-launch', expected=q.r.read(ROOT/'preflight.private.json')['sdk']['loadConfig'])
        c.once(ROOT/'started.json', {'at':q.r.now(), 'pid':os.getpid(), 'planSha256':q.r.digest(plan_path())})
        def one(e):
            directory = ROOT/'responses'/e['name']
            if directory.exists():
                raise RuntimeError('Attempt directory already exists')
            result = q.local_call(e['request'], directory)
            return {'name':e['name'], 'status':result['status']}
        rows = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(one,e) for e in plan['entries'] if e['request'] is not None]
            for future in concurrent.futures.as_completed(futures):
                rows.append(future.result())
                print(json.dumps({'finished':len(rows), 'total':len(futures), **rows[-1]}),flush=True)
        c.once(ROOT/'dispatch-finished.private.json', {'at':q.r.now(), 'rows':rows})
        runtime_audit(plan, 'post-dispatch', expected=q.r.read(ROOT/'preflight.private.json')['sdk']['loadConfig'])


def audit_result(e, directory):
    if q.r.read(directory/'request.json') != e['request']:
        raise RuntimeError('Actual request differs from blind plan')
    result = q.r.read(directory/'result.json')
    if result['requestSha256'] != q.r.hash_value(e['request']):
        raise RuntimeError('Request hash differs')
    raw_path = directory/'response.raw'
    if not raw_path.exists():
        if result['status'] != 'transport_failed':
            raise RuntimeError('Unaccounted missing response')
        return result, None
    if result.get('rawResponseSha256') != q.r.digest(raw_path):
        raise RuntimeError('Raw response hash differs')
    try:
        raw = json.loads(raw_path.read_bytes())
    except (ValueError, UnicodeDecodeError):
        if result['status'] != 'transport_failed' or result.get('output') is not None:
            raise RuntimeError('Malformed raw response misclassified')
        return result, None
    if raw != q.r.read(directory/'response.json') or result['responseSha256'] != q.r.digest(directory/'response.json'):
        raise RuntimeError('Parsed response differs from raw')
    choice = (raw.get('choices') or [{}])[0]
    try:
        output = json.loads(choice.get('message',{}).get('content',''))
    except (ValueError, TypeError):
        output = None
    expected = 'completed' if result['httpStatus'] == 200 and choice.get('finish_reason') == 'stop' and q.valid_judgment(output) else 'failed'
    if result['status'] != expected or result['output'] != output or result['usage'] != raw.get('usage') or result['finishReason'] != choice.get('finish_reason'):
        raise RuntimeError('Result status/output/usage differs from raw')
    if result.get('returnedModel') != raw.get('model') or ((result['status']=='completed' or raw.get('model') is not None) and raw.get('model') != e['request']['model']):
        raise RuntimeError('Returned model differs')
    reasoning=choice.get('message',{}).get('reasoning_content','') or ''
    if result.get('reasoningCharacters') != len(reasoning):
        raise RuntimeError('Recorded reasoning length differs')
    return result, raw.get('usage')


def audit():
    plan = verify(); review_gate(plan)
    q.r.read(ROOT/'post-dispatch.private.json')
    finished = q.r.read(ROOT/'dispatch-finished.private.json')['rows']
    expected = {e['name'] for e in plan['entries'] if e['request'] is not None}
    if len(finished) != len(expected) or {r['name'] for r in finished} != expected:
        raise RuntimeError('Incomplete dispatch coverage')
    actual = {str(p.parent.relative_to(ROOT/'responses')) for p in (ROOT/'responses').rglob('started.json')}
    if actual != expected:
        raise RuntimeError('Extra or missing attempts')
    decisions = {v:{} for v in VARIANTS}; quoted = {v:{} for v in VARIANTS}; rows=[]
    token_counts = {r['caseId']:r['inputTokens'] for r in q.r.read(ROOT/'preflight.private.json')['sdk']['counts']}
    for e in plan['entries']:
        if e['request'] is None:
            decision='UNSCORABLE'; exact=False; status='rule_unavailable'; hashes={}; usage=None; seconds=None
        else:
            directory=ROOT/'responses'/e['name']; result,usage=audit_result(e,directory)
            status=result['status']; output=result.get('output')
            seconds=result.get('seconds')
            if usage is not None and usage.get('prompt_tokens') != token_counts[e['name']]:
                raise RuntimeError('Actual full-input token count differs from preflight')
            decision=q.settlement(output) if status=='completed' else 'UNSCORABLE'
            email=json.loads(e['request']['messages'][1]['content'])['email']
            exact=bool(isinstance(output,dict) and isinstance(output.get('evidenceQuote'),str) and output['evidenceQuote'] and output['evidenceQuote'] in email['completeSemanticText'])
            hashes={str(p.relative_to(ROOT)):q.r.digest(p) for p in directory.iterdir() if p.is_file()}
        decisions[e['variant']][e['caseId']]=decision
        quoted[e['variant']][e['caseId']]=decision if exact or decision not in ['A','B'] else 'NEITHER'
        rows.append({'name':e['name'],'status':status,'decision':decision,'exactQuote':exact,'fileHashes':hashes,'usage':usage,'seconds':seconds})
    labels=q.r.read(PANEL/'adjudicated-labels.private.json')
    common={cid for cid in decisions['baseline'] if all(decisions[v][cid]!='UNSCORABLE' for v in VARIANTS)}
    report={'at':q.r.now(),'planSha256':q.r.digest(plan_path()),'rows':rows,
        'allPanel':{v:{'strict':scoring.measure(labels,decisions[v]),'quoted':scoring.measure(labels,quoted[v])} for v in VARIANTS},
        'commonCompleted':len(common),'paired':{v:{'strict':scoring.measure([l for l in labels if l['caseId'] in common],{k:d for k,d in decisions[v].items() if k in common}),
            'quoted':scoring.measure([l for l in labels if l['caseId'] in common],{k:d for k,d in quoted[v].items() if k in common})} for v in VARIANTS},
        'qualification':'Exposed development prompt diagnostic under model-adjudicated source interpretation. One answerable example; no projected accuracy, statistical independence, weights update or automatic promotion.'}
    report['artifactHashes']={str(p.relative_to(ROOT)):q.r.digest(p) for p in ROOT.rglob('*') if p.is_file()}
    c.once(ROOT/'audited-results.private.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['rows','artifactHashes']}))


if __name__ == '__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['prepare','amend','verify','preflight','run','audit'])
    args=parser.parse_args(); globals()[args.command]()
