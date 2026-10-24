"""Peace BBC strict offline four-field extraction, QP and input/token commitment checks.

Run with the pinned private Python environment. This exporter does not perform RSA
verification, model inference, onchain extraction, or onchain tokenization. A gate
may pin its output hashes, but that policy is not proof of a general HTML/tokenizer
computation. Original fixtures, tokenizer compatibility copy and scores are read only.
"""
import argparse
import base64
import copy
import hashlib
import html
from html.parser import HTMLParser
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse

sys.dont_write_bytecode = True
BASE = Path.home() / '.local/share/means-of-prediction'
SWEEP = BASE / 'alerts-candidate-sweep-20261021'
REFERENCE = BASE / 'laya-alert-demo-20261021/reference'
DEFAULT_OUT = BASE / 'nobel-input-20261021'
REPO = Path(__file__).resolve().parents[3]
PINS = {
    'fixture': (SWEEP / 'nobel-fixtures.private.json', '521e6317c29b3a2610fd0c83e6cf6ea3929524ae63a4663e1944287cd29886ae'),
    'frozen': (SWEEP / 'shortlist-frozen.private.json', '1191792e1f5e0161ec82a350083b57b9b47a628b85e52292b466c8d30b1d9944'),
    'selection': (SWEEP / 'shortlist.private.json', 'e1d0372ed3556f9eaa3a346764596b9580f4c6d92dd3c7e08b60093fd1a08a6d'),
    'manifest': (REFERENCE / 'model-manifest.private.json', '9d0153f9b6d7b940ba0e934b988ceeb695344ff9f233547e8a960b2394cdd13a'),
    'priorFrozen': (REFERENCE / 'frozen.private.json', 'e00025dc7a6f133cc0fd8623236ea4d879f6a65daa8239cbd274df53d35bfb51'),
}


class BindingError(ValueError):
    pass


def require(ok, why):
    if not ok:
        raise BindingError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical(value):
    """Hash serialization: UTF-8 JSON, sorted keys, compact separators, no newline."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def unhex(value):
    require(isinstance(value, str) and value.startswith('0x'), 'hex prefix')
    return bytes.fromhex(value[2:])


def qp_window(body, start, length):
    """Match BodyParser.decode's bounded QP operation; validate both split edges."""
    require(isinstance(start, int) and isinstance(length, int), 'integer window')
    require(0 <= start <= len(body) and 0 < length <= 4096 and start + length <= len(body), 'window bounds')
    require(not (start > 0 and body[start - 1] == 61) and not (start > 1 and body[start - 2] == 61), 'QP start split')
    end = start + length
    out = bytearray()
    i = start
    while i < end:
        c = body[i]
        if c == 61:
            require(i + 2 < end, 'QP end split')
            pair = body[i + 1:i + 3]
            if pair == b'\r\n':
                i += 3
                continue
            require(re.fullmatch(b'[0-9A-Fa-f]{2}', pair) is not None, 'malformed QP escape')
            c = int(pair, 16)
            i += 2
        out.append(c)
        i += 1
    return bytes(out)


def clean_text(text):
    # HTMLParser decodes entities once; do not unescape a second time.
    require(not any(ord(c) < 32 and c not in '\t\r\n' for c in text), 'control character')
    return re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()


def publisher_url(href):
    """No label-based identity, open redirect host, repeated url= or double decode."""
    require(not any(c.isspace() or ord(c) < 32 for c in href), 'redirect whitespace')
    p = urllib.parse.urlsplit(href)
    require(p.scheme == 'https' and p.netloc in {'google.com', 'www.google.com'} and p.path == '/url', 'Google redirect origin')
    require(not p.fragment, 'redirect fragment')
    pairs = urllib.parse.parse_qsl(p.query, keep_blank_values=True, strict_parsing=True)
    require(len(pairs) == len({k for k, _ in pairs}), 'duplicate redirect parameter')
    urls = [v for k, v in pairs if k == 'url']
    require(len(urls) == 1 and urls[0], 'one publisher URL')
    target = urls[0]
    require(not any(c.isspace() or ord(c) < 32 for c in target), 'publisher URL whitespace')
    p = urllib.parse.urlsplit(target)
    require(p.scheme == 'https' and p.netloc == 'www.bbc.com' and p.path == '/audio/play/m00331hm', 'frozen publisher origin/path')
    require(not p.query and not p.fragment and p.username is None and p.password is None, 'publisher URL ambiguity')
    require(target == 'https://www.bbc.com/audio/play/m00331hm', 'canonical publisher URL')
    return target


class ArticlePrefix(HTMLParser):
    """Strict four-field prefix grammar, intentionally not a browser HTML parser.

    The frozen source window ends at description </div>, before layout ancestors
    close. Exactly one root Article and completed URL/headline/publisher/description
    are required; no recovery, scripts, comments, external text or next result.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = {}
        self.capture = None
        self.chunks = []
        self.finished = False
        self.started = False

    def handle_starttag(self, tag, attrs):
        require(not self.finished, 'content after description')
        require(tag in {'tr', 'td', 'div', 'span', 'a', 'b'}, 'unsupported HTML element')
        keys = [k for k, _ in attrs]
        require(len(keys) == len(set(keys)), 'duplicate HTML attribute')
        a = dict(attrs)
        require(set(a) <= {'style', 'href', 'itemprop', 'itemscope', 'itemtype'}, 'unsupported HTML attribute')
        if not self.started:
            require(tag == 'tr' and a.get('itemtype') == 'http://schema.org/Article' and 'itemscope' in a, 'Article root')
            self.started = True
        else:
            require(tag != 'tr' and a.get('itemtype') != 'http://schema.org/Article', 'second/nested Article')
        prop = a.get('itemprop')
        require(prop in {None, 'url', 'name', 'publisher', 'description'}, 'unknown/multiple itemprop')
        if 'itemtype' in a:
            require((tag == 'tr' and a['itemtype'] == 'http://schema.org/Article') or
                    (prop == 'publisher' and a['itemtype'] == 'http://schema.org/Organization'), 'unexpected itemtype')
        if prop == 'url':
            require(tag == 'a' and 'url' not in self.fields and self.capture is None and not any(x[1] == 'publisher' for x in self.stack), 'URL location/duplicate')
            require('href' in a, 'missing href')
            self.fields['url'] = publisher_url(a['href'])
        elif 'href' in a:
            raise BindingError('unexpected non-result href')
        if prop == 'publisher':
            require(tag == 'div' and 'url' in self.fields and 'headline' in self.fields and 'publisher' not in self.fields and self.capture is None, 'publisher location/duplicate')
            require(not any(x[1] == 'publisher' for x in self.stack), 'nested publisher')
        if prop == 'name':
            require(tag == 'span' and self.capture is None, 'name location')
            in_pub = any(x[1] == 'publisher' for x in self.stack)
            in_url = any(x[1] == 'url' for x in self.stack)
            require(in_pub != in_url, 'ambiguous name owner')
            field = 'publisher' if in_pub else 'headline'
            require(field not in self.fields, 'duplicate name')
            self.capture = (field, len(self.stack))
            self.chunks = []
        elif prop == 'description':
            require(tag == 'div' and self.capture is None and all(k in self.fields for k in ['headline', 'publisher', 'url']), 'description order/missing fields')
            require(not any(x[1] in {'url', 'publisher'} for x in self.stack), 'description owner')
            require('snippet' not in self.fields, 'duplicate description')
            self.capture = ('snippet', len(self.stack))
            self.chunks = []
        elif self.capture is not None:
            require(tag == 'b' and prop is None and not a, 'unexpected markup in text field')
        self.stack.append((tag, prop))

    def handle_endtag(self, tag):
        require(not self.finished and self.stack and self.stack[-1][0] == tag, 'mismatched HTML close')
        self.stack.pop()
        if self.capture is not None and self.capture[1] == len(self.stack):
            field = self.capture[0]
            text = clean_text(''.join(self.chunks))
            require(bool(text), 'empty field')
            self.fields[field] = text
            self.capture = None
            if field == 'snippet':
                self.finished = True

    def handle_data(self, data):
        if self.capture is not None:
            self.chunks.append(data)
        else:
            require(not data.strip(), 'query/banner/outside-field text')

    def handle_comment(self, data):
        raise BindingError('HTML comment')

    def handle_decl(self, decl):
        raise BindingError('HTML declaration')

    def handle_pi(self, data):
        raise BindingError('HTML processing instruction')

    def handle_startendtag(self, tag, attrs):
        raise BindingError('self-closing HTML')


def extract(decoded):
    text = decoded.decode('utf-8', errors='strict')
    require(not any(ord(c) < 32 and c not in '\t\r\n' for c in text), 'HTML control character')
    # Refuse HTMLParser's permissive recovery of unknown/unterminated entities.
    for m in re.finditer('&', text):
        entity = re.match(r'&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);', text[m.start():])
        require(entity is not None, 'unterminated entity')
        e = entity.group()
        require(html.unescape(e) != e, 'unknown entity')
    p = ArticlePrefix()
    p.feed(text)
    p.close()
    require(p.finished and p.capture is None and set(p.fields) == {'headline', 'publisher', 'snippet', 'url'}, 'incomplete four-field prefix')
    return dict(section='News', headline=p.fields['headline'], publisher=p.fields['publisher'],
                snippet=p.fields['snippet'], url=p.fields['url'], host='bbc.com')


def bind_source(source, frozen):
    body = unhex(source['bodyHex'])
    header = unhex(source['headerHex'])
    require(0 < len(body) <= 196608, 'fixed V2 fullbody size')
    require(sha(body) == source['canonicalBodySha256'].removeprefix('0x'), 'full canonical body hash')
    require(sha(header) == source['canonicalHeaderSha256'].removeprefix('0x'), 'canonical header hash')
    require(source['rawSha256'] == '0x' + frozen['rawSHA256'] and source['candidateID'] == frozen['id'] and source['resultIndex'] == frozen['resultIndex'], 'candidate identity')
    # Exactly one signed bh in this pinned canonical header, no l= partial body.
    sig = header.split(b'dkim-signature:', 1)
    require(len(sig) == 2, 'canonical DKIM signature')
    tags = [x.strip().split(b'=', 1) for x in sig[1].split(b';') if x.strip()]
    require(all(len(t) == 2 for t in tags) and len(tags) == len({t[0] for t in tags}), 'DKIM tag ambiguity')
    tags = dict(tags)
    require(b'l' not in tags and tags.get(b'c') == b'relaxed/relaxed', 'DKIM full body canonical mode')
    require(base64.b64decode(tags[b'bh'], validate=True) == hashlib.sha256(body).digest(), 'signed bh mismatch')
    decoded = qp_window(body, source['bodyOffset'], source['encodedLength'])
    require(decoded == unhex(source['decodedHex']) and len(decoded) == source['decodedLength'], 'decoded witness parity')
    unit = extract(decoded)
    require(unit == frozen['unit'], 'frozen four-field parity')
    return unit, decoded


def adversarial(source, frozen):
    decoded = unhex(source['decodedHex'])
    tests = []

    def reject(name, fn):
        try:
            fn()
        except (BindingError, ValueError, KeyError, UnicodeError):
            tests.append({'name': name, 'passed': True, 'expected': 'reject'})
        else:
            raise AssertionError('adversarial input accepted: ' + name)

    def changed(name, old, new):
        require(old in decoded, 'test mutation missing')
        reject(name, lambda: extract(decoded.replace(old, new, 1)))

    changed('missing publisher field', b'itemprop="publisher"', b'itemprop="other"')
    changed('missing snippet field', b'itemprop="description"', b'itemprop="other"')
    changed('duplicate attribute', b'itemprop="description"', b'itemprop="description" itemprop="description"')
    changed('nested Article cross-result mixing', b'<div itemprop="description"', b'<tr itemscope="" itemtype="http://schema.org/Article"><div itemprop="description"')
    changed('unclosed headline crosses publisher', b'Audio</span>', b'Audio')
    changed('mismatched snippet close', b'chief&nbsp;...</div>', b'chief&nbsp;...</span>')
    changed('duplicate publisher name', b'>BBC</span>', b'>BBC</span><span itemprop="name">Other</span>')
    changed('URL from untrusted redirect host', b'https://www.google.com/url?', b'https://www.google.com.evil.test/url?')
    changed('redirect userinfo spoof', b'https://www.google.com/url?', b'https://www.google.com@evil.test/url?')
    changed('redirect wrong path', b'/url?rct=', b'/search?rct=')
    changed('redirect repeated url parameter', b'&amp;ct=ga', b'&amp;url=https://evil.test/&amp;ct=ga')
    changed('publisher host suffix spoof', b'https://www.bbc.com/audio', b'https://www.bbc.com.evil.test/audio')
    changed('publisher userinfo spoof', b'https://www.bbc.com/audio', b'https://www.bbc.com@evil.test/audio')
    changed('publisher HTTP downgrade', b'url=https://www.bbc.com', b'url=http://www.bbc.com')
    changed('publisher double encoded URL', b'url=https://www.bbc.com', b'url=https%253A%252F%252Fwww.bbc.com')
    changed('unknown entity', b'&#39;', b'&unknown;')
    changed('unterminated entity', b'&nbsp;', b'&nbsp')
    changed('script text', b'<b>Nobel', b'<script>Nobel')
    reject('query banner outside Article', lambda: extract(b'new results for [Nobel]' + decoded))
    reject('second Article appended', lambda: extract(decoded + decoded))
    reject('share layout appended after complete description', lambda: extract(decoded + b'<div>Share</div>'))
    reject('partial description', lambda: extract(decoded[:-6]))
    reject('invalid UTF8', lambda: extract(decoded.replace(b'BBC Audio', b'BBC \xff')))
    body = unhex(source['bodyHex'])
    for name, mutate in [
        ('full body tamper outside window', lambda s: s.update(bodyHex='0x' + (body[:100] + bytes([body[100] ^ 1]) + body[101:]).hex())),
        ('canonical header tamper', lambda s: s.update(headerHex=s['headerHex'][:-2] + '30')),
        ('window offset tamper', lambda s: s.update(bodyOffset=s['bodyOffset'] + 1)),
        ('window length tamper', lambda s: s.update(encodedLength=s['encodedLength'] - 1)),
        ('decoded witness tamper', lambda s: s.update(decodedHex=s['decodedHex'][:-2] + '30')),
        ('cross-candidate result index', lambda s: s.update(resultIndex=1)),
    ]:
        tampered = copy.deepcopy(source)
        mutate(tampered)
        reject(name, lambda s=tampered: bind_source(s, frozen))
    altered = copy.deepcopy(frozen)
    altered['unit']['snippet'] = 'A field from another article'
    reject('cross-article frozen field replacement', lambda: bind_source(source, altered))
    for name, data, start, length in [
        ('QP first nibble start', b'x=3Dy', 2, 3), ('QP second nibble start', b'x=3Dy', 3, 2),
        ('QP escape split end', b'x=3Dy', 0, 3), ('QP softbreak split end', b'x=\r\ny', 0, 3),
        ('QP softbreak split start', b'x=\r\ny', 3, 2), ('QP bad hex', b'x=ZZy', 0, 5),
        ('window oversized', b'x' * 4097, 0, 4097), ('window negative', b'abc', -1, 1),
    ]:
        reject(name, lambda d=data, s=start, n=length: qp_window(d, s, n))
    require(qp_window(b'x=3Dy=\r\nz', 0, 9) == b'x=yz', 'QP positive')
    tests.append({'name': 'QP hex and softbreak positive', 'passed': True, 'expected': 'accept'})
    # Grammar normalization parity only. These variants do NOT get substituted
    # into the signed/frozen witness; its original byte hashes stay fixed.
    for name, variant in [
        ('equivalent numeric HTML apostrophe', decoded.replace(b'&#39;', b'&#x27;')),
        ('equivalent whitespace and NBSP', decoded.replace(b'year old', b'year\t\r\n old').replace(b'&nbsp;', b'&#160;')),
        ('single-pass entities', decoded.replace(b'BBC</span>', b'B&#66;C</span>')),
    ]:
        require(extract(variant) == frozen['unit'], name)
        tests.append({'name': name, 'passed': True, 'expected': 'same extracted fields, different witness bytes'})
    return tests



def gate_hashes(input_bytes, flat_ids, cast):
    def call(args):
        return subprocess.run([str(cast)] + args, check=True, capture_output=True, text=True).stdout.strip()
    encoded = call(['abi-encode', 'f(uint32[])', '[' + ','.join(map(str, flat_ids)) + ']'])
    return {'inputHash': call(['keccak', '0x' + input_bytes.hex()]), 'tokenIdsHash': call(['keccak', encoded]), 'tokenIdsABIHex': encoded, 'encoding': 'inputHash=keccak256(exactInputs UTF8 bytes); tokenIdsHash=keccak256(abi.encode(uint32[] q.ids+A.ids+B.ids)); no packed encoding'}


def input_audit(item, tokenizer, common, agent_module):
    """Rebuild semantics and every tensor; reject altered input, ids, masks and markers."""
    exact = Path(item['inputPath']).read_bytes()
    checks = []
    def verify(data, tokens, batch):
        require(sha(data) == item['inputSHA256'], 'exact input bytes')
        x = json.loads(data)
        require(list(x) == ['state', 'questions'] and list(x['state']) == ['subject', 'body'] and list(x['questions']) == ['q','A','B'], 'serialization order')
        require(x['state'] == item['state'] and x['questions'] == item['questions'], 'input values')
        built=[]
        for q in x['questions'].values():
            qi=agent_module.Agent._to_internal(q)
            ids, markers=common.build_sequence(tokenizer,x['state'],qi,320,160)
            built.append({'ids':ids,'markers':markers,'qtype':common.QTYPES[qi['t']]})
        require(built == [{k:t[k] for k in ['ids','markers','qtype']} for t in tokens], 'all token/marker/type values')
        tensors=common.collate_items([built],tokenizer.pad_token_id)
        require({k:v.tolist() for k,v in tensors.items() if hasattr(v,'tolist')} == batch, 'all batch tensors')
    verify(exact,item['tokens'],item['batch'])
    checks.append({'name':'exact input/all token IDs/all batch tensor parity','passed':True})
    def reject(label, data=exact, tokens=None, batch=None):
        try: verify(data,tokens if tokens is not None else item['tokens'],batch if batch is not None else item['batch'])
        except (BindingError, ValueError, KeyError, AssertionError): checks.append({'name':label,'passed':True})
        else: raise AssertionError('input mutation accepted: '+label)
    x=json.loads(exact)
    for label,change in [('state headline',lambda x:x['state'].update(subject='Different article')),('state body',lambda x:x['state'].update(body='Different article')),('A predicate',lambda x:x['questions']['A'].update(instructions='Different predicate'))]:
        v=copy.deepcopy(x);change(v);reject(label,json.dumps(v,ensure_ascii=False,separators=(',',':')).encode())
    reject('state dictionary order',json.dumps({'state':dict(reversed(list(x['state'].items()))),'questions':x['questions']},ensure_ascii=False,separators=(',',':')).encode())
    for n in range(3):
        for key in ['ids','markers','qtype']:
            ts=copy.deepcopy(item['tokens'])
            if key=='ids': ts[n][key][0]^=1
            elif key=='qtype': ts[n][key]+=1
            else:
                # Markers in pinned Laya are scalar positions, not masks.
                ts[n][key][0]+=1
            reject(f'question{n} '+key,tokens=ts)
    for key,value in item['batch'].items():
        bad=copy.deepcopy(item['batch']);v=bad[key]
        while isinstance(v[0],list):v=v[0]
        v[0]=1-v[0] if isinstance(v[0],bool) else v[0]+1
        reject('batch '+key,batch=bad)
    return checks
