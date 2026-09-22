"""Held-out (validation-split) view of any benchmark rows file written by laya_bench.py."""
import json, sys
from pathlib import Path
held = set(json.load(open(Path.home()/'.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915/validation-split.json'))['validationCaseIds'])
def side(r): return r['expected'] if r['expected'] in ('A', 'B') else None
for path in sys.argv[1:]:
    rows = [r for r in json.load(open(path)) if r['caseId'] in held]; fact = [r for r in rows if r['kind'] == 'factual']; ctrl = [r for r in rows if r['kind'] == 'control']; weak = [r for r in rows if r['kind'] in ('weak', 'unlabeled')]
    yn = [r for r in fact if r['yesSide']]; ty = [r for r in yn if side(r) == r['yesSide']]; tn = [r for r in yn if side(r) and side(r) != r['yesSide']]
    print(json.dumps({'rows': path.split('/')[-2], 'heldOut': len(rows), 'factual': len(fact), 'choiceCorrect': sum(r.get('pick') == side(r) for r in fact), 'wrongSide': sum(r.get('pick') in ('A', 'B') and r.get('pick') != side(r) for r in fact),
        'negativeControls': sum(not side(r) for r in ctrl), 'falseOnNegativeControls': sum(r.get('pick') in ('A', 'B') for r in ctrl if not side(r)), 'weakUnlabeled': len(weak), 'falseOnWeakUnlabeled': sum(r.get('pick') in ('A', 'B') for r in weak),
        'sweep0.5': {'trueYes': f"{sum(r.get('sweepMaxP', 0) >= 0.5 for r in ty)}/{len(ty)}", 'trueNoFalse': f"{sum(r.get('sweepMaxP', 0) >= 0.5 for r in tn)}/{len(tn)}", 'weakFalse': f"{sum(r.get('sweepMaxP', 0) >= 0.5 for r in weak if r['yesSide'])}/{sum(bool(r['yesSide']) for r in weak)}"},
        'sweep0.9': {'trueYes': f"{sum(r.get('sweepMaxP', 0) >= 0.9 for r in ty)}/{len(ty)}", 'trueNoFalse': f"{sum(r.get('sweepMaxP', 0) >= 0.9 for r in tn)}/{len(tn)}", 'weakFalse': f"{sum(r.get('sweepMaxP', 0) >= 0.9 for r in weak if r['yesSide'])}/{sum(bool(r['yesSide']) for r in weak)}"}}))
