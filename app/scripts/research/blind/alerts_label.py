"""Teacher labels on alert-shaped units paired to resolved markets.

Reads pairs.private.jsonl (from gal_index.py pair) and the Fable rules (rules_batch.py). For every (unit, market) pair asks Jev
the same typed questions the newsletter judge used, on exactly what an alert result shows: headline, publisher label, snippet.
  state   = {subject: headline, body: headline + publisher + snippet}
  A/B     = "Does the text state, as something that has already happened: <factualA|factualB>" (noul)
  q       = the market question as a yes/no completed-fact question (noul)
Markets without a Fable rule yet get only q. Resumable (unitId+marketId), halts on budget errors (the OpenRouter key's own
daily limit is the only cap). Output: labels-alerts.private.jsonl, one record per pair with pA, pB, pQuestion."""
import argparse, concurrent.futures, hashlib, json, os, sys, threading, time
from pathlib import Path
from laya_distill import RULE, Jev

def sha(s): return hashlib.sha256(s.encode()).hexdigest()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pairs', required=True); ap.add_argument('--rules', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--cap', type=int, default=40, help='units per market (highest match score first)'); ap.add_argument('--workers', type=int, default=8); ap.add_argument('--model', default='typesafe/jev-1.13'); ap.add_argument('--max-cost', type=float, default=1000.0); ap.add_argument('--only-with-rule', action='store_true'); a = ap.parse_args()
    os.umask(0o077); rules = {}
    for l in open(a.rules):
        if l.strip(): r = json.loads(l); rules[r['marketId']] = r
    done = set()
    if Path(a.out).exists():
        for l in open(a.out):
            if l.strip(): r = json.loads(l); done.add((r['marketId'], r['unitId']))
    tasks = []
    for l in open(a.pairs):
        p = json.loads(l); rule = rules.get(p['marketId'])
        if a.only_with_rule and not rule: continue
        for u in sorted(p['units'], key=lambda u: -u.get('score', 0))[:a.cap]:
            uid = sha(u['url']+'|'+u['headline'])
            if (p['marketId'], uid) in done: continue
            state = {'subject': u['headline'], 'body': u['headline']+'\n'+(u.get('publisher') or u['host'])+'\n'+(u.get('snippet') or '')}
            qs = {'q': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened, that the answer to this question is yes: '+p['question']+RULE}}
            if rule:
                qs['A'] = {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['factualA'][:600]+RULE}
                qs['B'] = {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['factualB'][:600]+RULE}
            tasks.append({'marketId': p['marketId'], 'unitId': uid, 'host': u['host'], 'seenAt': u['seenAt'], 'closed': p['closed'], 'hasRule': bool(rule), 'state': state, 'qs': qs})
    print(json.dumps({'pairsFile': a.pairs, 'rules': len(rules), 'alreadyDone': len(done), 'tasks': len(tasks)}), flush=True)
    jev = Jev(a.model, a.max_cost); lock = threading.Lock(); n = [0]; fails = [0]; halt = threading.Event(); why = ['']
    def one(t):
        if halt.is_set(): return None
        try: out = jev.ask(t['state'], t['qs'])
        except Exception as exc:
            msg = str(exc)[:200]
            with lock:
                fails[0] += 1
                if 'cost guard' in msg or 'HTTP 40' in msg or fails[0] >= 10: halt.set(); why[0] = msg
            return None
        with lock: fails[0] = 0
        ans = out['answers']; rec = {k: t[k] for k in ('marketId', 'unitId', 'host', 'seenAt', 'closed', 'hasRule')}
        rec.update({'pQuestion': ans['q']['noul'], 'pA': ans['A']['noul'] if 'A' in ans else None, 'pB': ans['B']['noul'] if 'B' in ans else None, 'cost': (out.get('usage') or {}).get('cost')})
        return rec
    with open(a.out, 'a') as f, concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for rec in pool.map(one, tasks):
            if rec is None:
                if halt.is_set(): break
                continue
            f.write(json.dumps(rec)+'\n'); n[0] += 1
            if n[0] % 2000 == 0: f.flush(); print(json.dumps({'labelled': n[0], 'of': len(tasks), 'costUsd': round(jev.cost, 3)}), flush=True)
    print(json.dumps({'labelled': n[0], 'of': len(tasks), 'costUsd': round(jev.cost, 3), 'halted': why[0] or None}), flush=True)
    if halt.is_set(): sys.exit(3)

if __name__ == '__main__': main()
