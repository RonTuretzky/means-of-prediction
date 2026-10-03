"""Full-text index over the GDELT Article List days and market pairing in alert shape.

  build   SQLite FTS5 over title + desc of every English GAL record (one row per URL, first seen), with t (file time,
          'seen by'), date (publisher-declared), domain, outletName, url. ~60M rows for the June 2025 - Sept 2026 window.
  pair    For each market: entity terms from the question (and the Fable rule when present), a time window around the
          close (or the rule's event instance later), FTS5 match (all entities, then the two most specific, then any),
          BM25 ranking, cap per market. Writes alert-shaped units: headline (title), publisher (outletName), snippet (desc),
          host (domain), url, seenAt. Payouts are not read here.
Private outputs; resumable (build by day, pair by market)."""
import argparse, collections, datetime, gzip, json, os, re, sqlite3, time
from pathlib import Path

GAL = Path.home()/'.local/share/means-of-prediction/gdelt-gal'
STOP = {'Will', 'The', 'Yes', 'No', 'This', 'That', 'What', 'Who', 'When', 'Does', 'And', 'Before', 'After', 'Exact', 'Score', 'Did', 'Is', 'Are', 'Be', 'By', 'In', 'On', 'At', 'Of', 'For', 'To', 'A', 'An', 'Or', 'If', 'How', 'Many', 'Most', 'Next', 'New', 'Any', 'All', 'More', 'Than', 'Over', 'Under', 'Between', 'Both', 'Win', 'Wins', 'Lose', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday', 'Week', 'Day', 'Year', 'Month', 'Season', 'Game', 'Match', 'Round', 'Final', 'Finals', 'Cup', 'League', 'Team', 'Player', 'President', 'Election', 'Vote', 'Market', 'Price', 'Million', 'Billion', 'US', 'U.S', 'USA', 'UK', 'EU', 'Trump', 'Biden'}

def connect(path):
    con = sqlite3.connect(path); con.execute('PRAGMA journal_mode=WAL'); con.execute('PRAGMA synchronous=OFF'); con.execute('PRAGMA cache_size=-800000'); return con

def build(db, days):
    con = connect(db)
    con.execute('CREATE TABLE IF NOT EXISTS art (id INTEGER PRIMARY KEY, t TEXT, date TEXT, domain TEXT, outlet TEXT, url TEXT UNIQUE, title TEXT, desc TEXT)')
    con.execute('CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, desc, content="art", content_rowid="id", tokenize="unicode61 remove_diacritics 2")')  # external content: text lives once, in art
    con.execute('CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, rows INTEGER, dup INTEGER)'); con.execute('CREATE INDEX IF NOT EXISTS art_t ON art(t)')
    done = {r[0] for r in con.execute('SELECT day FROM days')}; t0 = time.time(); total = 0
    for f in sorted(GAL.glob('en/*.jsonl.gz')):
        day = f.name[:10]
        if day in done or (days and day not in days): continue
        rows = dup = 0; cur = con.cursor()
        for line in gzip.open(f, 'rt', encoding='utf-8'):
            try: r = json.loads(line)
            except ValueError: continue
            title, desc = (r.get('title') or '').strip(), (r.get('desc') or '').strip()
            try: cur.execute('INSERT INTO art (t, date, domain, outlet, url, title, desc) VALUES (?,?,?,?,?,?,?)', (r['t'], (r.get('date') or '')[:19], r.get('domain') or '', r.get('outletName') or '', r.get('url') or '', title, desc))
            except sqlite3.IntegrityError: dup += 1; continue
            cur.execute('INSERT INTO fts (rowid, title, desc) VALUES (?,?,?)', (cur.lastrowid, title, desc)); rows += 1
        cur.execute('INSERT INTO days VALUES (?,?,?)', (day, rows, dup)); con.commit(); total += rows
        print(json.dumps({'day': day, 'rows': rows, 'dup': dup, 'totalRows': total, 'minutes': round((time.time()-t0)/60, 1)}), flush=True)
    con.execute("INSERT INTO fts(fts) VALUES ('optimize')"); con.commit(); print(json.dumps({'built': True, 'rows': con.execute('SELECT count(*) FROM art').fetchone()[0]}), flush=True)

def entities(text):
    words = re.findall(r"\b[A-Z][a-zA-Z'’.-]{2,}\b|\b\d[\d,.]*\b", text)
    out = []
    for w in words:
        w = w.strip('.,')
        if w in STOP or w.lower() in {s.lower() for s in STOP} or len(w) < 3 and not w.isdigit(): continue
        if w not in out: out.append(w)
    return out

def phrase(w): return '"'+w.replace('"', '')+'"'

def pair(db, sample, rules_path, out_path, before_days, after_days, cap, since_market=None):
    con = connect(db); markets = json.loads(Path(sample).read_text()); rules = {}
    if rules_path and Path(rules_path).exists():
        for l in open(rules_path):
            if l.strip(): r = json.loads(l); rules[r['marketId']] = r
    done = set()
    if Path(out_path).exists():
        for l in open(out_path):
            if l.strip(): done.add(json.loads(l)['marketId'])
    todo = [m for m in markets if m['marketId'] not in done]; t0 = time.time(); stats = collections.Counter()
    print(json.dumps({'markets': len(markets), 'done': len(done), 'todo': len(todo), 'rules': len(rules)}), flush=True)
    with open(out_path, 'a') as out:
        for n, m in enumerate(todo, 1):
            close = datetime.date.fromisoformat(m['closed']); lo = (close-datetime.timedelta(days=before_days)).strftime('%Y%m%d'); hi = (close+datetime.timedelta(days=after_days+1)).strftime('%Y%m%d')
            ents = entities(m['question']); rule = rules.get(m['marketId'])
            if rule: ents = ents+[e for e in entities(rule.get('factualA', ''))[:4] if e not in ents]
            ents = ents[:8]; hits = []; strategy = None
            def run(q, limit):
                return con.execute("SELECT fts.rowid, bm25(fts) AS s, art.title, art.desc, art.t, art.date, art.domain, art.outlet, art.url FROM fts JOIN art ON art.id = fts.rowid WHERE fts MATCH ? AND art.t >= ? AND art.t < ? ORDER BY s LIMIT ?", (q, lo+'000000', hi+'000000', limit)).fetchall()
            def df(e):  # corpus-wide document frequency, capped: rare terms carry the match
                try: return con.execute("SELECT count(*) FROM (SELECT rowid FROM fts WHERE fts MATCH ? LIMIT 3000)", (phrase(e),)).fetchone()[0]
                except sqlite3.OperationalError: return 10**9
            ranked = sorted([e for e in ents if not e.isdigit()], key=df) + [e for e in ents if e.isdigit()]
            tries = []
            if len(ranked) >= 2: tries.append(('rare3', ' AND '.join(phrase(e) for e in ranked[:3])))
            if len(ranked) >= 2: tries.append(('rare2', ' AND '.join(phrase(e) for e in ranked[:2])))
            if ranked: tries.append(('any2', ' OR '.join(phrase(e) for e in ranked[:6])))
            for strategy, q in tries:
                try: hits = run(q, cap*4 if strategy == 'any2' else cap)
                except sqlite3.OperationalError: continue
                if strategy == 'any2':  # keep only records naming at least two distinct entities
                    low = lambda t: (t or '').lower(); hits = [h for h in hits if sum(e.lower() in low(h[2])+' '+low(h[3]) for e in ranked[:6]) >= 2][:cap]
                if len(hits) >= 5: break
            seen = set(); units = []
            for rowid, s, title, desc, t, date, domain, outlet, url in hits:
                k = (title.strip().lower(), domain)
                if k in seen: continue
                seen.add(k); units.append({'headline': title, 'publisher': outlet, 'snippet': desc, 'host': domain, 'url': url, 'seenAt': t, 'declaredDate': date, 'score': round(-s, 3)})
            stats[strategy or 'none'] += 1; stats['withUnits'] += bool(units)
            out.write(json.dumps({'marketId': m['marketId'], 'question': m['question'], 'closed': m['closed'], 'window': [lo, hi], 'entities': ents, 'strategy': strategy, 'units': units}, ensure_ascii=False)+'\n')
            if n % 500 == 0: out.flush(); print(json.dumps({'paired': n, 'of': len(todo), 'secondsPerMarket': round((time.time()-t0)/n, 2), **stats}), flush=True)
    print(json.dumps({'finished': True, **stats}), flush=True)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['build', 'pair']); ap.add_argument('--db', default=str(GAL/'gal.sqlite3')); ap.add_argument('--days', default='', help='comma list of days (smoke test)')
    ap.add_argument('--sample'); ap.add_argument('--rules'); ap.add_argument('--out'); ap.add_argument('--before-days', type=int, default=10); ap.add_argument('--after-days', type=int, default=2); ap.add_argument('--cap', type=int, default=60); a = ap.parse_args()
    os.umask(0o077)
    if a.cmd == 'build': build(a.db, set(a.days.split(',')) if a.days else None)
    else: pair(a.db, a.sample, a.rules, a.out, a.before_days, a.after_days, a.cap)
