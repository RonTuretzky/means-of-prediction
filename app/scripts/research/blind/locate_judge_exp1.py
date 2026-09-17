"""Locate-then-judge, experiment 1: replay a frontier locator's quotes through the small local judge.

Everything is held fixed except the evidence body: same frozen rules, same
judge prompt, same judge request builder, same scorer. The whole email is
replaced by a short excerpt around the quote the Fable judge located (its
verdict is discarded; only the excerpt is used). Rows where the locator
produced no verifiable quote submit nothing, which the settlement flow treats
as "no claim". Local inference only; outputs are immutable like every other
judge call.

Answers one question: how much of the whole-email gap between the small
judge and the frontier judge is closed by locating alone?
"""
import argparse, collections, concurrent.futures, json, os, re
from pathlib import Path
import qwen_round1 as q
import fable_round

NO_CLAIM = {'factualOutcome': 'NEITHER', 'outcomeA': 'NO', 'outcomeB': 'NO', 'evidenceQuote': '', 'missingConditions': ['No excerpt submitted by the locator']}

def excerpt(text, quote, window):
    start = text.find(quote)
    if start < 0: return None
    if window == 0: return quote
    lo, hi = max(0, start-window), min(len(text), start+len(quote)+window)
    # Snap outward to sentence or line boundaries so the judge never sees half a sentence.
    head = max(text.rfind('. ', 0, lo), text.rfind('\n', 0, lo)); lo = head+1 if head >= 0 and lo-head < 200 else lo
    tails = [i for i in (text.find('. ', hi), text.find('\n', hi)) if i >= 0]; hi = min(tails)+1 if tails and min(tails)-hi < 200 else hi
    return text[lo:hi].strip()

def run(root, arm_root, method, window, workers):
    root = Path(root); fable_round.require_fable_root()
    if (root/'judgments.private.json').exists(): raise RuntimeError('Experiment already complete')
    os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    items = {i['caseId']: i for i in q.load(q.ITEMS)}; rules = {x['marketId']: x for x in q.load('methods/'+method+'/rules.json')}
    runtime = q.load('runtime.json'); prompt = (q.ROOT/(method+'-judge.txt')).read_text()
    located = {x['caseId']: x for x in q.r.read(Path(arm_root)/'judgments.private.json')}
    plan = {'at': q.r.now(), 'method': method, 'locatorArm': str(arm_root), 'windowCharacters': window, 'rows': len(located),
            'design': 'Identical frozen rule, judge prompt, request builder and scorer as the whole-email local judge; only completeSemanticText is replaced by the excerpt. Locator verdicts are discarded.'}
    q.r.save(root/'plan.json', plan)
    def one(case_id):
        item = items[case_id]; rule = rules[item['marketId']]; loc = located[case_id]; base = {'caseId': case_id, 'marketId': item['marketId'], 'trial': 1, 'kind': item['kind']}
        if rule['status'] != 'completed' or loc['status'] != 'completed': return {**base, 'status': 'rule_unavailable' if rule['status'] != 'completed' else 'locator_unavailable', 'output': None}
        text = q.evidence_text(item['email']); quote = (loc['output'] or {}).get('evidenceQuote') or ''
        cut = excerpt(text, quote, window) if quote else None
        if not cut: return {**base, 'status': 'completed', 'output': dict(NO_CLAIM), 'noExcerpt': True, 'excerptCharacters': 0}
        email = {**q.restore_email(item['email']), 'semanticText': cut}
        result = q.local_call(q.judge_request(rule['output'], email, prompt, runtime), root/'judgments'/case_id/'1')
        return {**base, 'directory': str(root/'judgments'/case_id/'1'), 'excerptCharacters': len(cut), 'noExcerpt': False, **result}
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(one, sorted(located)):
            records.append(row)
            if len(records) % 50 == 0: print(json.dumps({'judged': len(records), 'total': len(located)}), flush=True)
    q.r.save(root/'judgments.private.json', records)
    scores = [q.score_record(items[x['caseId']], x) for x in records]; q.r.save(root/'scores.private.json', scores)
    return compare(root, arm_root, method)

def compare(root, arm_root, method):
    root = Path(root); mine = {x['caseId']: x for x in q.r.read(root/'scores.private.json')}
    fable = {x['caseId']: x for x in q.r.read(Path(arm_root)/'scores.private.json')}
    whole = {x['caseId']: x for x in q.load('methods/'+method+'/development-scores.private.json') if x['caseId'] in mine}
    common = [k for k in mine if mine[k]['valid'] and fable[k]['valid'] and whole[k]['valid']]
    def block(rows):
        s = fable_round.subset_summary(rows); m = s['metrics']
        return {'groundedFactual': m['factual']['groundedFactualPasses'], 'rawFactual': m['factual']['factualPasses'], 'factualTotal': m['factual']['positiveTotal'],
                'strictPositives': m['control']['strictPositivePasses'], 'positiveControls': m['control']['positiveTotal'], 'falsePositives': m['control']['falsePositives'], 'negativeControls': m['control']['negativeTotal'],
                'wrongSide': m['control']['wrongOutcomes'], 'weakOrUnlabeledClaims': sum(x['settlementOutcome'] in ['A', 'B'] for x in rows if x['kind'] in ['weak', 'unlabeled']),
                'macroRecall': round(s['factFamilyMacroRecall'], 3), 'utility': round(s['utility'], 3)}
    records = q.r.read(root/'judgments.private.json'); sizes = [x['excerptCharacters'] for x in records if x.get('excerptCharacters')]
    out = {'at': q.r.now(), 'commonRows': len(common), 'excerptRows': len(sizes), 'noExcerptRows': sum(bool(x.get('noExcerpt')) for x in records),
           'medianExcerptCharacters': sorted(sizes)[len(sizes)//2] if sizes else None, 'statuses': dict(collections.Counter(x['status'] for x in records)),
           'smallJudgeWholeEmail': block([whole[k] for k in common]), 'smallJudgeOnLocatedExcerpt': block([mine[k] for k in common]), 'frontierJudgeWholeEmail': block([fable[k] for k in common])}
    q.r.save(root/'comparison.json', out); print(json.dumps(out, indent=1), flush=True); return out

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['run', 'compare']); p.add_argument('--root', required=True); p.add_argument('--arm-root', required=True)
    p.add_argument('--method', default='baseline'); p.add_argument('--window', type=int, default=300); p.add_argument('--workers', type=int, default=4); a = p.parse_args()
    run(a.root, a.arm_root, a.method, a.window, a.workers) if a.action == 'run' else compare(a.root, a.arm_root, a.method)
