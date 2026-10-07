"""K-outlet tables on the alert-shaped retrospective corpus: payout consistency of Jev labels per market.

A unit claims YES when pA >= t. A market "reaches K" when K distinct hosts claim (all hosts, or registry hosts from
docs/NEWSLETTER-SUBSCRIPTIONS.md via alerts_probe.allowlist()). Coverage = YES-payout markets reaching K; false YES =
NO-payout markets reaching K. Payouts are a consistency check, never proof. Units are counted only if dated on or before
the market's close date (the pairing window runs to close + 2 days); the window START is not known here, so events that
happened before market creation can still count (see the October 7 audit of the ten false-YES markets in the master handoff).
Output: table JSON under --out (default slides/alerts-corpus-20261003/tables-<stamp>.json) and a printed table."""
import argparse, collections, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alerts_probe

def main():
    ap = argparse.ArgumentParser(); C = os.path.expanduser('~/.local/share/means-of-prediction/slides/alerts-corpus-20261003')
    ap.add_argument('--sample', default=C+'/sample.private.json'); ap.add_argument('--labels', default=C+'/labels-alerts.private.jsonl')
    ap.add_argument('--thresholds', default='0.5,0.7'); ap.add_argument('--any-time', action='store_true', help='count units after the close date too'); ap.add_argument('--out')
    a = ap.parse_args(); allow = alerts_probe.allowlist(); ts = [float(x) for x in a.thresholds.split(',')]
    s = json.load(open(a.sample)); ms = s if isinstance(s, list) else (s.get('markets') or list(s.values())[0]); meta = {m['marketId']: m for m in ms}
    per = collections.defaultdict(list); n = 0
    for l in open(a.labels):
        r = json.loads(l); n += 1
        if r.get('pA') is not None: per[r['marketId']].append(r)
    cells = collections.defaultdict(lambda: collections.Counter()); topics = collections.defaultdict(lambda: collections.Counter())
    for mid, rs in per.items():
        m = meta.get(mid)
        if not m or m['payout'] not in ('Yes', 'No'): continue
        rs = [r for r in rs if a.any_time or r['seenAt'][:8] <= m['closed'].replace('-', '')]
        if not rs: continue
        for t in ts:
            hosts = {r['host'] for r in rs if r['pA'] >= t}
            for scope, h in (('all', hosts), ('registry', hosts & allow)):
                for K in (1, 2, 3):
                    c = cells[(t, scope, K)]; c[(m['payout'], 'n')] += 1; c[(m['payout'], 'hit')] += (len(h) >= K)
            if t == ts[-1]:
                c = topics[m['topic']]; c[(m['payout'], 'n')] += 1; c[(m['payout'], 'hit')] += bool(hosts)
    rows = []
    print(json.dumps({'labels': n, 'marketsWithLabels': len(per), 'unitsAfterClose': 'counted' if a.any_time else 'dropped'}))
    print(f"{'t':>4} {'hosts':>8} {'K':>2} | YES markets reaching K (coverage) | NO markets reaching K (false YES)")
    for (t, scope, K), c in sorted(cells.items()):
        row = {'threshold': t, 'hosts': scope, 'K': K, 'yesN': c[('Yes', 'n')], 'yesHit': c[('Yes', 'hit')], 'noN': c[('No', 'n')], 'noHit': c[('No', 'hit')]}; rows.append(row)
        print(f"{t:>4} {scope:>8} {K:>2} | {row['yesHit']:>6} / {row['yesN']:<6} {row['yesHit']/max(1,row['yesN']):6.1%}        | {row['noHit']:>5} / {row['noN']:<6} {row['noHit']/max(1,row['noN']):6.2%}")
    print(f"\nper topic at t={ts[-1]}, any host, K=1")
    tp = []
    for topic, c in sorted(topics.items(), key=lambda kv: -sum(kv[1].values())):
        tp.append({'topic': topic, 'yesN': c[('Yes', 'n')], 'yesHit': c[('Yes', 'hit')], 'noN': c[('No', 'n')], 'noHit': c[('No', 'hit')]})
        print(f"  {topic:<20} YES {c[('Yes','hit')]:>5}/{c[('Yes','n')]:<5} {c[('Yes','hit')]/max(1,c[('Yes','n')]):6.1%} | NO {c[('No','hit')]:>4}/{c[('No','n')]:<5} {c[('No','hit')]/max(1,c[('No','n')]):6.2%}")
    out = a.out or f"{C}/tables-{time.strftime('%Y%m%d-%H%M')}.json"
    os.umask(0o077); json.dump({'at': time.strftime('%Y-%m-%dT%H:%M%z'), 'labels': n, 'marketsWithLabels': len(per), 'unitsAfterClose': bool(a.any_time), 'cells': rows, 'topics': tp}, open(out, 'w'), indent=1); print('wrote', out)

if __name__ == '__main__': main()
