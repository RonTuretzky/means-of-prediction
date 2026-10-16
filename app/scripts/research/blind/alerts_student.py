"""Alert-shaped student: distil Laya from Jev's labels on (alert result, market) units.

  split        seal the split before anything is trained: markets closed on or after --time-from are the time hold-out
               ("validation-time"); --group-frac of the remaining event groups plus the whole event group of every
               120-market-probe market are "validation"; everything else is "train". Written once to split.json together
               with the sha256 of the sample, pairs and rules files; never rewritten.
  relabel-cut  the teacher judged uncut GDELT text; the student sees Google's cut (headline 110, snippet 162, whole words
               then " ..."). Ask Jev again on the cut text for every positive or near-miss unit whose text is cut (negatives
               stay valid: less text cannot add a stated fact). Resumable; labels-cut.private.jsonl.
  prepare      snapshot the Jev labels (labels.private.jsonl, copied once), apply the cut relabels, join to the unit text
               and the Fable rules, build the Laya sequences (A, B: the rule's predicates; q only with --with-q; no choice)
               with soft targets. Training uses train-market records only, minus: units seen on or after --time-from,
               units whose text also appears under a held-out market, and a --calib-units calibration slice (never trained,
               used to pre-register the threshold). Keeps every teacher positive and near miss (0.2 to 0.5) and --neg-ratio
               random easy negatives per positive. --val-units random units from "validation" markets (never the time
               hold-out) are the in-training validation set. Written once; items carry a market-specific unitId so the
               side-contrast weighting in laya_distill.train stays within one (text, market) unit.
  train        laya_distill.train on the prepared items (same knobs: --init, --positive-weight, --contrast-weight, pacing).
  evaluate     student against the teacher: the pre-registered side threshold is the smallest t with at most
               --max-false-fire false fires on teacher negatives of the calibration slice; held-out metrics by split on
               units never seen in training (in-training validation units and shared text excluded; validation-time counted
               on units seen on or after the cutoff); then the real alert results of the forward run against Jev's
               judgements there. Writes student-labels-*.private.jsonl (alerts_tables.py can read them) and eval-<model>.json.
Private outputs only (umask 077). The forward-run pairs are an evaluation set and never enter training."""
import argparse, collections, concurrent.futures, hashlib, json, os, random, shutil, sys, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import laya_distill as ld
from laya_distill import RULE, gpu_pause

C = Path.home()/'.local/share/means-of-prediction/slides/alerts-corpus-20261003'
RULES = Path.home()/'.local/share/means-of-prediction/slides/alerts-rules-20261003/rules.jsonl'
PROBE = Path.home()/'.local/share/means-of-prediction/slides/alerts-probe-20261002/sample.private.json'
FWD = Path.home()/'.local/share/means-of-prediction/alerts-forward-run-20261007'
FWD_RULES = Path.home()/'.local/share/means-of-prediction/slides/alerts-forward-20261003/rules/rules.jsonl'
HEADLINE_MAX, SNIPPET_MAX = 110, 162
SEAL = (('sampleSha256', C/'sample.private.json'), ('pairsSha256', C/'pairs.private.jsonl'), ('rulesSha256', RULES))

def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def check_seal(sp):
    now = {k: sha_file(p) for k, p in SEAL}
    for k, v in now.items():
        if k in sp and sp[k] != v: raise SystemExit(f'{k}: {dict(SEAL)[k].name} differs from the file sealed in split.json; the corpus was regenerated after the split')
    return now
def cut(s, n):
    """Google's alert shape: whole words then ' ...' (real alerts: 6,208 of 6,212 ellipsis snippets end ' ...', snippet max 161; cut headlines end ' ...' at 81 to 100 chars)."""
    s = (s or '').strip()
    if len(s) <= n: return s
    head = s[:n-4]; sp = head.rfind(' ')
    return (head[:sp] if sp > n//2 else head).rstrip()+' ...'
def was_cut(u, headline_only=False): return len((u.get('headline') or '').strip()) > HEADLINE_MAX or (not headline_only and len((u.get('snippet') or '').strip()) > SNIPPET_MAX)
def unit_state(u, headline_only=False):
    h = cut(u['headline'], HEADLINE_MAX); body = h if headline_only else h+'\n'+(u.get('publisher') or u['host'])+'\n'+cut(u.get('snippet'), SNIPPET_MAX)
    return {'subject': h, 'body': body}
def questions(question, rule):
    qs = {'q': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened, that the answer to this question is yes: '+question+RULE}}
    if rule:
        qs['A'] = {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['factualA'][:600]+RULE}
        qs['B'] = {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['factualB'][:600]+RULE}
    return qs
def load_sample():
    s = json.loads((C/'sample.private.json').read_text()); ms = s if isinstance(s, list) else (s.get('markets') or list(s.values())[0]); return {m['marketId']: m for m in ms}
def load_rules(path=RULES): return {json.loads(l)['marketId']: json.loads(l) for l in open(path) if l.strip()}
def load_units(need):
    """(marketId, unitId) -> unit text, for the keys in need, streamed from the pairs file."""
    units = {}
    for l in open(C/'pairs.private.jsonl'):
        p = json.loads(l)
        for u in p['units']:
            k = (p['marketId'], sha(u['url']+'|'+u['headline']))
            if k in need: units[k] = u
    return units
def load_labels(root):
    recs = [json.loads(l) for l in (root/'labels.private.jsonl').read_text().splitlines() if l.strip()]; recs = [r for r in recs if r.get('pA') is not None]
    cutp = root/'labels-cut.private.jsonl'; n = 0
    if cutp.exists():
        over = {}
        for l in cutp.read_text().splitlines():
            if l.strip(): r = json.loads(l); over[(r['marketId'], r['unitId'])] = r
        for r in recs:
            o = over.get((r['marketId'], r['unitId']))
            if o: r.update({'pA': o['pA'], 'pB': o['pB'], 'pQuestion': o.get('pQuestion'), 'relabelledOnCut': True, 'uncut': {'pA': r['pA'], 'pB': r['pB']}}); n += 1
    return recs, n
def kind_of(r, with_q):
    mx = max(r['pA'], r['pB'], (r.get('pQuestion') or 0.0) if with_q else 0.0); return 'positive' if mx >= 0.5 else 'near' if mx >= 0.2 else 'negative'
def log(**f): print(json.dumps({'at': time.strftime('%H:%M:%S'), **f}, ensure_ascii=False), flush=True)

def split(root, time_from, group_frac, seed):
    root = Path(root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700); out = root/'split.json'
    if out.exists(): print('split.json exists; not rewritten'); return
    meta = load_sample(); probe = json.loads(PROBE.read_text()); probe = probe if isinstance(probe, list) else (probe.get('markets') or list(probe.values())[0]); probe_ids = {str(x['marketId']) for x in probe}
    probe_groups = {m['group'] for mid, m in meta.items() if mid in probe_ids}
    groups = sorted({m['group'] for m in meta.values() if m['closed'] < time_from and m['group'] not in probe_groups}); rnd = random.Random(seed); rnd.shuffle(groups)
    val_groups = set(groups[:int(len(groups)*group_frac)]) | probe_groups
    assign = {mid: 'validation-time' if m['closed'] >= time_from else 'validation' if m['group'] in val_groups else 'train' for mid, m in meta.items()}
    counts = collections.Counter(assign.values()); seal = {k: sha_file(p) for k, p in SEAL}
    out.write_text(json.dumps({'at': time.strftime('%Y-%m-%dT%H:%M%z'), 'timeFrom': time_from, 'groupFrac': group_frac, 'seed': seed, **seal, 'probeMarkets': len(probe_ids & set(meta)), 'probeGroups': len(probe_groups), 'validationGroups': len(val_groups), 'counts': counts, 'markets': assign}, indent=0))
    log(split=counts, validationGroups=len(val_groups), probeGroups=len(probe_groups))

def relabel_cut(root, max_cost, workers, headline_only, with_q):
    root = Path(root); os.umask(0o077); sp = json.loads((root/'split.json').read_text()); assign = sp['markets']; check_seal(sp)
    snap = root/'labels.private.jsonl'
    if not snap.exists(): shutil.copyfile(C/'labels-alerts.private.jsonl', snap)
    recs = [json.loads(l) for l in snap.read_text().splitlines() if l.strip()]; recs = [r for r in recs if r.get('pA') is not None and r['marketId'] in assign]
    todo = [r for r in recs if kind_of(r, True) != 'negative']; units = load_units({(r['marketId'], r['unitId']) for r in todo})
    todo = [r for r in todo if (u := units.get((r['marketId'], r['unitId']))) is not None and was_cut(u, headline_only)]
    out = root/'labels-cut.private.jsonl'; done = set()
    if out.exists():
        for l in out.read_text().splitlines():
            if l.strip(): r = json.loads(l); done.add((r['marketId'], r['unitId']))
    todo = [r for r in todo if (r['marketId'], r['unitId']) not in done]
    meta = load_sample(); rules = load_rules(); jev = ld.Jev('typesafe/jev-1.13', max_cost)
    log(stage='relabel-cut', toRelabel=len(todo), alreadyDone=len(done))
    def one(r):
        u = units[(r['marketId'], r['unitId'])]
        try:
            a = jev.ask(unit_state(u, headline_only), questions(meta[r['marketId']]['question'], rules.get(r['marketId'])))['answers']
            return {'marketId': r['marketId'], 'unitId': r['unitId'], 'pQuestion': a['q']['noul'], 'pA': a['A']['noul'] if 'A' in a else r['pA'], 'pB': a['B']['noul'] if 'B' in a else r['pB'], 'cutHeadline': len(u['headline'].strip()) > HEADLINE_MAX, 'cutSnippet': len((u.get('snippet') or '').strip()) > SNIPPET_MAX}
        except Exception as exc: return {'error': str(exc)[:160]}
    n = fails = 0
    with out.open('a') as f, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for rec in pool.map(one, todo):
            if 'error' in rec:
                fails += 1
                if fails >= 10 or 'HTTP 40' in rec['error']: log(halted=rec['error']); break
                continue
            f.write(json.dumps(rec)+'\n'); n += 1
            if n % 2000 == 0: log(relabelled=n, of=len(todo), costUsd=round(jev.cost, 3))
    log(stage='relabel-cut done', relabelled=n, failures=fails, costUsd=round(jev.cost, 3), resolved=jev.resolved)

def prepare(root, max_len, head_max_len, neg_ratio, val_units, calib_units, seed, headline_only, with_q):
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    from laya.agent import _fix_tokenizer_config
    from laya.common import build_sequence, render_options, QTYPES
    root = Path(root); os.umask(0o077); sp = json.loads((root/'split.json').read_text()); assign = sp['markets']; cutoff = sp['timeFrom'].replace('-', ''); seal = check_seal(sp); rnd = random.Random(seed)
    if (root/'prepare.json').exists(): print('prepare.json exists; not rewritten (a new root is a new experiment)'); return
    snap = root/'labels.private.jsonl'
    if not snap.exists(): shutil.copyfile(C/'labels-alerts.private.jsonl', snap)
    recs, relabelled = load_labels(root); recs = [r for r in recs if r['marketId'] in assign]
    held = [r for r in recs if assign[r['marketId']] != 'train']; held_text = {r['unitId'] for r in held}
    train_all = [r for r in recs if assign[r['marketId']] == 'train']
    train = [r for r in train_all if r['seenAt'][:8] < cutoff]; dropped_after_cutoff = len(train_all)-len(train)
    before = len(train); train = [r for r in train if r['unitId'] not in held_text]; dropped_shared = before-len(train)
    rnd.shuffle(train); calib = train[:calib_units]; calib_text = {r['unitId'] for r in calib}; train = [r for r in train[calib_units:] if r['unitId'] not in calib_text]
    pos = [r for r in train if kind_of(r, with_q) == 'positive']; near = [r for r in train if kind_of(r, with_q) == 'near']; neg = [r for r in train if kind_of(r, with_q) == 'negative']; rnd.shuffle(neg)
    chosen = pos+near+neg[:int(neg_ratio*len(pos))]
    pool = [r for r in held if assign[r['marketId']] == 'validation']; rnd.shuffle(pool); val = pool[:val_units]
    units = load_units({(r['marketId'], r['unitId']) for r in chosen+val}); meta = load_sample(); rules = load_rules()
    model_dir = snapshot_download('convaiinnovations/laya', allow_patterns=['rl_agent_config.json', 'model.safetensors', 'tokenizer/*', 'encoder/*']); _fix_tokenizer_config(model_dir)
    tok = AutoTokenizer.from_pretrained(os.path.join(model_dir, 'tokenizer'))
    items = {'train': [], 'validation': []}; skipped = missing = cut_unrelabelled = 0; lens = []
    for split_name, rs in (('train', chosen), ('validation', val)):
        for r in rs:
            u = units.get((r['marketId'], r['unitId']))
            if u is None: missing += 1; continue
            is_cut = was_cut(u, headline_only)
            if is_cut and not r.get('relabelledOnCut') and kind_of(r, True) != 'negative': cut_unrelabelled += 1; continue  # the teacher judged text the student will not see
            qs = questions(meta[r['marketId']]['question'], rules.get(r['marketId'])); state = unit_state(u, headline_only)
            targets = {'A': [1-r['pA'], r['pA']], 'B': [1-r['pB'], r['pB']]}
            if with_q and r.get('pQuestion') is not None: targets['q'] = [1-r['pQuestion'], r['pQuestion']]
            for qid, target in targets.items():
                if qid not in qs: continue
                q = qs[qid]; seq, markers = build_sequence(tok, state, {'t': q['type'], 'ins': q['instructions'], 'crit': {}}, max_len, head_max_len)
                if len(markers) != len(render_options({'t': q['type'], 'crit': {}})): skipped += 1; continue
                lens.append(len(seq)); items[split_name].append({'ids': seq, 'markers': markers, 'qtype': QTYPES[q['type']], 'target': target, 'label': target.index(max(target)), 'unitId': r['marketId']+':'+r['unitId'], 'alertUnitId': r['unitId'], 'qid': qid, 'marketId': r['marketId'], 'cut': is_cut})
    for s, its in items.items(): torch.save(its, root/(s+'_items.pt'))
    (root/'calibration.private.json').write_text(json.dumps([[r['marketId'], r['unitId']] for r in calib]))
    (root/'val-units.private.json').write_text(json.dumps([[r['marketId'], r['unitId']] for r in val]))
    (root/'train-text.private.json').write_text(json.dumps(sorted({it['alertUnitId'] for it in items['train']})))
    seal_items = sha('\n'.join(sorted(f"{it['unitId']}|{it['qid']}|{s}" for s, its in items.items() for it in its))); lens.sort()
    meta_out = {'train': len(items['train']), 'validation': len(items['validation']), 'skipped': skipped, 'missingUnits': missing, 'maxLen': max_len, 'headMaxLen': head_max_len, 'modelDir': model_dir, 'includeChoice': False, 'itemsSha256': seal_items, 'preparedAt': time.strftime('%Y-%m-%dT%H:%M%z'), 'seed': seed, 'inputSha256': seal,
                'labelsSnapshot': len(recs), 'relabelledOnCut': relabelled, 'timeFrom': sp['timeFrom'], 'trainRecordsDroppedAtOrAfterCutoff': dropped_after_cutoff, 'trainRecordsDroppedSharedWithHeldOut': dropped_shared, 'calibrationUnits': len(calib), 'cutUnrelabelledDropped': cut_unrelabelled,
                'trainUnits': {'positive': len(pos), 'near': len(near), 'negative': min(len(neg), int(neg_ratio*len(pos)))}, 'trainPositiveSequences': sum(it['target'][1] >= 0.5 for it in items['train']), 'heldOutUnits': len(held), 'valUnits': len(val), 'valFromSplit': 'validation', 'headlineOnly': headline_only, 'negRatio': neg_ratio, 'withQ': with_q, 'seqLenMedianP95Max': [lens[len(lens)//2], lens[int(len(lens)*0.95)], lens[-1]] if lens else None}
    (root/'prepare.json').write_text(json.dumps(meta_out, indent=1)); log(**meta_out)

def evaluate(root, model_path, device, max_false_fire, headline_only, forward):
    import laya, torch, numpy as np
    root = Path(root); os.umask(0o077); sp = json.loads((root/'split.json').read_text()); assign = sp['markets']; cutoff = sp['timeFrom'].replace('-', ''); seal = check_seal(sp); meta = load_sample(); rules = load_rules()
    dev = device if device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cpu'); agent = laya.Agent(model_path, device=dev)
    tag = os.path.basename(os.path.dirname(model_path.rstrip('/')))+'-'+os.path.basename(model_path.rstrip('/'))
    recs, _ = load_labels(root); recs = [r for r in recs if r['marketId'] in assign]
    calib = {tuple(k) for k in json.loads((root/'calibration.private.json').read_text())}; val_ids = {tuple(k) for k in json.loads((root/'val-units.private.json').read_text())}; train_text = set(json.loads((root/'train-text.private.json').read_text()))
    train_slice = [r for r in recs if (r['marketId'], r['unitId']) in calib]; held = [r for r in recs if assign[r['marketId']] != 'train']
    units = load_units({(r['marketId'], r['unitId']) for r in held+train_slice})
    def run(rs, out_path):
        rows = []
        with open(out_path, 'w') as f:
            for r in rs:
                u = units.get((r['marketId'], r['unitId']))
                if u is None: continue
                ts = time.time(); a = agent.predict(unit_state(u, headline_only), questions(meta[r['marketId']]['question'], rules.get(r['marketId'])))['answers']; gpu_pause(ts, dev)
                row = {'marketId': r['marketId'], 'unitId': r['unitId'], 'host': r['host'], 'seenAt': r['seenAt'], 'closed': r['closed'], 'split': assign[r['marketId']], 'pQuestion': a['q']['noul'], 'pA': a['A']['noul'] if 'A' in a else None, 'pB': a['B']['noul'] if 'B' in a else None,
                       'teacher': {'pA': r['pA'], 'pB': r['pB'], 'pQuestion': r.get('pQuestion')}, 'cut': was_cut(u, headline_only), 'relabelledOnCut': bool(r.get('relabelledOnCut')), 'inTrainingVal': (r['marketId'], r['unitId']) in val_ids, 'seenInTraining': r['unitId'] in train_text}
                f.write(json.dumps(row)+'\n'); rows.append(row)
        return rows
    t0 = time.time(); tr = run(train_slice, root/f'student-labels-calibration-{tag}.private.jsonl')
    def fires(rows, t): neg = [x for x in rows if x['pA'] is not None and max(x['teacher']['pA'], x['teacher']['pB']) < 0.5]; return round(sum(max(x['pA'], x['pB']) >= t for x in neg)/max(1, len(neg)), 5), len(neg)
    threshold = next((t for t in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8] if fires(tr, t)[0] <= max_false_fire), 0.8)
    hd = run(held, root/f'student-labels-heldout-{tag}.private.jsonl')
    def metrics(rows):
        out = {'units': len(rows)}
        for qid, key in (('A', 'pA'), ('B', 'pB'), ('q', 'pQuestion')):
            sel = [x for x in rows if x[key] is not None and x['teacher'][key] is not None]
            if not sel: continue
            s = np.array([x[key] for x in sel]); t = np.array([x['teacher'][key] for x in sel]); pos = t >= 0.5; auc = None
            if pos.any() and (~pos).any(): order = np.argsort(s); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s)+1); auc = float((ranks[pos].sum()-pos.sum()*(pos.sum()+1)/2)/(pos.sum()*(~pos).sum()))
            out[qid] = {'n': int(len(s)), 'agreementAt0.5': round(float(np.mean((s >= 0.5) == pos)), 4), 'aucVsTeacher': None if auc is None else round(auc, 4), 'teacherPositives': int(pos.sum()), 'recallAt0.5': round(float((s[pos] >= 0.5).mean()), 4) if pos.any() else None, 'recallAtThreshold': round(float((s[pos] >= threshold).mean()), 4) if pos.any() else None, 'falseAt0.5': round(float((s[~pos] >= 0.5).mean()), 5), 'falseAtThreshold': round(float((s[~pos] >= threshold).mean()), 5), 'falseAt0.7': round(float((s[~pos] >= 0.7).mean()), 5)}
        return out
    clean = [x for x in hd if not x['inTrainingVal'] and not x['seenInTraining']]
    out = {'model': model_path, 'headlineOnly': headline_only, 'inputSha256': seal, 'preRegisteredThreshold': threshold, 'calibrationFalseFire': fires(tr, threshold), 'calibrationUnits': len(tr),
           'heldOut': metrics(clean), 'bySplit': {'validation': metrics([x for x in clean if x['split'] == 'validation']), 'validation-time': metrics([x for x in clean if x['split'] == 'validation-time' and x['seenAt'][:8] >= cutoff]), 'validation-time-all': metrics([x for x in clean if x['split'] == 'validation-time'])},
           'excludedFromHeldOut': {'inTrainingVal': sum(x['inTrainingVal'] for x in hd), 'seenInTraining': sum(x['seenInTraining'] and not x['inTrainingVal'] for x in hd)}, 'cutUnitsInHeldOut': sum(x['cut'] for x in clean), 'cutRelabelled': sum(x['relabelledOnCut'] for x in clean), 'minutes': round((time.time()-t0)/60, 1)}
    sealp = Path(model_path).parent/'prepare-seal.json'
    if sealp.exists(): out['trainedFromPrepare'] = json.loads(sealp.read_text())
    if forward and (FWD/'pairs.private.json').exists():
        pairs = json.loads((FWD/'pairs.private.json').read_text()); frules = load_rules(FWD_RULES); jev = {}
        for l in open(FWD/'judged-jev.private.jsonl'):
            r = json.loads(l); jev[(r['marketId'], r['unitId'])] = r
        rows = []; seen = set()
        with open(root/f'student-forward-{tag}.private.jsonl', 'w') as f:
            for m in pairs:
                for u in m['units']:
                    k = (m['marketId'], u['unitId'])
                    if k in seen or k not in jev: continue
                    seen.add(k); ts = time.time(); a = agent.predict(unit_state(u, headline_only), questions(m['question'], frules.get(m['marketId'])))['answers']; gpu_pause(ts, dev)
                    row = {'marketId': m['marketId'], 'unitId': u['unitId'], 'host': u['host'], 'pA': a['A']['noul'] if 'A' in a else None, 'pB': a['B']['noul'] if 'B' in a else None, 'pQuestion': a['q']['noul'], 'teacher': {'pA': jev[k]['pA'], 'pB': jev[k]['pB'], 'pQuestion': jev[k].get('pQuestion')}}
                    f.write(json.dumps(row)+'\n'); rows.append(row)
        ts_ = sorted({threshold, 0.5, 0.7})
        out['forwardRealAlerts'] = {**metrics(rows), 'marketsWithAClaim': {str(t): len({x['marketId'] for x in rows if x['pA'] is not None and x['pA'] >= t}) for t in ts_}, 'marketsWithBClaim': {str(t): len({x['marketId'] for x in rows if x['pB'] is not None and x['pB'] >= t}) for t in ts_}, 'note': 'none of these 60 open markets had happened on October 7, so every A claim is a false YES'}
    (root/f'eval-{tag}.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('split'); p.add_argument('--root', required=True); p.add_argument('--time-from', default='2026-08-17'); p.add_argument('--group-frac', type=float, default=0.12); p.add_argument('--seed', type=int, default=7)
    p = sub.add_parser('relabel-cut'); p.add_argument('--root', required=True); p.add_argument('--max-cost', type=float, default=5.0); p.add_argument('--workers', type=int, default=8); p.add_argument('--headline-only', action='store_true'); p.add_argument('--with-q', action='store_true')
    p = sub.add_parser('prepare'); p.add_argument('--root', required=True); p.add_argument('--max-len', type=int, default=320); p.add_argument('--head-max-len', type=int, default=160); p.add_argument('--neg-ratio', type=float, default=2.0); p.add_argument('--val-units', type=int, default=5000); p.add_argument('--calib-units', type=int, default=4000); p.add_argument('--seed', type=int, default=7); p.add_argument('--headline-only', action='store_true'); p.add_argument('--with-q', action='store_true', help='also train the market-question (q) sequences; off by default, settlement uses the A/B predicates')
    p = sub.add_parser('train'); p.add_argument('--root', required=True); p.add_argument('--out', required=True); p.add_argument('--epochs', type=int, default=2); p.add_argument('--micro-batch', type=int, default=32); p.add_argument('--grad-accum', type=int, default=1); p.add_argument('--lr-encoder', type=float, default=2.5e-5); p.add_argument('--lr-head', type=float, default=1e-4)
    p.add_argument('--group-size', type=int, default=4); p.add_argument('--device', default='auto'); p.add_argument('--max-steps', type=int, default=0); p.add_argument('--seed', type=int, default=0); p.add_argument('--positive-weight', type=float, default=2.0); p.add_argument('--contrast-weight', type=float, default=4.0); p.add_argument('--init'); p.add_argument('--start-epoch', type=int, default=0); p.add_argument('--gpu-share', type=ld.share_arg, default=ld.GPU_SHARE); p.add_argument('--no-grad-checkpoint', action='store_true'); p.add_argument('--resume-every', type=int, default=250)
    p = sub.add_parser('evaluate'); p.add_argument('--root', required=True); p.add_argument('--model-path', required=True); p.add_argument('--device', default='auto'); p.add_argument('--max-false-fire', type=float, default=0.005); p.add_argument('--headline-only', action='store_true'); p.add_argument('--no-forward', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'split': split(a.root, a.time_from, a.group_frac, a.seed)
    elif a.cmd == 'relabel-cut': relabel_cut(a.root, a.max_cost, a.workers, a.headline_only, a.with_q)
    elif a.cmd == 'prepare': prepare(a.root, a.max_len, a.head_max_len, a.neg_ratio, a.val_units, a.calib_units, a.seed, a.headline_only, a.with_q)
    elif a.cmd == 'train':
        os.umask(0o077); Path(a.out).mkdir(parents=True, exist_ok=True); pm = json.loads((Path(a.root)/'prepare.json').read_text())
        (Path(a.out)/'prepare-seal.json').write_text(json.dumps({k: pm.get(k) for k in ('itemsSha256', 'preparedAt', 'negRatio', 'withQ', 'headlineOnly', 'seed', 'inputSha256')}))
        ld.train(a.root, a.out, a.epochs, a.micro_batch, a.grad_accum, a.lr_encoder, a.lr_head, a.group_size, a.device, a.max_steps, a.seed, a.positive_weight, True, a.init, a.start_epoch, a.gpu_share, not a.no_grad_checkpoint, a.contrast_weight, a.resume_every)
    else: evaluate(a.root, a.model_path, a.device, a.max_false_fire, a.headline_only, not a.no_forward)
