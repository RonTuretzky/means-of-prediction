"""How far is the GDELT Article List from what Google Alerts actually delivered?

For every result in the collected alert emails (results.private.jsonl from alerts_mail.py), look for the same article in the
GDELT daily files around the send date: by exact URL, then by (host, normalised title). Reports presence rates overall and per
host, headline and snippet agreement where both exist, and the delay from GDELT's first sighting to the alert's send time.
Usage: alerts_fidelity.py --mail-root <alerts-mail dir> --days 2026-10-02,2026-10-03,..."""
import argparse, collections, datetime, gzip, json, os, re, statistics, urllib.parse
from pathlib import Path
GAL = Path(os.path.expanduser('~/.local/share/means-of-prediction/gdelt-gal/en'))

def norm_url(u):
    p = urllib.parse.urlsplit(u.strip()); host = p.netloc.lower().split(':')[0]; host = host[4:] if host.startswith('www.') else host
    return host+p.path.rstrip('/').lower()
def norm_title(t):
    t = re.sub(r'\s*[-|–]\s*[^-|–]{2,40}$', '', t)  # drop a trailing " - Outlet"
    return re.sub(r'[^a-z0-9 ]', '', t.lower()).strip()
def host_of(u):
    h = urllib.parse.urlsplit(u).netloc.lower().split(':')[0]; parts = h.split('.'); two = {'co.uk', 'com.au', 'co.za', 'org.uk', 'com.br', 'co.jp', 'co.in', 'co.nz'}
    return '.'.join(parts[-3:]) if '.'.join(parts[-2:]) in two else '.'.join(parts[-2:])
def jaccard(a, b):
    A = set(re.findall(r'[a-z0-9]+', a.lower())); B = set(re.findall(r'[a-z0-9]+', b.lower())); return len(A & B)/len(A | B) if A | B else 0.0

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--mail-root', required=True); ap.add_argument('--days', required=True); a = ap.parse_args()
    by_url, by_ht = {}, {}
    for day in a.days.split(','):
        f = GAL/f'{day}.jsonl.gz'
        if not f.exists(): print('missing GAL day', day); continue
        for line in gzip.open(f, 'rt', encoding='utf-8'):
            r = json.loads(line); u = norm_url(r['url']); by_url.setdefault(u, r); by_ht.setdefault((host_of(r['url']), norm_title(r['title'] or '')), r)
    print(json.dumps({'galRecords': len(by_url), 'days': a.days}), flush=True)
    rows = [json.loads(l) for l in open(Path(a.mail_root)/'results.private.jsonl')]
    tot = found_url = found_title = 0; per_host = collections.defaultdict(lambda: [0, 0]); delays = []; head_eq = head_prefix = 0; snip_sim = []; youtube = 0
    for r in rows:
        try: sent = datetime.datetime.fromisoformat(r['sent']).astimezone(datetime.UTC)
        except Exception: sent = None
        for x in r['results']:
            tot += 1; h = x['host']; per_host[h][0] += 1
            if h == 'youtube.com': youtube += 1
            g = by_url.get(norm_url(x['url'])); how = 'url' if g else None
            if not g: g = by_ht.get((h, norm_title(x['headline']))); how = 'title' if g else None
            if not g: continue
            per_host[h][1] += 1; found_url += how == 'url'; found_title += how == 'title'
            gt = norm_title(g['title'] or ''); at = norm_title(x['headline']); head_eq += gt == at; head_prefix += (gt != at and (gt.startswith(at.rstrip('.')) or at.startswith(gt)))
            if x['snippet'] and g.get('desc'): snip_sim.append(jaccard(x['snippet'], g['desc']))
            if sent and g.get('t'):
                seen = datetime.datetime.strptime(g['t'], '%Y%m%d%H%M%S').replace(tzinfo=datetime.UTC); delays.append((sent-seen).total_seconds()/3600)
    found = found_url+found_title
    out = {'alertResults': tot, 'youtubeResults': youtube, 'foundInGdelt': found, 'byUrl': found_url, 'byHostTitle': found_title, 'foundShare': round(found/tot, 3) if tot else None,
           'foundShareExcludingYoutube': round(found/(tot-youtube), 3) if tot-youtube else None,
           'headlineEqualAmongFound': head_eq, 'headlinePrefixOrTruncated': head_prefix, 'snippetVsDescJaccardMedian': round(statistics.median(snip_sim), 3) if snip_sim else None, 'snippetsCompared': len(snip_sim),
           'alertMinusGdeltHoursMedian': round(statistics.median(delays), 2) if delays else None, 'delayQuartiles': [round(x, 2) for x in statistics.quantiles(delays, n=4)] if len(delays) > 3 else None, 'alertBeforeGdelt': sum(d < 0 for d in delays),
           'perHost': {h: {'results': n, 'found': k, 'share': round(k/n, 2)} for h, (n, k) in sorted(per_host.items(), key=lambda kv: -kv[1][0])[:20]}}
    Path(a.mail_root, 'fidelity.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))

if __name__ == '__main__': main()
