"""Pull Google Alerts emails from the research mailbox (read-only IMAP, every folder including Spam), store the raw RFC822 bytes
privately, snapshot the google.com DKIM record for each selector seen, verify signatures offline, and print a format census.
Never prints or stores anything but the raw messages (which contain the recipient address and per-alert tokens: keep the
directory private and never publish a message). Usage: alerts_mail.py --root <dir> [--since 03-Oct-2026]"""
import argparse, collections, datetime, email, email.policy, email.utils, imaplib, json, os, re, statistics, subprocess, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import alerts_email as ae

def pull(root, since):
    cfg = json.load(open(os.path.expanduser('~/.config/means-of-prediction/mailbox.json'))); M = imaplib.IMAP4_SSL(cfg['host']); M.login(cfg['user'], cfg['appPassword'])
    raw_dir = root/'raw'; raw_dir.mkdir(parents=True, exist_ok=True); os.chmod(root, 0o700); os.chmod(raw_dir, 0o700); seen = {p.stem for p in raw_dir.glob('*.eml')}; new = 0; by_folder = collections.Counter()
    for b in M.list()[1]:
        box = b.decode().split(' "/" ')[-1].strip('"')
        try: typ, _ = M.select(f'"{box}"', readonly=True)
        except Exception: continue
        if typ != 'OK': continue
        ids = M.search(None, f'(FROM "googlealerts-noreply@google.com" SINCE {since})')[1][0].split(); by_folder[box] = len(ids)
        for i in ids:
            hdr = M.fetch(i, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')[1][0][1].decode(errors='replace'); mid = re.sub(r'[^A-Za-z0-9]', '', hdr.split(':', 1)[-1])[:48]
            if not mid or mid in seen: continue
            raw = M.fetch(i, '(BODY.PEEK[])')[1][0][1]; p = raw_dir/(mid+'.eml'); p.write_bytes(raw); os.chmod(p, 0o600); seen.add(mid); new += 1
    M.logout(); return new, by_folder

def dns_snapshot(root, selectors):
    snap = root/'dkim-dns.json'; d = json.loads(snap.read_text()) if snap.exists() else {}
    for s in selectors:
        try:
            import dns.resolver; txt = ''.join(b.decode() if isinstance(b, bytes) else str(b) for r in dns.resolver.resolve(f'{s}._domainkey.google.com', 'TXT') for b in r.strings)
        except Exception as exc: txt = 'lookup failed: '+str(exc)[:80]
        d.setdefault(s, []).append({'at': datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ'), 'txt': txt})
    snap.write_text(json.dumps(d, indent=1)); return {s: (d[s][-1]['txt'][:40]+'...' if d[s][-1]['txt'] else 'EMPTY') for s in selectors}

def verify(raw):
    try:
        import dkim; return bool(dkim.verify(raw))
    except Exception as exc: return str(exc)[:60]

def census(root, sample_verify):
    rows = []
    for p in sorted((root/'raw').glob('*.eml')):
        raw = p.read_bytes(); m = email.message_from_bytes(raw, policy=email.policy.default); d = ae.parse(raw)
        try: sent = email.utils.parsedate_to_datetime(d['date'])
        except Exception: sent = None
        rows.append({'file': p.name, 'query': d.get('query') or re.sub(r'^Google Alert - ', '', d['subject']), 'sent': sent.isoformat() if sent else None, 'bytes': len(raw), 'selector': d['dkimSelector'], 'results': d['results'], 'contentType': str(m.get_content_type())})
    sel = collections.Counter(r['selector'] for r in rows); per = collections.Counter(r['query'] for r in rows); nres = [len(r['results']) for r in rows]; sizes = [r['bytes'] for r in rows]
    allr = [x for r in rows for x in r['results']]; hosts = collections.Counter(x['host'] for x in allr); secs = collections.Counter(x['section'] for x in allr)
    hl = [len(x['headline']) for x in allr]; sn = [len(x['snippet']) for x in allr]
    sent = sorted(r['sent'] for r in rows if r['sent']); per_day = collections.Counter(s[:10] for s in sent)
    ver = collections.Counter(); import random; random.seed(1)
    for p in random.sample(sorted((root/'raw').glob('*.eml')), min(sample_verify, len(rows))): ver[str(verify(p.read_bytes()))] += 1
    out = {'emails': len(rows), 'firstSent': sent[0] if sent else None, 'lastSent': sent[-1] if sent else None, 'perDay': dict(sorted(per_day.items())), 'selectors': dict(sel), 'contentTypes': dict(collections.Counter(r['contentType'] for r in rows)),
           'bytesMedianMax': [statistics.median(sizes), max(sizes)] if sizes else None, 'resultsPerEmail': {'median': statistics.median(nres), 'max': max(nres), 'one': sum(n == 1 for n in nres), 'tenOrMore': sum(n >= 10 for n in nres)} if nres else None,
           'results': len(allr), 'sections': dict(secs), 'headlineLenMedianMax': [statistics.median(hl), max(hl)] if hl else None, 'snippetLenMedianMax': [statistics.median(sn), max(sn)] if sn else None,
           'headlineEllipsis': sum(x['headline'].rstrip().endswith('...') for x in allr), 'snippetEllipsis': sum(x['snippet'].rstrip().endswith('...') for x in allr), 'headlineOutletSuffix': sum(x['headline'].endswith(' - '+x['publisher']) for x in allr if x['publisher']),
           'distinctHosts': len(hosts), 'topHosts': hosts.most_common(15), 'perQuery': per.most_common(), 'dkimVerifiedSample': dict(ver)}
    (root/'census.json').write_text(json.dumps(out, indent=1, default=str)); (root/'results.private.jsonl').write_text(''.join(json.dumps({k: r[k] for k in ('file', 'query', 'sent', 'selector')} | {'results': r['results']}, ensure_ascii=False)+'\n' for r in rows))
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--root', default=os.path.expanduser('~/.local/share/means-of-prediction/alerts-mail-20261006')); ap.add_argument('--since', default='03-Oct-2026'); ap.add_argument('--verify-sample', type=int, default=40); a = ap.parse_args()
    os.umask(0o077); root = Path(a.root); root.mkdir(parents=True, exist_ok=True)
    new, by_folder = pull(root, a.since); print(json.dumps({'newRawMessages': new, 'byFolder': {k: v for k, v in by_folder.items() if v}}), flush=True)
    c = census(root, a.verify_sample); print(json.dumps({'dnsSnapshot': dns_snapshot(root, [s for s in c['selectors'] if s])}))
    print(json.dumps({k: v for k, v in c.items() if k not in ('perQuery', 'topHosts')}, default=str)); print('per query:', c['perQuery']); print('top hosts:', c['topHosts'])
