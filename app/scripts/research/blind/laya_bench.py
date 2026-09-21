"""Quick benchmark of Laya (non-autoregressive typed-decision encoder) as the verifiable settlement judge.

Same rows, rules and located passages as the Qwen and Fable judge comparisons
(730-row judge-swap subset of the Fable round). Standalone: reads the private
JSON artifacts directly so it can run in Laya's own Python environment.

Arms
  excerpt-question  yes/no markets: P(text reports the question's YES as a completed fact), on the
                    passage the frontier locator found. Comparable to locate-then-judge 1c.
  excerpt-claims    all markets: one noul per generated claim (A, B). Comparable to 1b.
  excerpt-choice    all markets: one choice over {A claim, B claim, neither}.
  sweep-question    yes/no markets, NO locator: slide windows over the whole email; a market-email
                    fires if any window's probability clears the threshold. This is both the
                    locator-free recall and the false-YES safety test.
Outputs private JSON under --root; prints content-free counts only.
"""
import argparse, collections, json, os, statistics, time
from pathlib import Path

ROUND = Path.home()/'.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915'
ARM = Path.home()/'.local/share/means-of-prediction/slides/fable-judge-baseline-20260915'
THRESHOLDS = [0.5, 0.7, 0.9, 0.97]
RULE = ' Forecasts, odds, plans, hypotheticals, denials and quoted predictions do not count.'

def read(p): return json.loads(Path(p).read_text())

def excerpt(text, quote, window=300):
    start = text.find(quote)
    if start < 0: return None
    lo, hi = max(0, start-window), min(len(text), start+len(quote)+window)
    head = max(text.rfind('. ', 0, lo), text.rfind('\n', 0, lo)); lo = head+1 if head >= 0 and lo-head < 200 else lo
    tails = [i for i in (text.find('. ', hi), text.find('\n', hi)) if i >= 0]; hi = min(tails)+1 if tails and min(tails)-hi < 200 else hi
    return text[lo:hi].strip()

def windows(text, size, stride):
    if len(text) <= size: return [text]
    return [text[i:i+size] for i in range(0, max(1, len(text)-size+stride), stride)]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); ap.add_argument('--checkpoint', default='english', choices=['english', 'typed-decisions'])
    ap.add_argument('--device', default='auto'); ap.add_argument('--sweep-limit', type=int, default=0, help='max long natural emails in the sweep (0 = all)')
    ap.add_argument('--window', type=int, default=1200); ap.add_argument('--stride', type=int, default=600); a = ap.parse_args()
    import laya, torch
    device = a.device if a.device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cpu')
    kwargs = {} if a.checkpoint == 'english' else {'subfolder': 'typed-decisions'}
    try: agent = laya.load('convaiinnovations/laya', device=device, **kwargs)
    except TypeError: agent = laya.load('convaiinnovations/laya', **kwargs)
    root = Path(a.root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    items = {i['caseId']: i for i in read(ROUND/'development-items-semantic.private.json')}
    public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}
    rules = {x['marketId']: x for x in read(ROUND/'methods/baseline/rules.json')}
    located = {x['caseId']: x for x in read(ARM/'judgments.private.json')}
    latencies = []
    def ask(state, questions):
        t = time.time(); out = agent.predict(state, questions)['answers']; latencies.append(time.time()-t); return out
    def binary(p):
        labels = [str(l).strip().lower() for l in p['outcomeLabels']]
        return ('A' if labels[0] == 'yes' else 'B') if sorted(labels) == ['no', 'yes'] else None
    qq = lambda question: {'q': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened, that the answer to this question is yes: '+question+RULE}}

    rows = []
    for cid in sorted(located):
        item = items[cid]; p = public[item['marketId']]; rule = rules[item['marketId']]; loc = located[cid]
        row = {'caseId': cid, 'kind': item['kind'], 'expected': item['expected'], 'yesSide': binary(p)}
        text = item['email'].get('completeSemanticText', ''); subject = item['email'].get('subject', '')
        quote = ((loc.get('output') or {}).get('evidenceQuote') or '') if loc['status'] == 'completed' else ''
        cut = excerpt(text, quote) if quote else None
        row['hasExcerpt'] = bool(cut)
        if cut and rule['status'] == 'completed':
            state = {'subject': subject, 'body': cut}
            claims = {'A': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['output']['factualA'][:600]+RULE},
                      'B': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['output']['factualB'][:600]+RULE},
                      'pick': {'type': 'choice', 'instructions': 'Which statement does the text report as a completed fact?',
                               'criteria': {'A': rule['output']['factualA'][:300], 'B': rule['output']['factualB'][:300], 'neither': 'The text does not report either statement as a completed fact.'}}}
            if row['yesSide']: claims.update(qq(p['question']))
            ans = ask(state, claims)
            row.update({'pA': ans['A']['noul'], 'pB': ans['B']['noul'], 'pick': ans['pick']['choice'], 'pickConfidence': ans['pick']['confidence'], 'pQuestion': ans['q']['noul'] if row['yesSide'] else None})
        rows.append(row)
        if len(rows) % 100 == 0: print(json.dumps({'excerptPhase': len(rows), 'of': len(located)}), flush=True)

    # Locator-free sweep over whole emails, yes/no markets only.
    sweep_ids = [cid for cid in sorted(located) if binary(public[items[cid]['marketId']])]
    long_seen = 0
    for n, cid in enumerate(sweep_ids):
        item = items[cid]; text = item['email'].get('completeSemanticText', ''); row = next(r for r in rows if r['caseId'] == cid)
        if len(text) > 6000:
            long_seen += 1
            if a.sweep_limit and long_seen > a.sweep_limit: row['sweepSkipped'] = True; continue
        ws = windows(text, a.window, a.stride); best = 0.0
        for w in ws:
            best = max(best, ask({'subject': item['email'].get('subject', ''), 'body': w}, qq(public[item['marketId']]['question']))['q']['noul'])
        row.update({'sweepWindows': len(ws), 'sweepMaxP': best})
        if (n+1) % 50 == 0: print(json.dumps({'sweepPhase': n+1, 'of': len(sweep_ids)}), flush=True)
    (root/'rows.private.json').write_text(json.dumps(rows))

    def side(r): return r['expected'] if r['expected'] in ('A', 'B') else None
    def claims_outcome(r, t):
        a_, b_ = r.get('pA', 0) >= t, r.get('pB', 0) >= t
        return 'CONFLICT' if a_ and b_ else 'A' if a_ else 'B' if b_ else 'NEITHER'
    out = {'checkpoint': a.checkpoint, 'device': device, 'rows': len(rows), 'rowsWithExcerpt': sum(r['hasExcerpt'] for r in rows), 'forwardPasses': len(latencies),
           'medianMsPerCall': round(1000*statistics.median(latencies), 1) if latencies else None, 'thresholds': {}}
    fact = [r for r in rows if r['kind'] == 'factual']; ctrl = [r for r in rows if r['kind'] == 'control']; weak = [r for r in rows if r['kind'] in ('weak', 'unlabeled')]
    out['excerptChoice'] = {'factualCorrect': sum(r.get('pick') == side(r) for r in fact), 'factualTotal': len(fact), 'factualWrongSide': sum(r.get('pick') in ('A', 'B') and r.get('pick') != side(r) for r in fact),
                            'positiveControlsCorrect': sum(r.get('pick') == side(r) for r in ctrl if side(r)), 'positiveControls': sum(bool(side(r)) for r in ctrl),
                            'falseOnNegativeControls': sum(r.get('pick') in ('A', 'B') for r in ctrl if not side(r)), 'negativeControls': sum(not side(r) for r in ctrl),
                            'falseOnWeakUnlabeled': sum(r.get('pick') in ('A', 'B') for r in weak), 'weakUnlabeled': len(weak)}
    for t in THRESHOLDS:
        yn = lambda rs: [r for r in rs if r['yesSide']]
        ty = [r for r in yn(fact) if side(r) == r['yesSide']]; tn = [r for r in yn(fact) if side(r) and side(r) != r['yesSide']]
        cy = [r for r in yn(ctrl) if side(r) == r['yesSide']]; cn = [r for r in yn(ctrl) if side(r) != r['yesSide']]
        sw = lambda rs: [r for r in rs if 'sweepMaxP' in r]
        out['thresholds'][str(t)] = {
            'excerptClaims': {'factualCorrect': sum(claims_outcome(r, t) == side(r) for r in fact), 'factualTotal': len(fact), 'factualWrongOrConflict': sum(claims_outcome(r, t) not in (side(r), 'NEITHER') for r in fact),
                              'positiveControlsCorrect': sum(claims_outcome(r, t) == side(r) for r in ctrl if side(r)), 'falseOnNegativeControls': sum(claims_outcome(r, t) != 'NEITHER' for r in ctrl if not side(r)),
                              'falseOnWeakUnlabeled': sum(claims_outcome(r, t) != 'NEITHER' for r in weak)},
            'excerptQuestion': {'trueYesFacts': len(ty), 'yesOnTrueYesFacts': sum((r.get('pQuestion') or 0) >= t for r in ty), 'trueNoFacts': len(tn), 'falseYesOnTrueNoFacts': sum((r.get('pQuestion') or 0) >= t for r in tn),
                                'trueYesControls': len(cy), 'yesOnTrueYesControls': sum((r.get('pQuestion') or 0) >= t for r in cy), 'falseYesOnOtherControls': sum((r.get('pQuestion') or 0) >= t for r in cn), 'otherControls': len(cn)},
            'sweepQuestion': {'trueYesFacts': len(sw(ty)), 'firedOnTrueYesFacts': sum(r['sweepMaxP'] >= t for r in sw(ty)), 'trueNoFacts': len(sw(tn)), 'falseFiredOnTrueNoFacts': sum(r['sweepMaxP'] >= t for r in sw(tn)),
                              'trueYesControls': len(sw(cy)), 'firedOnTrueYesControls': sum(r['sweepMaxP'] >= t for r in sw(cy)), 'otherControls': len(sw(cn)), 'falseFiredOnOtherControls': sum(r['sweepMaxP'] >= t for r in sw(cn)),
                              'weakUnlabeled': len(sw(yn(weak))), 'falseFiredOnWeakUnlabeled': sum(r['sweepMaxP'] >= t for r in sw(yn(weak)))}}
    (root/'summary.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))

if __name__ == '__main__': main()
