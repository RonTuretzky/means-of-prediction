"""Parse a raw Google Alerts email into the result units a judge may read.

Each result in the signed body carries exactly four fields (verified on real 2025-2026 samples): the headline (page title,
at most ~100 characters, often ending " - Outlet"), a publisher label assigned by Google, a snippet (at most ~160
characters, an extract that may be cut mid-sentence) and a google.com/url redirect whose url= parameter is the article
URL. Outlet identity must come from the article URL's host, never from the label or the headline suffix. The Subject and
the "new results for [query]" banner echo the alert owner's query and are not evidence.
Usage: alerts_email.py file.eml [...]  ->  one JSON object per email."""
import email, email.policy, html, json, re, sys, urllib.parse

TWO = {'co.uk', 'com.au', 'co.za', 'net.au', 'org.uk', 'com.br', 'co.jp', 'co.in', 'com.ar', 'co.nz'}
def registrable(host):
    parts = host.lower().split(':')[0].split('.'); return '.'.join(parts[-3:]) if '.'.join(parts[-2:]) in TWO else '.'.join(parts[-2:])

def parse(raw):
    m = email.message_from_bytes(raw, policy=email.policy.default); sig = re.sub(r'\s+', '', str(m.get('DKIM-Signature', '')))
    out = {'from': str(m.get('From', '')), 'subject': str(m.get('Subject', '')), 'date': str(m.get('Date', '')), 'dkimDomain': (re.search(r'd=([^;]+)', sig) or [None, None])[1], 'dkimSelector': (re.search(r's=([^;]+)', sig) or [None, None])[1],
           'signedAt': int((re.search(r't=(\d+)', sig) or [0, 0])[1]) or None, 'results': []}
    part = m.get_body(preferencelist=('html',)); page = part.get_content() if part is not None else ''
    q = re.search(r'new results? for \[(.*?)\]', (m.get_body(preferencelist=('plain',)).get_content() if m.get_body(preferencelist=('plain',)) is not None else ''))
    if q: out['query'] = q.group(1)
    clean = lambda t: re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', t)).replace('\xa0', ' ')).strip()
    # The HTML part marks every result as a schema.org Article row: url, name (headline), publisher name, description (snippet).
    rows = re.split(r'<tr[^>]*itemtype="http://schema.org/Article"[^>]*>', page)
    for i, row in enumerate(rows[1:]):
        before = rows[i] if i == 0 else rows[i]; labels = re.findall(r'<span[^>]*color:#737373[^>]*>\s*([A-Z]{3,12})\s*</span>', rows[0] if i == 0 else rows[i])
        section = labels[-1].title() if labels else (out['results'][-1]['section'] if out['results'] else None)
        href = re.search(r'<a href="([^"]+)"[^>]*itemprop="url"', row); name = re.search(r'<span itemprop="name">(.*?)</span>', row, re.S)
        pub = re.search(r'itemprop="publisher".*?<span itemprop="name">(.*?)</span>', row, re.S); desc = re.search(r'<div itemprop="description"[^>]*>(.*?)</div>', row, re.S)
        if not (href and name): continue
        url = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(href.group(1))).query).get('url', [''])[0]
        out['results'].append({'section': section, 'headline': clean(name.group(1)), 'publisher': clean(pub.group(1)) if pub else '', 'snippet': clean(desc.group(1)) if desc else '', 'url': url, 'host': registrable(urllib.parse.urlparse(url).netloc)})
    return out

def unit_text(result):
    """Exactly what the judge reads for one result: headline, publisher label, snippet (the same three text lines the email shows)."""
    return result['headline']+'\n'+result['publisher']+'\n'+result['snippet']

if __name__ == '__main__':
    for path in sys.argv[1:]: print(json.dumps({'file': path, **parse(open(path, 'rb').read())}, ensure_ascii=False))
