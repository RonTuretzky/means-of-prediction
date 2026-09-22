"""Benchmark a typed-decision model as the verifiable settlement judge: Laya (local) or Jev (hosted).

Same rows, rules and located passages as the Qwen and Fable judge comparisons
(730-row judge-swap subset of the Fable round). Standalone: reads the private
JSON artifacts directly so it can run in Laya's own Python environment.

Backends
  laya  local non-autoregressive encoder (github.com/NandhaKishorM/laya), one process, sequential.
  jev   TypeSafe Jev through OpenRouter's /api/alpha/decisions (same typed-question shape);
        key from ~/.config/means-of-prediction/openrouter.json, never printed or stored in outputs;
        concurrent calls, a hard cumulative cost guard, and retry only on HTTP 429/5xx.

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
import argparse, collections, concurrent.futures, json, os, statistics, threading, time, urllib.error, urllib.request
from pathlib import Path

ROUND = Path.home()/'.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915'
ARM = Path.home()/'.local/share/means-of-prediction/slides/fable-judge-baseline-20260915'
KEYFILE = Path.home()/'.config/means-of-prediction/openrouter.json'
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

class Laya:
    workers = 1
    def __init__(self, checkpoint, device, model_path=None):
        import laya, torch, os
        self.device = device if device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cpu')
        if model_path:
            self.agent = laya.Agent(model_path, device=self.device); self.label = 'laya:'+os.path.basename(model_path.rstrip('/'))
        else:
            self.agent = laya.load('convaiinnovations/laya', device=self.device, **({} if checkpoint == 'english' else {'subfolder': checkpoint})); self.label = 'laya:'+checkpoint
        self.cost = 0.0
    def ask(self, state, questions): return self.agent.predict(state, questions)['answers']

class Jev:
    workers = 8
    def __init__(self, model, max_cost):
        self.key = read(KEYFILE)['apiKey']; self.model = model; self.max_cost = max_cost; self.cost = 0.0; self.lock = threading.Lock(); self.label = 'jev:'+model; self.device = 'hosted (OpenRouter -> TypeSafe)'; self.resolved = None
    def ask(self, state, questions):
        with self.lock:
            if self.cost >= self.max_cost: raise RuntimeError('Cost guard reached; stopping hosted calls')
        body = json.dumps({'model': self.model, 'state': state, 'questions': questions}).encode()
        for attempt in range(6):
            req = urllib.request.Request('https://openrouter.ai/api/alpha/decisions', data=body, headers={'Authorization': 'Bearer '+self.key, 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=90) as resp: out = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 5: time.sleep(2**attempt); continue
                raise RuntimeError('HTTP '+str(exc.code)+': '+exc.read().decode('utf-8', 'replace')[:300])
            except (urllib.error.URLError, TimeoutError):
                if attempt < 5: time.sleep(2**attempt); continue
                raise
            with self.lock: self.cost += float((out.get('usage') or {}).get('cost') or 0); self.resolved = out.get('model') or self.resolved
            return out['answers']
        raise RuntimeError('retries exhausted')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); ap.add_argument('--backend', default='laya', choices=['laya', 'jev'])
    ap.add_argument('--checkpoint', default='english', choices=['english', 'typed-decisions']); ap.add_argument('--model', default='typesafe/jev-1.13'); ap.add_argument('--max-cost', type=float, default=0.85)
    ap.add_argument('--device', default='auto'); ap.add_argument('--window', type=int, default=1200); ap.add_argument('--stride', type=int, default=600); ap.add_argument('--model-path', help='local fine-tuned Laya directory'); a = ap.parse_args()
    backend = Laya(a.checkpoint, a.device, a.model_path) if a.backend == 'laya' else Jev(a.model, a.max_cost)
    root = Path(a.root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    items = {i['caseId']: i for i in read(ROUND/'development-items-semantic.private.json')}
    public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}
    rules = {x['marketId']: x for x in read(ROUND/'methods/baseline/rules.json')}
    located = {x['caseId']: x for x in read(ARM/'judgments.private.json')}
    def binary(p):
        labels = [str(l).strip().lower() for l in p['outcomeLabels']]
        return ('A' if labels[0] == 'yes' else 'B') if sorted(labels) == ['no', 'yes'] else None
    qq = lambda question: {'q': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened, that the answer to this question is yes: '+question+RULE}}

    rows, tasks = {}, []
    for cid in sorted(located):
        item = items[cid]; p = public[item['marketId']]; rule = rules[item['marketId']]; loc = located[cid]
        row = rows[cid] = {'caseId': cid, 'kind': item['kind'], 'expected': item['expected'], 'yesSide': binary(p)}
        text = item['email'].get('completeSemanticText', ''); subject = item['email'].get('subject', '')
        quote = ((loc.get('output') or {}).get('evidenceQuote') or '') if loc['status'] == 'completed' else ''
        cut = excerpt(text, quote) if quote else None; row['hasExcerpt'] = bool(cut)
        if cut and rule['status'] == 'completed':
            claims = {'A': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['output']['factualA'][:600]+RULE},
                      'B': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['output']['factualB'][:600]+RULE},
                      'pick': {'type': 'choice', 'instructions': 'Which statement does the text report as a completed fact?',
                               'criteria': {'A': rule['output']['factualA'][:300], 'B': rule['output']['factualB'][:300], 'neither': 'The text does not report either statement as a completed fact.'}}}
            if row['yesSide']: claims.update(qq(p['question']))
            tasks.append(('excerpt', cid, {'subject': subject, 'body': cut}, claims))
        if row['yesSide']:
            for w in windows(text, a.window, a.stride): tasks.append(('sweep', cid, {'subject': subject, 'body': w}, qq(p['question'])))
    print(json.dumps({'backend': backend.label, 'tasks': len(tasks), 'excerptTasks': sum(t[0] == 'excerpt' for t in tasks)}), flush=True)

    latencies, done, failures = [], [0], []
    def run(task):
        kind, cid, state, questions = task; t = time.time()
        try: ans = backend.ask(state, questions)
        except Exception as exc: return kind, cid, None, str(exc)[:200]
        latencies.append(time.time()-t); return kind, cid, ans, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=backend.workers) as pool:
        for kind, cid, ans, err in pool.map(run, tasks):
            done[0] += 1
            if done[0] % 1000 == 0: print(json.dumps({'done': done[0], 'of': len(tasks), 'costUsd': round(backend.cost, 4), 'failures': len(failures)}), flush=True)
            row = rows[cid]
            if err: failures.append(err); row.setdefault('errors', 0); row['errors'] += 1; continue
            if kind == 'excerpt':
                pick = ans.get('pick', {}); row.update({'pA': ans['A']['noul'], 'pB': ans['B']['noul'], 'pick': pick.get('choice'), 'pickConfidence': pick.get('confidence'), 'pQuestion': ans['q']['noul'] if 'q' in ans else None})
            else:
                row['sweepWindows'] = row.get('sweepWindows', 0)+1; row['sweepMaxP'] = max(row.get('sweepMaxP', 0.0), ans['q']['noul'])
    rows = list(rows.values()); (root/'rows.private.json').write_text(json.dumps(rows))

    def side(r): return r['expected'] if r['expected'] in ('A', 'B') else None
    def claims_outcome(r, t):
        a_, b_ = r.get('pA', 0) >= t, r.get('pB', 0) >= t
        return 'CONFLICT' if a_ and b_ else 'A' if a_ else 'B' if b_ else 'NEITHER'
    out = {'backend': backend.label, 'resolvedModel': getattr(backend, 'resolved', None), 'device': backend.device, 'rows': len(rows), 'rowsWithExcerpt': sum(r['hasExcerpt'] for r in rows), 'calls': len(latencies),
           'failedCalls': len(failures), 'failureSamples': sorted(set(failures))[:3], 'medianMsPerCall': round(1000*statistics.median(latencies), 1) if latencies else None, 'costUsd': round(backend.cost, 4), 'thresholds': {}}
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
