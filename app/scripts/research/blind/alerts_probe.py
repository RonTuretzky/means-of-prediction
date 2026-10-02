"""Feasibility probe: can alert-shaped evidence (headline + outlet, as a Google Alerts email carries) settle resolved markets?

Stages (private outputs under --root):
  sample   Draw binary Yes/No markets from the resolved "credible reporting" pool, stratified by topic and payout.
  fetch    For each market query Google News RSS search inside [close-10d, close+2d]; keep headline, outlet name, outlet
           domain and publish date per result (what an alert result exposes). Cached per market, polite rate.
  judge    Ask a judge (the distilled Laya student, or Jev) per headline: does this text state, as something that has
           already happened, that the market's answer is yes?
  summary  Coverage, outlet allowlist coverage, and payout consistency: a YES claim on a NO-resolved market is a definite
           false claim; a YES claim on a YES-resolved market is consistent (never proof). Reported with denominators,
           for all outlets and for the allowlist (outlets whose newsletters the on-chain DKIM registry already holds).
Payouts are private observations used only as a consistency check."""
import argparse, ast, collections, concurrent.futures, datetime, hashlib, html, json, os, random, re, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from laya_distill import RULE, Jev, gpu_pause

POOL = Path.home()/'.local/share/means-of-prediction/dataset-v2-20260916/market-pool-v2/market-pool.jsonl'
REPO = Path(__file__).resolve().parents[4]
MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'

def allowlist():
    """Registrable web domains of the outlets in docs/NEWSLETTER-SUBSCRIPTIONS.md (mail subdomains stripped) plus web aliases."""
    doms = set()
    for line in (REPO/'docs/NEWSLETTER-SUBSCRIPTIONS.md').read_text().splitlines():
        if not line.startswith('|') or 'Verifiable sending domains' in line or '---' in line: continue
        for d in line.strip('|').split('|')[-1].split():
            parts = d.strip().lower().split('.'); two = {'co.uk', 'com.au', 'co.za', 'net.au', 'org.uk', 'com.br', 'co.jp', 'co.in', 'com.ar', 'co.nz'}
            doms.add('.'.join(parts[-3:]) if '.'.join(parts[-2:]) in two else '.'.join(parts[-2:]))
    return doms | {'aljazeera.com', 'reuters.com', 'nytimes.com', 'wsj.com', 'washingtonpost.com', 'bloomberg.com', 'theguardian.com', 'npr.org', 'politico.com', 'nbcnews.com', 'abcnews.go.com', 'go.com', 'usatoday.com', 'latimes.com', 'thehindu.com', 'time.com', 'forbes.com'}

def domain_of(url):
    host = urllib.parse.urlparse(url or '').netloc.lower().split(':')[0]; parts = host.split('.')
    two = {'co.uk', 'com.au', 'co.za', 'net.au', 'org.uk', 'com.br', 'co.jp', 'co.in', 'com.ar', 'co.nz'}
    return '.'.join(parts[-3:]) if '.'.join(parts[-2:]) in two else '.'.join(parts[-2:])

def query_of(question):
    q = re.sub(r'^\s*Will\s+', '', question.strip(), flags=re.I).rstrip('?').strip()
    q = re.sub(r'\b(by|before|on|in|after|through|until)\s+(the end of\s+)?(%s)(\s+\d{1,2})?(,?\s*20\d\d)?' % MONTHS, '', q, flags=re.I)
    q = re.sub(r'\b(in|by|before|during)\s+20\d\d\b', '', q); return re.sub(r'\s+', ' ', q).strip()[:150]

def sample(root, n, seed, since, per_group=0):
    rng = random.Random(seed); by = collections.defaultdict(list); seen_groups = set(); groups = collections.defaultdict(list)
    for line in POOL.open():
        r = json.loads(line)
        lit = lambda v: ast.literal_eval(v) if isinstance(v, str) else v
        try: labels = [str(x).lower() for x in lit(r['outcomeLabels'])]; obs = lit(r['privateObservation']); group = str(r['eventGroupIds'])
        except Exception: continue
        if sorted(labels) != ['no', 'yes'] or r['closedTime'][:10] < since or obs.get('outcome') not in ('Yes', 'No'): continue
        m = {'marketId': r['marketId'], 'question': r['question'], 'rules': (r.get('rules') or '')[:3000], 'topic': r['topic'], 'closed': r['closedTime'][:10], 'payout': obs['outcome'], 'group': group}
        by[(r['topic'], obs['outcome'])].append(m); groups[group].append(m)
    if per_group:
        # Every event group, up to per_group markets: the Yes-resolved one first (if any), then random No siblings (mutually exclusive near-misses that share the same coverage).
        picked = []
        for g in sorted(groups):
            ms = groups[g]; rng.shuffle(ms); ms.sort(key=lambda m: m['payout'] != 'Yes'); picked += ms[:per_group]
        rng.shuffle(picked); (root/'sample.private.json').write_text(json.dumps(picked))
        print(json.dumps({'markets': len(picked), 'eventGroups': len(groups), 'yes': sum(m['payout'] == 'Yes' for m in picked), 'no': sum(m['payout'] == 'No' for m in picked), 'byTopic': dict(collections.Counter(m['topic'] for m in picked))})); return
    picked = []; keys = sorted(by); per = max(1, n//len(keys))
    for k in keys:
        rng.shuffle(by[k])
        for m in by[k]:
            if sum(1 for p in picked if (p['topic'], p['payout']) == k) >= per: break
            if m['group'] in seen_groups: continue  # one market per event group, so siblings do not share headlines
            seen_groups.add(m['group']); picked.append(m)
    (root/'sample.private.json').write_text(json.dumps(picked, indent=1)); print(json.dumps({'markets': len(picked), 'byTopicPayout': {f'{a}/{b}': sum(1 for p in picked if (p['topic'], p['payout']) == (a, b)) for a, b in keys}}))

def gnews(q, after, before):
    url = 'https://news.google.com/rss/search?'+urllib.parse.urlencode({'q': f'{q} after:{after} before:{before}', 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'})
    for attempt in range(5):
        try: raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research probe)'}), timeout=40).read(); break
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 4: time.sleep(20*(attempt+1)); continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 4: time.sleep(5*(attempt+1)); continue
            raise
    out = []
    for it in ET.fromstring(raw).findall('./channel/item'):
        src = it.find('source'); title = it.findtext('title') or ''; name = src.text if src is not None else ''
        head = title[:-len(name)-3] if name and title.endswith(' - '+name) else title
        try: day = datetime.datetime.strptime(it.findtext('pubDate') or '', '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d')
        except ValueError: day = None
        out.append({'headline': html.unescape(head).strip(), 'outlet': name, 'domain': domain_of(src.get('url') if src is not None else ''), 'outletUrl': src.get('url') if src is not None else None, 'day': day, 'pubDate': it.findtext('pubDate'), 'link': it.findtext('link')})
    return out

def fetch(root, before_days, after_days, cap, pause):
    markets = json.loads((root/'sample.private.json').read_text()); cache = root/'fetch'; cache.mkdir(exist_ok=True); n = 0; streak = 0; rng = random.Random(1)
    for m in markets:
        f = cache/(m['marketId']+'.json')
        if f.exists(): continue
        close = datetime.date.fromisoformat(m['closed']); q = query_of(m['question'])
        try: items = gnews(q, (close-datetime.timedelta(days=before_days)).isoformat(), (close+datetime.timedelta(days=after_days+1)).isoformat()); streak = 0
        except Exception as exc:
            streak += 1; print(json.dumps({'fetchError': m['marketId'], 'error': str(exc)[:120], 'streak': streak}), flush=True)
            if streak >= 8: print(json.dumps({'halted': 'eight consecutive fetch failures; rerun later, the cache resumes'})); break
            time.sleep(60); continue
        seen = set(); uniq = [x for x in items if x['headline'] and not ((x['headline'], x['domain']) in seen or seen.add((x['headline'], x['domain'])))]
        f.write_text(json.dumps({'marketId': m['marketId'], 'query': q, 'window': [(close-datetime.timedelta(days=before_days)).isoformat(), (close+datetime.timedelta(days=after_days)).isoformat()], 'results': len(items), 'items': uniq})); n += 1; time.sleep(pause+rng.random())
        if n % 250 == 0: print(json.dumps({'fetched': n, 'of': len(markets)}), flush=True)
    print(json.dumps({'fetchedNow': n, 'cached': len(list(cache.glob('*.json')))}))

def judge(root, backend, model_path, device, max_cost, workers, max_markets=0, seed=0, cap=40):
    markets = {m['marketId']: m for m in json.loads((root/'sample.private.json').read_text())}; out_path = root/f'judged-{backend}.private.jsonl'
    done = {(r['marketId'], r['i']) for r in (json.loads(l) for l in out_path.read_text().splitlines())} if out_path.exists() else set()
    tasks = []; files = sorted((root/'fetch').glob('*.json'))
    if max_markets: random.Random(seed).shuffle(files); files = files[:max_markets]  # a seeded random subset of markets, e.g. to fit a teacher budget
    for f in files:
        d = json.loads(f.read_text()); m = markets[d['marketId']]
        for i, it in enumerate(d['items'][:cap]):
            if (d['marketId'], i) in done: continue
            state = {'subject': 'Google Alert - '+d['query'], 'body': it['headline']+'\n'+it['outlet']}
            qs = {'q': {'type': 'noul', 'instructions': 'Does the text state, as something that has already happened, that the answer to this question is yes: '+m['question']+RULE}}
            tasks.append((d['marketId'], i, state, qs))
    print(json.dumps({'backend': backend, 'tasks': len(tasks), 'alreadyDone': len(done)}), flush=True)
    if backend == 'laya':
        import torch, laya
        dev = device if device != 'auto' else ('mps' if torch.backends.mps.is_available() else 'cpu'); agent = laya.Agent(model_path, device=dev)
        def ask(state, qs): ts = time.time(); a = agent.predict(state, qs)['answers']; gpu_pause(ts, dev); return a['q']['noul']
        workers = 1
    else:
        jev = Jev('typesafe/jev-1.13', max_cost)
        def ask(state, qs): return jev.ask(state, qs)['answers']['q']['noul']
    def run(t):
        try: return t[0], t[1], ask(t[2], t[3]), None
        except Exception as exc: return t[0], t[1], None, str(exc)[:160]
    n = fails = 0
    with out_path.open('a') as fh, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for mid, i, p, err in pool.map(run, tasks):
            if err:
                fails += 1
                if fails >= 10 or 'HTTP 40' in err or 'cost guard' in err: print(json.dumps({'halted': err, 'judged': n})); fh.flush(); os._exit(3)  # budget or key problem: stop now, the caller retries later
                continue
            fh.write(json.dumps({'marketId': mid, 'i': i, 'p': p})+'\n'); n += 1
            if n % 1000 == 0: fh.flush(); print(json.dumps({'judged': n, 'of': len(tasks)}), flush=True)
    print(json.dumps({'judged': n, 'failures': fails}))

def summary(root, thresholds):
    markets = json.loads((root/'sample.private.json').read_text()); allow = allowlist(); fetched = {}
    for f in (root/'fetch').glob('*.json'): d = json.loads(f.read_text()); fetched[d['marketId']] = d
    out = {'markets': len(markets), 'fetched': len(fetched), 'yes': sum(m['payout'] == 'Yes' for m in markets), 'no': sum(m['payout'] == 'No' for m in markets)}
    got = [m for m in markets if m['marketId'] in fetched]; n_items = [len(fetched[m['marketId']]['items']) for m in got]
    out['coverage'] = {'withAnyHeadline': sum(x > 0 for x in n_items), 'withAllowlistedHeadline': sum(any(it['domain'] in allow for it in fetched[m['marketId']]['items']) for m in got), 'of': len(got),
                       'medianHeadlines': sorted(n_items)[len(n_items)//2] if n_items else 0, 'medianDistinctOutlets': sorted(len({it['domain'] for it in fetched[m['marketId']]['items']}) for m in got)[len(got)//2] if got else 0,
                       'headlines': sum(n_items), 'allowlistedHeadlines': sum(it['domain'] in allow for m in got for it in fetched[m['marketId']]['items'])}
    for backend in ('laya', 'jev'):
        p = root/f'judged-{backend}.private.jsonl'
        if not p.exists(): continue
        probs = collections.defaultdict(dict)
        for l in p.read_text().splitlines(): r = json.loads(l); probs[r['marketId']][r['i']] = r['p']
        res = {}
        for t in thresholds:
            row = {}
            for scope in ('all', 'allowlist'):
                def claims(m, k):
                    items = fetched[m['marketId']]['items']; doms = {items[i]['domain'] for i, pv in probs.get(m['marketId'], {}).items() if pv >= t and (scope == 'all' or items[i]['domain'] in allow)}
                    return len(doms) >= k
                judged = [m for m in got if m['marketId'] in probs]
                yes = [m for m in judged if m['payout'] == 'Yes']; no = [m for m in judged if m['payout'] == 'No']
                row[scope] = {f'K{k}': {'yesMarketsWithClaim': f"{sum(claims(m, k) for m in yes)}/{len(yes)}", 'noMarketsWithFalseClaim': f"{sum(claims(m, k) for m in no)}/{len(no)}"} for k in (1, 2, 3)}
            res[str(t)] = row
        hl = [(pv, fetched[mid]['items'][i], mid) for mid, d in probs.items() for i, pv in d.items()]
        res['headlinesJudged'] = len(hl); res['headlinesAbove0.5'] = sum(pv >= 0.5 for pv, _, _ in hl); out[backend] = res
    (root/'summary.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['sample', 'fetch', 'judge', 'summary']); ap.add_argument('--root', required=True)
    ap.add_argument('--n', type=int, default=120); ap.add_argument('--seed', type=int, default=20261002); ap.add_argument('--since', default='2026-03-01')
    ap.add_argument('--before-days', type=int, default=10); ap.add_argument('--after-days', type=int, default=2); ap.add_argument('--cap', type=int, default=40)
    ap.add_argument('--backend', default='laya', choices=['laya', 'jev']); ap.add_argument('--model-path'); ap.add_argument('--device', default='auto'); ap.add_argument('--max-cost', type=float, default=1000.0, help='local guard only; the OpenRouter key has its own limit'); ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--thresholds', default='0.4,0.5,0.7'); ap.add_argument('--pause', type=float, default=1.5); ap.add_argument('--max-markets', type=int, default=0); ap.add_argument('--per-group', type=int, default=0, help='sample every event group with up to this many markets'); a = ap.parse_args()
    root = Path(a.root); os.umask(0o077); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if a.cmd == 'sample': sample(root, a.n, a.seed, a.since, a.per_group)
    elif a.cmd == 'fetch': fetch(root, a.before_days, a.after_days, a.cap, a.pause)
    elif a.cmd == 'judge': judge(root, a.backend, a.model_path, a.device, a.max_cost, a.workers, a.max_markets, a.seed, a.cap)
    else: summary(root, [float(x) for x in a.thresholds.split(',')])
