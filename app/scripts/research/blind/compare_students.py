"""Side-by-side of benchmark rows files on the held-out split: side picked from the per-side heads at several thresholds,
on all held-out rows and on the text-held-out subset (rows whose full email text never appears in a training-split
labelled record). Usage: compare_students.py --labels <labels.private.jsonl> <name>=<rows.private.json> ..."""
import argparse, hashlib, json
from pathlib import Path
ROUND = Path.home()/'.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915'
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def side(r): return r['expected'] if r['expected'] in ('A', 'B') else None
def pick(r, t):
    if 'pA' not in r: return 'neither'
    a, b = r['pA'], r['pB']; return 'neither' if max(a, b) < t else ('A' if a >= b else 'B')
def score(rows, t):
    fact = [r for r in rows if r['kind'] == 'factual']; pc = [r for r in rows if r['kind'] == 'control' and side(r)]; nc = [r for r in rows if r['kind'] == 'control' and not side(r)]; weak = [r for r in rows if r['kind'] in ('weak', 'unlabeled')]
    p = (lambda r: r.get('pickHead', r.get('pick', 'neither'))) if t == 'head' else (lambda r: pick(r, t))
    c = sum(p(r) == side(r) for r in fact); w = sum(p(r) in ('A', 'B') and p(r) != side(r) for r in fact)
    return f"{c:2d}/{w:2d}/{len(fact)-c-w:2d} of {len(fact)} | pos ctrl {sum(p(r) == side(r) for r in pc):2d}/{sum(p(r) in ('A', 'B') and p(r) != side(r) for r in pc):2d} of {len(pc)} | false {sum(p(r) in ('A', 'B') for r in nc):2d}/{len(nc)} neg, {sum(p(r) in ('A', 'B') for r in weak):2d}/{len(weak)} weak"
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--labels', required=True); ap.add_argument('--thresholds', default='head,0.3,0.4,0.5'); ap.add_argument('models', nargs='+'); a = ap.parse_args()
    items = {it['caseId']: it for it in json.load(open(ROUND/'development-items-semantic.private.json'))}; held = set(json.load(open(ROUND/'validation-split.json'))['validationCaseIds'])
    text = lambda cid: sha(items[cid]['email'].get('completeSemanticText', '')) if cid in items else None
    train_texts = {text(json.loads(l)['caseId']) for l in open(a.labels) if l.strip() and '"pA"' in l and '"split": "train"' in l}
    ths = [t if t == 'head' else float(t) for t in a.thresholds.split(',')]
    for spec in a.models:
        name, path = spec.split('=', 1); rows = [r for r in json.load(open(path)) if r['caseId'] in held]; clean = [r for r in rows if text(r['caseId']) not in train_texts]
        print(f"== {name}: {len(rows)} held-out rows, {len(clean)} text-held-out ({sum(r['kind'] == 'factual' for r in clean)} facts)")
        for t in ths:
            print(f"  {str(t):>5} all : facts correct/wrong/abstain {score(rows, t)}")
            print(f"  {str(t):>5} text: facts correct/wrong/abstain {score(clean, t)}")
if __name__ == '__main__': main()
