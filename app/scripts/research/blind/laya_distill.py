"""Distil Jev into Laya for the settlement-judge task: does this passage report claim X as a completed fact?

Stages (each write-once under --root, private):
  label     Build (window, market) units from the development items; ask Jev (OpenRouter
            decisions endpoint) the same typed questions the benchmark uses; store every
            probability. Cost-guarded; concurrent; retry only on 429/5xx.
  prepare   Tokenize units into Laya training sequences with Jev's soft targets. Rows whose
            market is in the round's validation split are held out (never trained on).
  train     Fine-tune the Laya English checkpoint on one device (MPS/CUDA/CPU) with the
            recipe from Laya's own notebook (proper-scoring RL term + soft cross-entropy),
            single process, rolling checkpoints, temperature refit on train items.
  evaluate  Student vs Jev on held-out units (Brier, agreement, AUC) and, through
            laya_bench.py --model-path, vs the human labels on the 730-row subset.

Teacher probabilities are targets, not truth: the human-labelled rows remain the yardstick.
"""
import argparse, collections, concurrent.futures, hashlib, json, math, os, random, re, statistics, threading, time, urllib.error, urllib.request
from pathlib import Path

ROUND = Path.home()/'.local/share/means-of-prediction/slides/fable-qwen-nyt-round1-20260915'
ARM = Path.home()/'.local/share/means-of-prediction/slides/fable-judge-baseline-20260915'
KEYFILE = Path.home()/'.config/means-of-prediction/openrouter.json'
RULE = ' Forecasts, odds, plans, hypotheticals, denials and quoted predictions do not count.'
WINDOW, STRIDE = 1200, 600

def read(p): return json.loads(Path(p).read_text())
def share_arg(v): return v if v == 'auto' else float(v)
GPU_SHARE = share_arg(os.environ.get('MOP_GPU_SHARE', '1'))  # fraction of wall time this process may keep the GPU busy; below 1 it sleeps between steps so the display and other apps stay responsive; 'auto' = MOP_GPU_ACTIVE_SHARE while someone is using the machine, full speed once input has been idle MOP_GPU_IDLE_SECS or the display is off
ACTIVE_SHARE, IDLE_SECS = float(os.environ.get('MOP_GPU_ACTIVE_SHARE', '0.3')), float(os.environ.get('MOP_GPU_IDLE_SECS', '180'))
_pace = {'checked': 0.0, 'share': None, 'why': None}
def user_present():
    # macOS only: seconds since the last keyboard/mouse/trackpad event (a sleeping display implies a long idle). Any failure counts as present (pace conservatively).
    import subprocess
    try:
        out = subprocess.run(['ioreg', '-c', 'IOHIDSystem', '-d', '4'], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r'"HIDIdleTime" = (\d+)', out); idle = int(m.group(1))/1e9 if m else 0.0
        return idle < IDLE_SECS, f'input idle {idle:.0f}s'
    except Exception as exc: return True, f'probe failed: {exc}'
def current_share(share):
    if share != 'auto': return share
    now = time.time()
    if now-_pace['checked'] >= 2:  # a returning user gets the paced GPU back within about two seconds; the probe costs ~30 ms
        present, why = user_present(); new = ACTIVE_SHARE if present else 1.0; _pace['checked'] = now
        if new != _pace['share']: print(json.dumps({'at': time.strftime('%H:%M:%S'), 'gpuShare': new, 'because': why}), flush=True)
        _pace['share'], _pace['why'] = new, why
    return _pace['share']
def gpu_pause(t_start, device, share=None):
    if device in ('mps', 'cuda') and (GPU_SHARE if share is None else share) != 1:
        import torch; (torch.mps if device == 'mps' else torch.cuda).synchronize()
    busy = min(time.time()-t_start, 5.0); share = current_share(GPU_SHARE if share is None else share)  # measured before the presence probe; capped because wall time spanning a system sleep is not GPU time (uncapped, one clamshell sleep produced a two-hour pause on September 24)
    if share < 1: time.sleep(busy*(1-share)/share)
def sha(s): return hashlib.sha256(s.encode()).hexdigest()

def windows(text):
    if len(text) <= WINDOW: return [(0, text)]
    return [(i, text[i:i+WINDOW]) for i in range(0, max(1, len(text)-WINDOW+STRIDE), STRIDE)]

def entities(question):
    return {w for w in re.findall(r"\b[A-Z][a-zA-Z'’-]{2,}\b", question) if w not in {'Will', 'The', 'Yes', 'No', 'This', 'That', 'What', 'Who', 'When', 'Does', 'And', 'Before', 'After', 'Exact', 'Score'}}

def binary(p):
    labels = [str(l).strip().lower() for l in p['outcomeLabels']]
    return ('A' if labels[0] == 'yes' else 'B') if sorted(labels) == ['no', 'yes'] else None

def questions_for(p, rule):
    """Same typed questions as laya_bench: three noul checks and one choice."""
    q = {'A': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['factualA'][:600]+RULE},
         'B': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened: '+rule['factualB'][:600]+RULE},
         'pick': {'type': 'choice', 'instructions': 'Which statement does the text report as a completed fact?',
                  'criteria': {'A': rule['factualA'][:300], 'B': rule['factualB'][:300], 'neither': 'The text does not report either statement as a completed fact.'}}}
    if binary(p): q['q'] = {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened, that the answer to this question is yes: '+p['question']+RULE}
    return q

# ---------------------------------------------------------------- label
class Jev:
    def __init__(self, model, max_cost):
        self.key = read(KEYFILE)['apiKey']; self.model = model; self.max_cost = max_cost; self.cost = 0.0; self.lock = threading.Lock(); self.calls = 0
    def ask(self, state, questions):
        with self.lock:
            if self.cost >= self.max_cost: raise RuntimeError('cost guard')
        body = json.dumps({'model': self.model, 'state': state, 'questions': questions}).encode()
        for attempt in range(6):
            req = urllib.request.Request('https://openrouter.ai/api/alpha/decisions', data=body, headers={'Authorization': 'Bearer '+self.key, 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=90) as resp: out = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 5: time.sleep(2**attempt); continue
                raise RuntimeError('HTTP %d: %s' % (exc.code, exc.read().decode('utf-8', 'replace')[:200]))
            except (urllib.error.URLError, TimeoutError):
                if attempt < 5: time.sleep(2**attempt); continue
                raise
            with self.lock: self.cost += float((out.get('usage') or {}).get('cost') or 0); self.calls += 1
            return out
        raise RuntimeError('retries exhausted')

def build_units(max_windows, cross_negatives, seed):
    """(window, market) units: every item's own market on a capped set of its email's windows, plus cross-market negatives."""
    rng = random.Random(seed)
    items = read(ROUND/'development-items-semantic.private.json'); public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}
    rules = {x['marketId']: x['output'] for x in read(ROUND/'methods/baseline/rules.json') if x['status'] == 'completed'}
    held_markets = set(read(ROUND/'validation-split.json')['validationMarketIds']); held_cases = set(read(ROUND/'validation-split.json')['validationCaseIds'])
    located = {x['caseId']: ((x.get('output') or {}).get('evidenceQuote') or '') for x in read(ARM/'judgments.private.json') if x['status'] == 'completed'}
    units, by_email = [], collections.defaultdict(list)
    for it in items:
        if it['marketId'] not in rules: continue
        text = it['email'].get('completeSemanticText', ''); subject = it['email'].get('subject', ''); ws = windows(text)
        ents = entities(public[it['marketId']]['question']); quote = located.get(it['caseId'], '')
        def score(w):
            off, body = w; s = 0
            if quote and quote in body: s += 100
            s += sum(e in body for e in ents); return s + rng.random()
        chosen = sorted(ws, key=score, reverse=True)[:max_windows] if len(ws) > max_windows else ws
        by_email[sha(text)].append(it)
        for off, body in chosen:
            units.append({'unitId': sha(it['caseId']+':'+str(off)), 'caseId': it['caseId'], 'marketId': it['marketId'], 'kind': it['kind'], 'expected': it['expected'], 'yesSide': binary(public[it['marketId']]),
                          'split': 'validation' if (it['caseId'] in held_cases or it['marketId'] in held_markets) else 'train', 'offset': off, 'state': {'subject': subject, 'body': body}, 'source': 'own-market'})
    # Cross-market negatives: real (non-control) email windows paired with unrelated train-split markets.
    real = [it for it in items if it['kind'] != 'control' and it['marketId'] in rules]; train_markets = [m for m in rules if m not in held_markets]
    seen = set()
    for it in real:
        text = it['email'].get('completeSemanticText', ''); key = sha(text)
        if key in seen: continue
        seen.add(key); ws = windows(text)
        for _ in range(cross_negatives):
            off, body = rng.choice(ws); m = rng.choice(train_markets)
            if any(x['marketId'] == m for x in by_email[key]): continue
            units.append({'unitId': sha('x:'+it['caseId']+':'+m+':'+str(off)), 'caseId': it['caseId'], 'marketId': m, 'kind': 'cross', 'expected': None, 'yesSide': binary(public[m]),
                          'split': 'train', 'offset': off, 'state': {'subject': it['email'].get('subject', ''), 'body': body}, 'source': 'cross-market'})
    return units, public, rules

def label(root, model, max_cost, max_windows, cross_negatives, workers, seed):
    root = Path(root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    out_path = root/'labels.private.jsonl'; done = set()
    # Only successfully labelled units count as done; error receipts are retried on relaunch.
    if out_path.exists(): done = {r['unitId'] for r in (json.loads(l) for l in out_path.read_text().splitlines() if l.strip()) if 'pA' in r}
    units, public, rules = build_units(max_windows, cross_negatives, seed)
    todo = [u for u in units if u['unitId'] not in done]
    (root/'plan.json').write_text(json.dumps({'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'teacher': model, 'units': len(units), 'alreadyLabelled': len(done), 'maxWindowsPerItem': max_windows, 'crossNegativesPerEmail': cross_negatives,
                                             'bySplit': dict(collections.Counter(u['split'] for u in units)), 'bySource': dict(collections.Counter(u['source'] for u in units)), 'byKind': dict(collections.Counter(u['kind'] for u in units)), 'window': WINDOW, 'stride': STRIDE, 'seed': seed}, indent=1))
    print(json.dumps({'units': len(units), 'todo': len(todo), 'bySplit': dict(collections.Counter(u['split'] for u in units))}), flush=True)
    label_units(out_path, todo, public, rules, model, max_cost, workers)

def label_units(out_path, todo, public, rules, model, max_cost, workers):
    """Ask the teacher the typed questions for each unit; append one record per unit (error receipts included, retried on relaunch)."""
    jev = Jev(model, max_cost); lock = threading.Lock(); n = [0]; ok = [0]; fails = [0]; halt = threading.Event(); why = ['']
    def one(u):
        if halt.is_set(): return None
        qs = questions_for(public[u['marketId']], rules[u['marketId']])
        try: out = jev.ask(u['state'], qs)
        except Exception as exc:
            msg = str(exc)[:200]
            with lock: fails[0] += 1
            if 'cost guard' in msg or re.match(r'HTTP 4(0\d|[1-9]\d)', msg) or fails[0] >= 10: halt.set(); why[0] = msg  # budget, credit or key problem (any non-retried 4xx) or a failure streak: stop instead of writing a receipt per unit
            return {**u, 'error': msg}
        with lock: fails[0] = 0
        a = out['answers']; rec = {k: v for k, v in u.items()}
        rec.update({'pA': a['A']['noul'], 'pB': a['B']['noul'], 'pQuestion': a['q']['noul'] if 'q' in a else None, 'pick': a['pick']['probabilities'], 'teacherModel': out.get('model'), 'cost': (out.get('usage') or {}).get('cost')})
        return rec
    with Path(out_path).open('a') as f, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for rec in pool.map(one, todo):
            if rec is None: continue
            with lock:
                f.write(json.dumps(rec, ensure_ascii=False)+'\n'); f.flush(); n[0] += 1; ok[0] += 'pA' in rec
                if n[0] % 500 == 0: print(json.dumps({'labelled': ok[0], 'attempted': n[0], 'of': len(todo), 'costUsd': round(jev.cost, 4)}), flush=True)
    print(json.dumps({'labelled': ok[0], 'attempted': n[0], 'of': len(todo), 'costUsd': round(jev.cost, 4), 'calls': jev.calls, 'halted': why[0] or None}), flush=True)
    return ok[0]

# ---------------------------------------------------------------- label-active
def label_active(root, student, device, min_score, own_min_score, max_new, max_candidates, model, max_cost, workers, seed, dry_run):
    """Student-proposed, teacher-labelled units. The current student scores candidate (window, market) units it has not
    seen labelled; the ones it finds suggestive (max side probability >= min_score) go to Jev. Only training-split markets
    and non-validation cases, so the held-out benchmark stays clean. Cross-market candidates need an entity of the
    market's question in the window. Candidates and scores are written for audit before any teacher call."""
    import torch, laya
    root = Path(root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700); rng = random.Random(seed)
    items = read(ROUND/'development-items-semantic.private.json'); public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}
    rules = {x['marketId']: x['output'] for x in read(ROUND/'methods/baseline/rules.json') if x['status'] == 'completed'}
    vs = read(ROUND/'validation-split.json'); held_markets = set(vs['validationMarketIds']); held_cases = set(vs['validationCaseIds'])
    out_path = root/'labels.private.jsonl'; scores_path = root/'active-scores.private.jsonl'; chosen_path = root/'active-chosen.private.json'
    labelled = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()] if out_path.exists() else []
    done = {r['unitId'] for r in labelled if 'pA' in r}; done_content = {(sha(r['state']['body']), r['marketId']) for r in labelled if 'pA' in r}  # same window text + market under any unitId counts as labelled
    if chosen_path.exists():
        # A previous invocation already picked its units: finish that selection rather than re-scoring and re-selecting.
        chosen = [c for c in read(chosen_path)['units'] if c['unitId'] not in done]
        print(json.dumps({'resumingSelection': str(chosen_path), 'remaining': len(chosen)}), flush=True)
        if dry_run or not chosen: return
        return label_units(out_path, chosen, public, rules, model, max_cost, workers)
    train_markets = [m for m in rules if m not in held_markets]; ents = {m: entities(public[m]['question']) for m in train_markets}
    # Email texts that carry any validation case are excluded outright, so the student cannot select more windows of the exact bodies behind held-out rows.
    held_texts = {sha(it['email'].get('completeSemanticText', '')) for it in items if it['caseId'] in held_cases}
    cands, seen_content = [], set()
    def add(c):
        ck = (sha(c['state']['body']), c['marketId'])
        if c['unitId'] in done or ck in done_content or ck in seen_content: return
        seen_content.add(ck); cands.append(c)
    usable = [it for it in items if it['marketId'] in rules and it['caseId'] not in held_cases and sha(it['email'].get('completeSemanticText', '')) not in held_texts]
    markets_of_text = collections.defaultdict(set)
    for it in usable: markets_of_text[sha(it['email'].get('completeSemanticText', ''))].add(it['marketId'])
    for it in usable:  # own-market windows first, so a window never gets recorded under another item's cross pairing
        if it['marketId'] in held_markets: continue
        text = it['email'].get('completeSemanticText', ''); subject = it['email'].get('subject', '')
        for off, body in windows(text):
            add({'unitId': sha(it['caseId']+':'+str(off)), 'caseId': it['caseId'], 'marketId': it['marketId'], 'kind': it['kind'], 'expected': it['expected'], 'yesSide': binary(public[it['marketId']]), 'split': 'train', 'offset': off, 'state': {'subject': subject, 'body': body}, 'source': 'active-own', 'hits': 0})
    seen_email = set()
    for it in usable:  # cross-market windows: one pass per distinct real email, never a market that email is itself attached to
        text = it['email'].get('completeSemanticText', ''); subject = it['email'].get('subject', ''); key = sha(text)
        if it['kind'] == 'control' or key in seen_email: continue
        seen_email.add(key); ws = windows(text)
        for m in train_markets:
            if m in markets_of_text[key] or not ents[m]: continue
            for off, body in ws:
                hits = sum(e in body for e in ents[m])
                if hits: add({'unitId': sha('x:'+it['caseId']+':'+m+':'+str(off)), 'caseId': it['caseId'], 'marketId': m, 'kind': 'cross', 'expected': None, 'yesSide': binary(public[m]), 'split': 'train', 'offset': off, 'state': {'subject': subject, 'body': body}, 'source': 'active-cross', 'hits': hits})
    counts = dict(collections.Counter(c['source'] for c in cands))
    if len(cands) > max_candidates:  # keep every own-market window; cross-market windows by entity hits, ties random
        own = [c for c in cands if c['source'] == 'active-own']; cross = [c for c in cands if c['source'] == 'active-cross']; rng.shuffle(cross)
        cands = own+sorted(cross, key=lambda c: -c['hits'])[:max(0, max_candidates-len(own))]
    prior = {}
    if scores_path.exists(): prior = {r['unitId']: r for r in (json.loads(l) for l in scores_path.read_text().splitlines() if l.strip()) if r.get('student') == student}  # a different student must re-score
    dev = device if device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cpu'); agent = laya.Agent(student, device=dev)
    print(json.dumps({'candidates': counts, 'scoring': len(cands), 'alreadyScored': sum(c['unitId'] in prior for c in cands), 'alreadyLabelled': len(done), 'student': student}), flush=True); t0 = time.time(); scored = 0
    with scores_path.open('a') as sf:
        for c in cands:
            if c['unitId'] in prior: c.update({k: prior[c['unitId']][k] for k in ('studentA', 'studentB', 'studentQ', 'studentScore')}); continue
            qs = {k: v for k, v in questions_for(public[c['marketId']], rules[c['marketId']]).items() if k != 'pick'}
            ts = time.time(); ans = agent.predict(c['state'], qs)['answers']; gpu_pause(ts, dev)
            c['studentA'], c['studentB'] = ans['A']['noul'], ans['B']['noul']; c['studentQ'] = ans['q']['noul'] if 'q' in ans else None; c['studentScore'] = max(c['studentA'], c['studentB'])
            sf.write(json.dumps({**c, 'student': student}, ensure_ascii=False)+'\n'); sf.flush(); scored += 1  # scores persist, so a relaunch never repeats a forward pass
            if scored % 1000 == 0: print(json.dumps({'scored': scored, 'of': len(cands), 'secondsPerUnit': round((time.time()-t0)/scored, 3)}), flush=True)
    # Own-market windows are where teacher positives live, so they get a lower bar and go first; cross-market windows (mostly hard negatives) fill the rest by score.
    own = sorted([c for c in cands if c['source'] == 'active-own' and c['studentScore'] >= own_min_score], key=lambda c: -c['studentScore'])
    cross = sorted([c for c in cands if c['source'] == 'active-cross' and c['studentScore'] >= min_score], key=lambda c: -c['studentScore'])
    chosen = [{k: v for k, v in c.items() if k != 'hits'} for c in (own+cross)[:max_new]]
    audit = {'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'student': student, 'candidates': counts, 'scored': len(cands), 'minScore': min_score, 'ownMinScore': own_min_score, 'maxNew': max_new, 'chosen': len(chosen),
             'chosenBySource': dict(collections.Counter(c['source'] for c in chosen)), 'chosenByKind': dict(collections.Counter(c['kind'] for c in chosen)),
             'scoreQuantiles': {q: round(sorted(c['studentScore'] for c in cands)[int(q*(len(cands)-1))], 3) for q in (0.5, 0.9, 0.99)} if cands else {}}
    print(json.dumps(audit), flush=True)
    if dry_run: (root/'active-candidates.private.json').write_text(json.dumps({**audit, 'dryRun': True}, indent=1)); return
    chosen_path.write_text(json.dumps({**audit, 'units': chosen}))  # the selection is fixed once; relaunches finish it
    return label_units(out_path, chosen, public, rules, model, max_cost, workers)

# ---------------------------------------------------------------- label-augment
def label_augment(root, crops, contrast, embeds, min_len, max_len, model, max_cost, workers, seed, dry_run):
    """More positive contexts for the same facts. For every teacher-positive training unit (own-market, non-held email text) cut `crops`
    random windows of min_len..max_len characters that still contain the located evidence quote (or, without a usable quote, the
    original window's centre), plus `contrast` windows from the same email that exclude the quote. Short positives (the synthetic
    control passages, median 260 characters, 407 of the 438 usable positives on September 25) cannot be cropped; instead each is
    embedded `embeds` times inside filler taken from teacher-negative windows of real newsletters, at a random position, so the
    student sees the same fact surrounded by unrelated newsletter text. The teacher labels every unit, so crops or embeddings
    that lose the fact become negatives. Content-deduped against everything already labelled."""
    root = Path(root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700); rng = random.Random(seed)
    items = {it['caseId']: it for it in read(ROUND/'development-items-semantic.private.json')}; public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}
    rules = {x['marketId']: x['output'] for x in read(ROUND/'methods/baseline/rules.json') if x['status'] == 'completed'}
    vs = read(ROUND/'validation-split.json'); held_cases = set(vs['validationCaseIds'])
    held_texts = {sha(it['email'].get('completeSemanticText', '')) for it in items.values() if it['caseId'] in held_cases}
    located = {x['caseId']: ((x.get('output') or {}).get('evidenceQuote') or '') for x in read(ARM/'judgments.private.json') if x['status'] == 'completed'}
    out_path = root/'labels.private.jsonl'; chosen_path = root/'augment-chosen.private.json'
    labelled = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()] if out_path.exists() else []
    done = {r['unitId'] for r in labelled if 'pA' in r}; done_content = {(sha(r['state']['body']), r['marketId']) for r in labelled if 'pA' in r}
    if chosen_path.exists():
        chosen = [c for c in read(chosen_path)['units'] if c['unitId'] not in done]
        print(json.dumps({'resumingSelection': str(chosen_path), 'remaining': len(chosen)}), flush=True)
        if dry_run or not chosen: return
        return label_units(out_path, chosen, public, rules, model, max_cost, workers)
    positives = [r for r in labelled if 'pA' in r and r['split'] == 'train' and r['source'] in ('own-market', 'active-own') and max(r['pA'], r['pB']) >= 0.5
                 and r['caseId'] in items and r['caseId'] not in held_cases and sha(items[r['caseId']]['email'].get('completeSemanticText', '')) not in held_texts and r['marketId'] in rules]
    units, seen, stats = [], set(), collections.Counter()
    filler = [r for r in labelled if 'pA' in r and r['split'] == 'train' and r['source'] == 'own-market' and max(r['pA'], r['pB']) < 0.2 and items.get(r['caseId'], {}).get('kind') != 'control'
              and len(r['state']['body']) >= 600 and sha(items[r['caseId']]['email'].get('completeSemanticText', '')) not in held_texts]
    def emit(kind, r, body, subject, start, anchored, extra=None):
        it = items[r['caseId']]; ck = (sha(body), r['marketId'])
        if len(body) < min_len or ck in done_content or ck in seen: stats['skippedDupOrShort'] += 1; return
        seen.add(ck); stats[kind] += 1
        units.append({'unitId': sha('aug:'+kind+':'+r['caseId']+':'+r['marketId']+':'+str(start)+':'+str(len(body))+':'+sha(body)[:8]), 'caseId': r['caseId'], 'marketId': r['marketId'], 'kind': it['kind'], 'expected': it['expected'], 'yesSide': r.get('yesSide'),
                      'split': 'train', 'offset': start, 'state': {'subject': subject, 'body': body}, 'source': 'augment-'+kind, 'parentUnitId': r['unitId'], 'anchored': anchored, **(extra or {})})
    def add(kind, r, start, length, anchored):
        it = items[r['caseId']]; text = it['email'].get('completeSemanticText', ''); emit(kind, r, text[start:start+length], it['email'].get('subject', ''), start, anchored)
    def embed(r):
        # the whole short positive text, dropped at a random position inside filler cut from one or two teacher-negative real newsletter windows
        it = items[r['caseId']]; core = it['email'].get('completeSemanticText', '').strip()
        if not core or not filler: return
        L = rng.randint(max(min_len, len(core)+200), max_len); budget = L-len(core)-2; before = rng.randint(0, budget); after = budget-before
        fa, fb = rng.choice(filler), rng.choice(filler); pre = fa['state']['body'][-before:] if before else ''; post = fb['state']['body'][:after] if after else ''
        body = (pre+'\n'+core+'\n'+post).strip()
        emit('embed', r, body, fa['state']['subject'], body.find(core), True, {'fillerUnitIds': [fa['unitId'], fb['unitId']], 'coreLength': len(core)})
    for r in positives:
        it = items[r['caseId']]; text = it['email'].get('completeSemanticText', ''); n = len(text); off = r['offset']
        if n < min_len+200:
            for _ in range(embeds): embed(r)
            continue
        quote = located.get(r['caseId'], ''); qs = text.find(quote) if quote and len(quote) >= 20 else -1
        if qs >= 0 and off <= qs < off+WINDOW: qe = qs+len(quote); anchored = True
        else: qs = qe = min(n, off+WINDOW//2); anchored = False  # no usable quote inside this window: keep the window's centre
        for _ in range(crops):
            L = rng.randint(min_len, max_len); lo = max(0, qe-L); hi = min(qs, max(0, n-L))
            if hi < lo: continue
            add('crop', r, rng.randint(lo, hi), L, anchored)
        for _ in range(contrast):
            L = rng.randint(min_len, max_len); side = rng.choice(['before', 'after'])
            start = rng.randint(0, max(0, qs-L)) if side == 'before' and qs-L > 0 else (rng.randint(qe, max(qe, n-L)) if n-L > qe else None)
            if start is None: continue
            add('contrast', r, start, L, anchored)
    audit = {'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'positiveParents': len(positives), 'anchoredParents': len({u['parentUnitId'] for u in units if u['source'] != 'augment-embed' and u['anchored']}), 'embeddedParents': len({u['parentUnitId'] for u in units if u['source'] == 'augment-embed'}), 'units': len(units), 'bySource': dict(collections.Counter(u['source'] for u in units)), 'counts': dict(stats.most_common()), 'fillerWindows': len(filler), 'crops': crops, 'contrast': contrast, 'embeds': embeds, 'lengths': [min_len, max_len]}
    print(json.dumps(audit), flush=True)
    if dry_run: (root/'augment-candidates.private.json').write_text(json.dumps({**audit, 'dryRun': True}, indent=1)); return
    chosen_path.write_text(json.dumps({**audit, 'units': units}))
    return label_units(out_path, units, public, rules, model, max_cost, workers)

# ---------------------------------------------------------------- prepare
def prepare(root, max_len, head_max_len, include_choice, active_min_score=0.0):
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    from laya.agent import _fix_tokenizer_config
    from laya.common import build_sequence, render_options, QTYPES
    root = Path(root); model_dir = snapshot_download('convaiinnovations/laya', allow_patterns=['rl_agent_config.json', 'model.safetensors', 'tokenizer/*', 'encoder/*']); _fix_tokenizer_config(model_dir)
    tok = AutoTokenizer.from_pretrained(os.path.join(model_dir, 'tokenizer'))
    public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}; rules = {x['marketId']: x['output'] for x in read(ROUND/'methods/baseline/rules.json') if x['status'] == 'completed'}
    recs = [json.loads(l) for l in (root/'labels.private.jsonl').read_text().splitlines() if l.strip()]; recs = [r for r in recs if 'pA' in r]
    # Student-proposed units: keep every teacher positive, but only the hard negatives (student side score at or above active_min_score), so the
    # class balance is not swamped by thousands of easy negatives (10,000 active units on September 25 held 40 teacher positives).
    before = len(recs); recs = [r for r in recs if not r.get('source', '').startswith('active-') or max(r['pA'], r['pB']) >= 0.5 or r.get('studentScore', 1.0) >= active_min_score]
    dropped_easy = before-len(recs)
    items = {'train': [], 'validation': []}; skipped = 0
    for r in recs:
        qs = questions_for(public[r['marketId']], rules[r['marketId']])
        targets = {'A': [1-r['pA'], r['pA']], 'B': [1-r['pB'], r['pB']]}
        if r.get('pQuestion') is not None: targets['q'] = [1-r['pQuestion'], r['pQuestion']]
        if include_choice: targets['pick'] = [r['pick'].get(k, 0.0) for k in qs['pick']['criteria']]
        for qid, target in targets.items():
            q = qs[qid]; s = sum(target); target = [v/s for v in target] if s > 0 else [1/len(target)]*len(target)
            seq, markers = build_sequence(tok, r['state'], {'t': q['type'], 'ins': q['instructions'], 'crit': q.get('criteria', {})}, max_len, head_max_len)
            if len(markers) != len(render_options({'t': q['type'], 'crit': q.get('criteria', {})})): skipped += 1; continue
            items[r['split']].append({'ids': seq, 'markers': markers, 'qtype': QTYPES[q['type']], 'target': target, 'label': target.index(max(target)), 'unitId': r['unitId'], 'qid': qid})
    for split, its in items.items(): torch.save(its, root/(split+'_items.pt'))
    print(json.dumps({'droppedEasyActiveNegatives': dropped_easy, 'activeMinScore': active_min_score}), flush=True)
    meta = {'train': len(items['train']), 'validation': len(items['validation']), 'skipped': skipped, 'maxLen': max_len, 'headMaxLen': head_max_len, 'modelDir': model_dir, 'includeChoice': include_choice}
    (root/'prepare.json').write_text(json.dumps(meta, indent=1)); print(json.dumps(meta), flush=True)

# ---------------------------------------------------------------- train
def collate(items, pad_id):
    import torch
    n, L = len(items), max(len(it['ids']) for it in items); kmax = max(len(it['markers']) for it in items)
    ids = torch.full((n, L), pad_id, dtype=torch.long); att = torch.zeros((n, L), dtype=torch.long); mpos = torch.zeros((n, kmax), dtype=torch.long); mmask = torch.zeros((n, kmax), dtype=torch.bool); target = torch.zeros((n, kmax))
    for i, it in enumerate(items):
        ids[i, :len(it['ids'])] = torch.tensor(it['ids']); att[i, :len(it['ids'])] = 1; k = len(it['markers']); mpos[i, :k] = torch.tensor(it['markers']); mmask[i, :k] = True; target[i, :len(it['target'])] = torch.tensor(it['target'])
    return {'input_ids': ids, 'attention_mask': att, 'marker_pos': mpos, 'marker_mask': mmask, 'target': target, 'qtype': torch.tensor([it['qtype'] for it in items])}

def fit_temp(sel):
    import torch
    if len(sel) < 10: return 1.0
    kmax = max(len(z) for z, _ in sel); Z = torch.full((len(sel), kmax), -1e4); T = torch.zeros((len(sel), kmax))
    for i, (z, t) in enumerate(sel): Z[i, :len(z)] = torch.tensor(z); T[i, :len(t)] = torch.tensor(t)
    log_t = torch.zeros(1, requires_grad=True); opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)
    def closure():
        opt.zero_grad(); loss = -(T*torch.log_softmax(Z/log_t.exp(), -1)).sum(-1).mean(); loss.backward(); return loss
    opt.step(closure); return float(torch.clamp(log_t.exp(), 0.1, 10.0).item())

def forward(model, batch, device):
    return model(batch['input_ids'].to(device), batch['attention_mask'].to(device), batch['marker_pos'].to(device), batch['marker_mask'].to(device), batch['qtype'].to(device))

def train(root, out_dir, epochs, micro_batch, grad_accum, lr_encoder, lr_head, group_size, device, max_steps, seed, positive_weight=1.0, bucket=True, init=None, start_epoch=0, gpu_share=1.0, grad_checkpoint=True):
    import torch
    from safetensors.torch import load_file, save_file
    from transformers import AutoTokenizer
    from laya.common import build_model, proper_reward
    root = Path(root); meta = read(root/'prepare.json'); model_dir = meta['modelDir']
    device = device if device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu')
    cfg = read(os.path.join(model_dir, 'rl_agent_config.json')); cfg['max_len'] = meta['maxLen']; cfg['head_max_len'] = meta['headMaxLen']
    tok = AutoTokenizer.from_pretrained(os.path.join(model_dir, 'tokenizer'))
    model = build_model(cfg, encoder_dir=os.path.join(model_dir, 'encoder')); model.load_state_dict(load_file(os.path.join(init or model_dir, 'model.safetensors')), strict=True)
    if grad_checkpoint: model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False}); model.head_checkpointing = True  # trades GPU time for memory; off is faster when memory is plentiful
    model.to(device); model.train()
    def pace(t_start): gpu_pause(t_start, device, gpu_share)
    items = torch.load(root/'train_items.pt', weights_only=False); val = torch.load(root/'validation_items.pt', weights_only=False)
    # Teacher-positive sequences are rare (about 6%); weight them so the soft targets are not swamped by negatives.
    def is_positive(it): return it['qtype'] == 2 and it['target'][1] >= 0.5 or (it['qtype'] == 0 and it['label'] != len(it['target'])-1)
    for it in items: it['w'] = positive_weight if is_positive(it) else 1.0
    say_w = {'positives': sum(it['w'] > 1 for it in items), 'of': len(items), 'positiveWeight': positive_weight}
    enc = [p for n, p in model.named_parameters() if 'encoder.' in n]; head = [p for n, p in model.named_parameters() if 'encoder.' not in n]
    opt = torch.optim.AdamW([{'params': enc, 'lr': lr_encoder}, {'params': head, 'lr': lr_head}], weight_decay=0.01)
    total_updates = max(1, (len(items)//(micro_batch*grad_accum))*epochs); sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=total_updates, eta_min=1e-6)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True); log = (out_dir/'train.log').open('a')
    def say(**f): line = json.dumps({'at': time.strftime('%H:%M:%S'), **f}); print(line, flush=True); log.write(line+'\n'); log.flush()
    say(device=device, trainItems=len(items), valItems=len(val), epochs=epochs, startEpoch=start_epoch, init=init, microBatch=micro_batch, gradAccum=grad_accum, totalUpdates=total_updates, gpuShare=gpu_share, gradCheckpoint=grad_checkpoint, **say_w)
    for _ in range(start_epoch*max(1, len(items)//(micro_batch*grad_accum))): sched.step()  # resume the cosine schedule where the checkpointed epoch left it
    def val_positive_recall():
        model.eval(); hit = tot = 0
        pos = [it for it in val if is_positive(it) and it['qtype'] == 2]
        with torch.no_grad():
            for i in range(0, len(pos), 16):
                ts = time.time(); b = collate(pos[i:i+16], tok.pad_token_id); logits, _ = forward(model, b, device); pr = torch.softmax(logits.float().cpu().masked_fill(~b['marker_mask'], -1e4), -1)
                hit += int((pr[:, 1] >= 0.5).sum()); tot += len(pos[i:i+16]); pace(ts)
        model.train(); return hit, tot
    def batches(seq):
        # Length buckets: shuffle, sort within chunks of 50 micro-batches, cut, shuffle the cuts. Less padding, steadier MPS memory.
        if not bucket: return [seq[i:i+micro_batch] for i in range(0, len(seq), micro_batch)]
        chunk = micro_batch*50; out = []
        for i in range(0, len(seq), chunk):
            part = sorted(seq[i:i+chunk], key=lambda it: len(it['ids'])); out += [part[j:j+micro_batch] for j in range(0, len(part), micro_batch)]
        random.shuffle(out); return out
    def val_loss():
        model.eval(); tot, n = 0.0, 0
        with torch.no_grad():
            for i in range(0, len(val), 16):
                ts = time.time(); b = collate(val[i:i+16], tok.pad_token_id); logits, _ = forward(model, b, device); logits = logits.float().cpu(); mask = b['marker_mask']
                tot += float(-(b['target']*torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).sum()); n += len(b['target']); pace(ts)
        model.train(); return tot/max(1, n)
    say(valSoftCE=round(val_loss(), 4), stage='before')
    t0, step, accum = time.time(), 0, 0; sigma_start, sigma_end = 0.4, 0.1
    for epoch in range(start_epoch, epochs):
        random.seed(seed+epoch); random.shuffle(items); epoch_loss, nb = 0.0, 0; opt.zero_grad(set_to_none=True)
        sigma = sigma_start+(sigma_end-sigma_start)*(epoch/max(1, epochs-1))
        all_batches = batches(items)
        for b_idx, chunk in enumerate(all_batches):
            ts = time.time(); b = collate(chunk, tok.pad_token_id); w = torch.tensor([it['w'] for it in chunk], device=device)
            logits, act = forward(model, b, device); logits = logits.float(); mask = b['marker_mask'].to(device); k = mask.sum(-1, keepdim=True).float(); target = b['target'].to(device)
            eps = torch.randn((group_size,)+logits.shape, device=device)*sigma*mask; eps = (eps-eps.sum(-1, keepdim=True)/k)*mask
            z = logits.detach().unsqueeze(0)+eps; q = torch.softmax(z.masked_fill(~mask, -1e4), -1)
            with torch.no_grad():
                r = proper_reward(q, target.unsqueeze(0), b['qtype'].to(device), mask, w_sph=0.75, w_rps=1.0); adv = r-r.mean(0, keepdim=True); adv = adv/(adv.std()+1e-6)
            logp = -(((z-logits.unsqueeze(0))**2)*mask).sum(-1)/(2*sigma**2); loss_rl = -(adv*logp*w).sum()/w.sum()/group_size
            loss_ce = (-(target*torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1)*w).sum()/w.sum()
            loss = (loss_rl+loss_ce)/grad_accum+0.0*act.sum(); loss.backward(); accum += 1
            if device == 'mps' and b_idx % 200 == 0: torch.mps.empty_cache()
            if accum % grad_accum == 0 or b_idx+1 >= len(all_batches):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
                if step % 25 == 0: say(epoch=epoch+1, update=step, of=total_updates, loss=round(float(loss)*grad_accum, 4), ce=round(float(loss_ce), 4), reward=round(float(r.mean()), 3), lr=sched.get_last_lr()[0], secondsPerUpdate=round((time.time()-t0)/step, 2))
                if max_steps and step >= max_steps: say(stoppedEarly=True, updates=step, secondsPerUpdate=round((time.time()-t0)/step, 2)); return
            epoch_loss += float(loss)*grad_accum; nb += 1; pace(ts)
        vl = val_loss(); hit, tot = val_positive_recall(); say(epochDone=epoch+1, avgLoss=round(epoch_loss/max(1, nb), 4), valSoftCE=round(vl, 4), valTeacherPositiveRecall=f'{hit}/{tot}', elapsedMin=round((time.time()-t0)/60, 1))
        ck = out_dir/('checkpoint_epoch'+str(epoch+1)); ck.mkdir(exist_ok=True); save_file({k: v.detach().contiguous().cpu() for k, v in model.state_dict().items()}, ck/'model.safetensors')
        model.encoder.config.save_pretrained(ck/'encoder'); tok.save_pretrained(ck/'tokenizer'); (ck/'checkpoint_meta.json').write_text(json.dumps({'epoch': epoch+1, 'valSoftCE': vl, 'valTeacherPositiveRecall': [hit, tot]}))
        json.dump({**cfg, 'fine_tuned': True, 'model_name': 'laya-settlement-judge-jev-distilled', 'temperature': [1.0, 1.2, 1.0]}, (ck/'rl_agent_config.json').open('w'), indent=2)
    # temperatures on a train slice (never on validation), then final save loadable by laya.Agent(out_dir)
    model.eval(); preds = []
    with torch.no_grad():
        for i in range(0, min(len(items), 600), 16):
            b = collate(items[i:i+16], tok.pad_token_id); logits, _ = forward(model, b, device); l = logits.float().cpu().numpy()
            for j, it in enumerate(items[i:i+16]): preds.append((it['qtype'], l[j, :len(it['markers'])], it['target']))
    temps = [1.2, 1.2, 1.2]
    for qt in range(3):
        sel = [(z, t) for q_type, z, t in preds if q_type == qt]
        if sel: temps[qt] = fit_temp(sel)
    save_file({k: v.detach().contiguous().cpu() for k, v in model.state_dict().items()}, out_dir/'model.safetensors'); model.encoder.config.save_pretrained(out_dir/'encoder'); tok.save_pretrained(out_dir/'tokenizer')
    cfg.update({'fine_tuned': True, 'model_name': 'laya-settlement-judge-jev-distilled', 'temperature': temps, 'temperature_by_options': {'noul:2': temps[2], 'choice:3-5': temps[0]}, 'training': {'teacher': 'typesafe/jev-1.13 via OpenRouter', 'trainItems': len(items), 'epochs': epochs, 'updates': step, 'hours': round((time.time()-t0)/3600, 2)}})
    (out_dir/'rl_agent_config.json').write_text(json.dumps(cfg, indent=2)); say(saved=str(out_dir), temperatures=[round(t, 3) for t in temps], hours=round((time.time()-t0)/3600, 2))

# ---------------------------------------------------------------- evaluate (student vs teacher on held-out units)
def evaluate(root, model_path, device):
    import laya, torch
    from laya.common import ece_score
    import numpy as np
    root = Path(root); public = {p['marketId']: p for p in read(ROUND/'public-inputs.json')}; rules = {x['marketId']: x['output'] for x in read(ROUND/'methods/baseline/rules.json') if x['status'] == 'completed'}
    recs = [json.loads(l) for l in (root/'labels.private.jsonl').read_text().splitlines() if l.strip()]; held = [r for r in recs if 'pA' in r and r['split'] == 'validation']
    dev = device if device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cpu')
    agent = laya.Agent(model_path, device=dev) if os.path.isdir(model_path) else laya.load('convaiinnovations/laya', device=dev, **({} if model_path == 'english' else {'subfolder': model_path}))
    pairs = collections.defaultdict(list)
    for r in held:
        ts = time.time(); ans = agent.predict(r['state'], questions_for(public[r['marketId']], rules[r['marketId']]))['answers']; gpu_pause(ts, dev)
        for qid, key in [('A', 'pA'), ('B', 'pB'), ('q', 'pQuestion')]:
            if r.get(key) is not None and qid in ans: pairs[qid].append((ans[qid]['noul'], r[key]))
        pairs['pick'].append((ans['pick']['choice'], max(r['pick'], key=r['pick'].get)))
    out = {'model': model_path, 'heldOutUnits': len(held)}
    for qid in ['A', 'B', 'q']:
        s = np.array([p for p, _ in pairs[qid]]); t = np.array([p for _, p in pairs[qid]])
        if not len(s): continue
        agree = float(np.mean((s >= 0.5) == (t >= 0.5))); brier = float(np.mean((s-t)**2)); pos = t >= 0.5
        auc = None
        if pos.any() and (~pos).any():
            order = np.argsort(s); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s)+1); auc = float((ranks[pos].sum()-pos.sum()*(pos.sum()+1)/2)/(pos.sum()*(~pos).sum()))
        out[qid] = {'n': int(len(s)), 'agreementAt0.5': round(agree, 4), 'brierVsTeacher': round(brier, 4), 'aucVsTeacher': None if auc is None else round(auc, 4), 'teacherPositives': int(pos.sum()), 'studentPositives': int((s >= 0.5).sum())}
    pk = pairs['pick']; out['pick'] = {'n': len(pk), 'agreement': round(sum(a == b for a, b in pk)/max(1, len(pk)), 4)}
    (root/('eval-'+re.sub(r'[^a-z0-9]+', '-', model_path.lower())[-40:]+'.json')).write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('label'); p.add_argument('--root', required=True); p.add_argument('--model', default='typesafe/jev-1.13'); p.add_argument('--max-cost', type=float, default=0.6); p.add_argument('--max-windows', type=int, default=12); p.add_argument('--cross-negatives', type=int, default=3); p.add_argument('--workers', type=int, default=8); p.add_argument('--seed', type=int, default=20260922)
    p = sub.add_parser('label-active'); p.add_argument('--root', required=True); p.add_argument('--student', required=True, help='student checkpoint directory that proposes units'); p.add_argument('--device', default='auto'); p.add_argument('--min-score', type=float, default=0.1, help='cross-market candidates need this student side probability'); p.add_argument('--own-min-score', type=float, default=0.05, help='own-market candidates need only this'); p.add_argument('--max-new', type=int, default=6000); p.add_argument('--max-candidates', type=int, default=16000); p.add_argument('--model', default='typesafe/jev-1.13'); p.add_argument('--max-cost', type=float, default=0.6); p.add_argument('--workers', type=int, default=8); p.add_argument('--seed', type=int, default=20260924); p.add_argument('--dry-run', action='store_true', help='score and write the candidate audit, no teacher calls')
    p = sub.add_parser('label-augment'); p.add_argument('--root', required=True); p.add_argument('--crops', type=int, default=4); p.add_argument('--contrast', type=int, default=1); p.add_argument('--embeds', type=int, default=4, help='embeddings per short positive (synthetic control passages) inside real newsletter filler'); p.add_argument('--min-len', type=int, default=700); p.add_argument('--max-len', type=int, default=1200); p.add_argument('--model', default='typesafe/jev-1.13'); p.add_argument('--max-cost', type=float, default=0.6); p.add_argument('--workers', type=int, default=8); p.add_argument('--seed', type=int, default=20260925); p.add_argument('--dry-run', action='store_true')
    p = sub.add_parser('prepare'); p.add_argument('--root', required=True); p.add_argument('--max-len', type=int, default=768); p.add_argument('--head-max-len', type=int, default=256); p.add_argument('--no-choice', action='store_true'); p.add_argument('--active-min-score', type=float, default=0.0, help='keep student-proposed negatives only at or above this student side score (teacher positives always kept)')
    p = sub.add_parser('train'); p.add_argument('--root', required=True); p.add_argument('--out', required=True); p.add_argument('--epochs', type=int, default=3); p.add_argument('--micro-batch', type=int, default=8); p.add_argument('--grad-accum', type=int, default=4)
    p.add_argument('--lr-encoder', type=float, default=2.5e-5); p.add_argument('--lr-head', type=float, default=1e-4); p.add_argument('--group-size', type=int, default=4); p.add_argument('--device', default='auto'); p.add_argument('--max-steps', type=int, default=0); p.add_argument('--seed', type=int, default=42)
    p.add_argument('--positive-weight', type=float, default=1.0); p.add_argument('--no-bucket', action='store_true'); p.add_argument('--init', help='checkpoint directory to resume weights from'); p.add_argument('--start-epoch', type=int, default=0)
    p.add_argument('--gpu-share', type=share_arg, default=GPU_SHARE, help="fraction of wall time the trainer may keep the GPU busy (0.5 = sleep as long as each step took); 1 = no pacing; 'auto' = MOP_GPU_ACTIVE_SHARE while the machine is in use, full speed when input is idle or the display is off"); p.add_argument('--no-grad-checkpoint', action='store_true', help='skip gradient checkpointing (faster steps, more memory)')
    p = sub.add_parser('evaluate'); p.add_argument('--root', required=True); p.add_argument('--model-path', required=True); p.add_argument('--device', default='auto')
    a = ap.parse_args()
    if a.cmd == 'label': label(a.root, a.model, a.max_cost, a.max_windows, a.cross_negatives, a.workers, a.seed)
    elif a.cmd == 'label-active': label_active(a.root, a.student, a.device, a.min_score, a.own_min_score, a.max_new, a.max_candidates, a.model, a.max_cost, a.workers, a.seed, a.dry_run)
    elif a.cmd == 'label-augment': label_augment(a.root, a.crops, a.contrast, a.embeds, a.min_len, a.max_len, a.model, a.max_cost, a.workers, a.seed, a.dry_run)
    elif a.cmd == 'prepare': prepare(a.root, a.max_len, a.head_max_len, not a.no_choice, a.active_min_score)
    elif a.cmd == 'train': train(a.root, a.out, a.epochs, a.micro_batch, a.grad_accum, a.lr_encoder, a.lr_head, a.group_size, a.device, a.max_steps, a.seed, a.positive_weight, not a.no_bucket, a.init, a.start_epoch, a.gpu_share, not a.no_grad_checkpoint)
    else: evaluate(a.root, a.model_path, a.device)
