"""Download the GDELT Article List (GAL) for a date range, keeping English records in alert shape.

GAL (https://data.gdeltproject.org/gdeltv3/gal/YYYYMMDDHHMMSS.gal.json.gz) publishes about two files per quarter hour at
slightly varying minutes and offers no public listing, so every quarter hour is probed at minute offsets 0..7. Each record
has title, desc (a one-sentence description, median ~146 characters), domain, outletName, url, date: the same four fields a
Google Alerts result carries (headline, snippet, publisher, link), plus the file timestamp as a "seen by" time. Licence:
GDELT data is free to use and redistribute with citation. One gzip JSONL per day under --root/en/, resumable by day."""
import argparse, concurrent.futures, datetime, gzip, io, json, os, threading, time, urllib.error, urllib.request
from pathlib import Path

KEEP = ('date', 'url', 'domain', 'outletName', 'title', 'desc')

def get(stamp):
    url = f'https://data.gdeltproject.org/gdeltv3/gal/{stamp}.gal.json.gz'
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'means-of-prediction research (GDELT GAL bulk reader)'}), timeout=120) as resp: return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404): return None
            if attempt == 3: raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 3: raise
        time.sleep(2*(attempt+1))

def day_job(root, day, workers):
    out = root/'en'/f'{day}.jsonl.gz'
    if out.exists(): return None
    stamps = [f"{day.replace('-', '')}{h:02d}{b+o:02d}00" for h in range(24) for b in (0, 15, 30, 45) for o in range(8)]
    tmp = out.with_suffix('.tmp'); lock = threading.Lock(); stats = {'day': day, 'files': 0, 'records': 0, 'en': 0, 'bytes': 0, 'errors': 0}
    with gzip.open(tmp, 'wt', encoding='utf-8') as gz:
        def one(stamp):
            try: raw = get(stamp)
            except Exception:
                with lock: stats['errors'] += 1
                return
            if not raw: return
            lines = []; n = 0
            try: text = gzip.decompress(raw).decode('utf-8', 'replace')
            except Exception:
                with lock: stats['errors'] += 1
                return
            for line in text.splitlines():
                if not line.strip(): continue
                n += 1
                try: r = json.loads(line)
                except ValueError: continue
                if r.get('lang') != 'en' or not r.get('title'): continue
                lines.append(json.dumps({'t': stamp, **{k: r.get(k) for k in KEEP}}, ensure_ascii=False))
            with lock:
                stats['files'] += 1; stats['records'] += n; stats['en'] += len(lines); stats['bytes'] += len(raw)
                if lines: gz.write('\n'.join(lines)+'\n')
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool: list(pool.map(one, stamps))
    if stats['errors'] > 20: tmp.unlink(); stats['skipped'] = 'too many errors; will retry on the next run'; return stats
    tmp.rename(out); return stats

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', default=str(Path.home()/'.local/share/means-of-prediction/gdelt-gal')); ap.add_argument('--start', required=True); ap.add_argument('--end', required=True)
    ap.add_argument('--workers', type=int, default=12); ap.add_argument('--oldest-first', action='store_true'); a = ap.parse_args()
    root = Path(a.root); (root/'en').mkdir(parents=True, exist_ok=True)
    d0, d1 = datetime.date.fromisoformat(a.start), datetime.date.fromisoformat(a.end); days = [(d0+datetime.timedelta(days=i)).isoformat() for i in range((d1-d0).days+1)]
    if not a.oldest_first: days.reverse()
    for day in days:
        t = time.time(); stats = day_job(root, day, a.workers)
        if stats is None: continue
        stats['seconds'] = round(time.time()-t, 1)
        with (root/'manifest.jsonl').open('a') as f: f.write(json.dumps(stats)+'\n')
        print(json.dumps(stats), flush=True)
    print(json.dumps({'finished': True, 'days': len(list((root/'en').glob('*.jsonl.gz')))}), flush=True)

if __name__ == '__main__': main()
