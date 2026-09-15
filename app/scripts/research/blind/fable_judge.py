"""Judge-swap diagnostic: Claude Fable 5.1 judges the same frozen rules and whole emails as the local Qwen judge.

The arm lives in its own private root beside the round root. It binds the
round's frozen rules (rules-freeze.json), judge prompt and semantic items by
hash, selects a deterministic subset of development rows, and sends each row
as one blind request: system prompt = the method's judge prompt, user turn =
{"email": <complete semantic email packet>, "rule": <frozen rule>}, the same
content the local judge receives. No labels, tools or history reach the
judge. Rows are scored with the round's own score_record and compared paired
against the Qwen judgments on rows both judges completed.

This is a diagnostic of judge behaviour on one development cohort. Its
outputs never enter teacher shards, selection or fresh evaluation.
"""
import argparse, collections, concurrent.futures, hashlib, json, os, statistics
from pathlib import Path
import qwen_round1 as q
import fable_round
import improve

JUDGE_BUDGET_USD = 2.5
SUBSET_RULE = 'all factual, all weak, controls whose sha256(caseId) starts with 0-3 (about a quarter), unlabeled whose sha256(caseId) starts with 0-7 (about half)'

def subset(items):
    keep = []
    for item in items:
        h = hashlib.sha256(item['caseId'].encode()).hexdigest()[0]
        if item['kind'] in ('factual', 'weak') or (item['kind'] == 'control' and h in '0123') or (item['kind'] == 'unlabeled' and h in '01234567'):
            keep.append(item['caseId'])
    return sorted(keep)

def judge_job(rule, email, prompt, effort):
    if set(rule) != set(q.RULE_SCHEMA['properties']): raise ValueError('Malformed frozen rule')
    packet = q.email_packet(email)
    return {'instructions': prompt, 'input': {'email': packet, 'rule': rule}, 'effort': effort, 'schema': q.JUDGE_SCHEMA, 'maxBudgetUsd': JUDGE_BUDGET_USD}

def prepare(root, method, effort='medium', workers=4):
    root = Path(root); round_root = fable_round.require_fable_root()
    if root.exists(): raise RuntimeError('Judge arm root exists')
    freeze = round_root/'methods'/method/'rules-freeze.json'
    if not freeze.exists(): raise RuntimeError('Frozen rules required: '+str(freeze))
    os.umask(0o077); root.mkdir(parents=True, mode=0o700)
    items = q.load(q.ITEMS); chosen = subset(items); kinds = collections.Counter(i['kind'] for i in items if i['caseId'] in set(chosen))
    plan = {'createdAt': q.r.now(), 'roundRoot': str(round_root), 'method': method, 'judge': 'claude-fable-5-1 via fable_transport', 'effort': effort, 'workers': workers,
            'maxBudgetUsd': JUDGE_BUDGET_USD, 'subsetRule': SUBSET_RULE, 'caseIds': chosen, 'counts': dict(kinds), 'totalRows': len(items),
            'rulesFreezeSha256': fable_round.sha(freeze), 'rulesSha256': fable_round.sha(round_root/'methods'/method/'rules.json'),
            'judgePromptSha256': fable_round.sha(round_root/(method+'-judge.txt')), 'itemsSha256': fable_round.sha(round_root/q.ITEMS),
            'blindness': 'Judge receives the frozen rule and one complete semantic email packet with metadata; no labels, tools, history or other emails.',
            'scope': 'Diagnostic only; not used for selection, teacher feedback or fresh evaluation.'}
    q.r.save(root/'plan.json', plan)
    print(json.dumps({'root': str(root), 'rows': len(chosen), 'counts': plan['counts'], 'effort': effort}), flush=True)

def verify_plan(root):
    root = Path(root); plan = q.r.read(root/'plan.json'); round_root = Path(plan['roundRoot'])
    if str(q.ROOT) != plan['roundRoot']: raise RuntimeError('MOP_QWEN_ROOT differs from the plan round root')
    method = plan['method']
    for name, sha in [('methods/'+method+'/rules-freeze.json', plan['rulesFreezeSha256']), ('methods/'+method+'/rules.json', plan['rulesSha256']),
                      (method+'-judge.txt', plan['judgePromptSha256']), (q.ITEMS, plan['itemsSha256'])]:
        if fable_round.sha(round_root/name) != sha: raise RuntimeError('Frozen input changed: '+name)
    return plan

def run(root):
    root = Path(root); plan = verify_plan(root); method = plan['method']
    if (root/'judgments.private.json').exists(): raise RuntimeError('Arm already complete')
    items = {i['caseId']: i for i in q.load(q.ITEMS)}; rules = {x['marketId']: x for x in q.load('methods/'+method+'/rules.json')}
    prompt = (q.ROOT/(method+'-judge.txt')).read_text()
    def one(case_id):
        item = items[case_id]; rule = rules[item['marketId']]; directory = root/'judgments'/case_id/'1'
        if rule['status'] != 'completed':
            return {'caseId': case_id, 'marketId': item['marketId'], 'trial': 1, 'kind': item['kind'], 'directory': str(directory), 'status': 'rule_unavailable', 'output': None}
        job = judge_job(rule['output'], q.restore_email(item['email']), prompt, plan['effort'])
        try: parsed = improve.invoke(job, directory)
        except RuntimeError:
            if not (directory/'parsed.json').exists(): raise
            parsed = q.r.read(directory/'parsed.json')
        result = q.r.read(directory/'transport-result.json') if (directory/'transport-result.json').exists() else {}
        valid = parsed['status'] == 'completed' and q.valid_judgment(parsed.get('output'))
        return {'caseId': case_id, 'marketId': item['marketId'], 'trial': 1, 'kind': item['kind'], 'directory': str(directory),
                'status': 'completed' if valid else ('invalid_judgment' if parsed['status'] == 'completed' else parsed['status']),
                'output': parsed.get('output') if valid else None, 'usage': parsed.get('usage'), 'seconds': result.get('seconds'), 'costUsd': result.get('costUsd'),
                'limitWaits': len(result.get('limitWaits', []))}
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=plan['workers']) as pool:
        for row in pool.map(one, plan['caseIds']):
            records.append(row); print(json.dumps({'fableJudge': method, 'judged': len(records), 'total': len(plan['caseIds']), 'status': row['status']}), flush=True)
    q.r.save(root/'judgments.private.json', records)
    scores = [q.score_record(items[x['caseId']], x) for x in records]
    q.r.save(root/'scores.private.json', scores)
    summary = summarize(records, scores, plan)
    q.r.save(root/'summary.json', summary); print(json.dumps({k: v for k, v in summary.items() if k != 'metrics'}), flush=True)
    return summary

def summarize(records, scores, plan):
    summary = fable_round.subset_summary(scores)
    times = [x['seconds'] for x in records if x.get('seconds') is not None]; costs = [x['costUsd'] for x in records if x.get('costUsd') is not None]
    summary.update({'at': q.r.now(), 'method': plan['method'], 'judge': plan['judge'], 'effort': plan['effort'], 'rows': len(records),
                    'statuses': dict(collections.Counter(x['status'] for x in records)),
                    'medianSeconds': statistics.median(times) if times else None, 'listCostUsd': sum(costs), 'limitWaits': sum(x.get('limitWaits', 0) for x in records)})
    return summary

def compare(root):
    """Paired Fable-vs-Qwen judge comparison on rows both completed; writes comparison.json."""
    root = Path(root); plan = q.r.read(root/'plan.json'); method = plan['method']
    fable = {x['caseId']: x for x in q.r.read(root/'scores.private.json')}
    qwen_path = q.ROOT/'methods'/method/'development-scores.private.json'
    if not qwen_path.exists(): raise RuntimeError('Qwen development scores not complete yet')
    qwen = {x['caseId']: x for x in q.r.read(qwen_path) if x['caseId'] in fable}
    common = [k for k in fable if fable[k]['valid'] and qwen[k]['valid']]
    def block(rows):
        s = fable_round.subset_summary(rows); return {'metrics': s['metrics'], 'factFamilyMacroRecall': s['factFamilyMacroRecall'], 'utility': s['utility']}
    out = {'at': q.r.now(), 'method': method, 'subsetRows': len(fable), 'commonCompleted': len(common),
           'onlyFableCompleted': sum(fable[k]['valid'] and not qwen[k]['valid'] for k in fable), 'onlyQwenCompleted': sum(qwen[k]['valid'] and not fable[k]['valid'] for k in fable),
           'fable': block([fable[k] for k in common]), 'qwen': block([qwen[k] for k in common]),
           'fableAllSubset': block(list(fable.values())), 'qwenAllSubset': block(list(qwen.values())),
           'agreement': {'factualOutcome': sum(fable[k]['factualOutcome'] == qwen[k]['factualOutcome'] for k in common),
                         'settlementOutcome': sum(fable[k]['settlementOutcome'] == qwen[k]['settlementOutcome'] for k in common), 'of': len(common)},
           'qualification': 'One development cohort subset, retrospective factual labels and synthetic controls; not settlement accuracy and not a population estimate. Qwen replay noise floor: 50/55 strict decisions agreed under 4-way concurrency.'}
    q.r.save(root/'comparison.json', out)
    print(json.dumps({'common': len(common), 'fableGrounded': out['fable']['metrics']['factual']['groundedFactualPasses'], 'qwenGrounded': out['qwen']['metrics']['factual']['groundedFactualPasses'],
                      'fableStrictPos': out['fable']['metrics']['control']['strictPositivePasses'], 'qwenStrictPos': out['qwen']['metrics']['control']['strictPositivePasses'],
                      'fableFalsePos': out['fable']['metrics']['control']['falsePositives'], 'qwenFalsePos': out['qwen']['metrics']['control']['falsePositives'],
                      'fableUtility': round(out['fable']['utility'], 4), 'qwenUtility': round(out['qwen']['utility'], 4), 'agreement': out['agreement']}), flush=True)
    return out

if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['prepare', 'run', 'compare']); parser.add_argument('--root', required=True)
    parser.add_argument('--method', default='baseline'); parser.add_argument('--effort', default='medium'); parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.root, args.method, args.effort, args.workers)
    elif args.action == 'run': run(args.root)
    else: compare(args.root)
