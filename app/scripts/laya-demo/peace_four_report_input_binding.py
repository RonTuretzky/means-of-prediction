"""Strict OFFCHAIN four-field extraction for the four fixed Peace BBC/CNN/ABC-Australia/RFI windows.

This is not an onchain tokenizer or general browser HTML implementation. The
candidate-bound grammar rejects ambiguous fields/URLs and compares its results
against the unmodified original-mail parser and a pre-inference freeze. Full-body
DKIM/RSA and MIME authentication are independently checked by the evidence gate.
"""
import copy
from pathlib import Path
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import subprocess
import urllib.parse


class BindingError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise BindingError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def qp_window(body, start, length):
    require(isinstance(start, int) and isinstance(length, int), 'integer window')
    require(0 <= start <= len(body) and 0 < length <= 4096 and start + length <= len(body), 'window bounds')
    require(not (start > 0 and body[start - 1] == 61) and not (start > 1 and body[start - 2] == 61), 'QP start split')
    out = bytearray()
    i, end = start, start + length
    while i < end:
        c = body[i]
        if c == 61:
            require(i + 2 < end, 'QP end split')
            pair = body[i + 1:i + 3]
            if pair == b'\r\n':
                i += 3
                continue
            require(re.fullmatch(b'[0-9a-fA-F]{2}', pair) is not None, 'malformed QP')
            c = int(pair, 16)
            i += 2
        out.append(c)
        i += 1
    return bytes(out)


def redirect_target(href, expected_url):
    require(not any(c.isspace() or ord(c) < 32 for c in href), 'redirect whitespace')
    p = urllib.parse.urlsplit(href)
    require(p.scheme == 'https' and p.netloc in {'www.google.com', 'google.com'} and p.path == '/url' and not p.fragment, 'Google redirect origin')
    pairs = urllib.parse.parse_qsl(p.query, keep_blank_values=True, strict_parsing=True)
    require(len(pairs) == len({k for k, _ in pairs}), 'duplicate redirect parameter')
    urls = [v for k, v in pairs if k == 'url']
    require(len(urls) == 1, 'unique target URL')
    target = urls[0]
    p = urllib.parse.urlsplit(target)
    require(p.scheme == 'https' and p.netloc in {'www.bbc.com', 'www.cnn.com', 'www.abc.net.au', 'www.rfi.fr'} and p.username is None and not p.query and not p.fragment, 'publisher URL origin')
    require(target == expected_url, 'exact publisher URL')
    return target


class ArticlePrefix(HTMLParser):
    def __init__(self, expected_url):
        super().__init__(convert_charrefs=True)
        self.expected_url = expected_url
        self.stack = []
        self.fields = {}
        self.capture = None
        self.chunks = []
        self.finished = False
        self.decorations = 0

    def handle_starttag(self, tag, attrs):
        require(not self.finished, 'content after description')
        require(tag in {'tr', 'td', 'div', 'span', 'a', 'b', 'table', 'link'}, 'unsupported HTML element')
        keys = [k for k, _ in attrs]
        require(len(keys) == len(set(keys)), 'duplicate attribute')
        a = dict(attrs)
        require(not any(k.startswith('on') for k in a), 'event attribute')
        prop = a.get('itemprop')
        if not self.stack:
            require(tag == 'tr' and a.get('itemtype') == 'http://schema.org/Article' and 'itemscope' in a and not self.fields, 'Article root')
        else:
            require(a.get('itemtype') != 'http://schema.org/Article', 'nested Article')
        decoration = bool(self.stack and self.stack[-1][2])
        if not decoration and tag == 'a' and 'href' in a and prop is None:
            require(not self.fields and self.capture is None and self.decorations == 0, 'unexpected extra result anchor')
            redirect_target(a['href'], self.expected_url)
            self.decorations += 1
            decoration = True
        if decoration:
            require(set(a) <= {'style', 'href', 'align', 'height', 'width', 'valign', 'itemprop'}, 'decorative attribute')
            require(prop is None or (tag == 'link' and prop == 'image'), 'semantic field in thumbnail')
            require(tag in {'a', 'table', 'tr', 'td', 'div', 'link'}, 'thumbnail element')
            if 'href' in a and tag != 'a':
                p = urllib.parse.urlsplit(a['href'])
                require(tag == 'link' and p.scheme == 'https' and p.hostname in {'encrypted-tbn0.gstatic.com', 'encrypted-tbn1.gstatic.com', 'encrypted-tbn2.gstatic.com', 'encrypted-tbn3.gstatic.com'}, 'thumbnail image URL')
            if tag == 'a':
                require(not any(x[0] == 'a' and x[2] for x in self.stack), 'nested decorative anchor')
            if tag == 'link':
                return  # HTML void element, never captures article text.
        else:
            require(set(a) <= {'style', 'href', 'itemprop', 'itemtype', 'itemscope'}, 'unsupported attribute')
            require(tag not in {'table', 'link'} and (tag != 'tr' or not self.stack), 'layout nesting outside thumbnail')
            require(prop in {None, 'url', 'name', 'publisher', 'description'}, 'unknown itemprop')
            if 'itemtype' in a:
                require((tag == 'tr' and a['itemtype'] == 'http://schema.org/Article') or (prop == 'publisher' and a['itemtype'] == 'http://schema.org/Organization'), 'unexpected itemtype')
            if prop == 'url':
                require(tag == 'a' and 'url' not in self.fields and self.capture is None and not any(x[1] == 'publisher' for x in self.stack), 'URL owner/duplicate')
                self.fields['url'] = redirect_target(a.get('href', ''), self.expected_url)
            elif 'href' in a:
                raise BindingError('unexpected href')
            if prop == 'publisher':
                require(tag == 'div' and 'headline' in self.fields and 'publisher' not in self.fields and self.capture is None and not any(x[1] == 'publisher' for x in self.stack), 'publisher owner/duplicate')
            if prop == 'name':
                require(tag == 'span' and self.capture is None, 'name owner')
                in_pub = any(x[1] == 'publisher' for x in self.stack)
                in_url = any(x[1] == 'url' for x in self.stack)
                require(in_pub != in_url, 'ambiguous name owner')
                field = 'publisher' if in_pub else 'headline'
                require(field not in self.fields, 'duplicate name')
                self.capture = (field, len(self.stack))
                self.chunks = []
            elif prop == 'description':
                require(tag == 'div' and self.capture is None and all(k in self.fields for k in ['url', 'headline', 'publisher']), 'description order')
                require(not any(x[1] in {'publisher', 'url'} for x in self.stack), 'description owner')
                self.capture = ('snippet', len(self.stack))
                self.chunks = []
            elif self.capture is not None:
                require(tag == 'b' and not a, 'unsupported field markup')
        self.stack.append((tag, prop, decoration))

    def handle_endtag(self, tag):
        require(not self.finished and self.stack and self.stack[-1][0] == tag, 'mismatched close')
        self.stack.pop()
        if self.capture is not None and self.capture[1] == len(self.stack):
            field = self.capture[0]
            text = re.sub(r'\s+', ' ', ''.join(self.chunks).replace('\xa0', ' ')).strip()
            require(bool(text), 'empty field')
            self.fields[field] = text
            self.capture = None
            if field == 'snippet':
                self.finished = True

    def handle_data(self, data):
        if self.capture is not None:
            self.chunks.append(data)
        else:
            require(not data.strip(), 'outside-field text/query banner')

    def handle_comment(self, data):
        require(self.stack and self.stack[-1][2] and data.startswith('[if gte mso 9]') and 'itemprop' not in data.lower() and 'schema.org/Article' not in data, 'unsupported HTML comment')

    def handle_decl(self, decl):
        raise BindingError('HTML declaration')

    def handle_pi(self, data):
        raise BindingError('HTML processing instruction')

    def handle_startendtag(self, tag, attrs):
        raise BindingError('self-closing element')


def extract(decoded, expected_url):
    text = decoded.decode('utf-8', errors='strict')
    require(not any(ord(c) < 32 and c not in '\t\r\n' for c in text), 'control character')
    for m in re.finditer('&', text):
        entity = re.match(r'&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);', text[m.start():])
        require(entity is not None and html.unescape(entity.group()) != entity.group(), 'unknown/unterminated entity')
    p = ArticlePrefix(expected_url)
    p.feed(text)
    p.close()
    require(p.finished and p.capture is None and set(p.fields) == {'headline', 'publisher', 'snippet', 'url'}, 'incomplete four fields')
    host = urllib.parse.urlsplit(p.fields['url']).hostname.removeprefix('www.')
    return dict(section='News', headline=p.fields['headline'], publisher=p.fields['publisher'], snippet=p.fields['snippet'], url=p.fields['url'], host=host)


def bind_window(source):
    body = bytes.fromhex(source['bodyHex'].removeprefix('0x'))
    require(0 < len(body) <= 196608 and sha(body) == source['canonicalBodySha256'].removeprefix('0x'), 'complete body pin')
    decoded = qp_window(body, source['bodyOffset'], source['encodedLength'])
    require(decoded == bytes.fromhex(source['decodedHex'].removeprefix('0x')), 'decoded window pin')
    unit = extract(decoded, source['evidence']['canonicalURL'])
    require(unit == source['evidence']['result'], 'four-field parity')
    return unit, decoded


def adversarial(sources):
    tests = []
    def reject(name, fn):
        try:
            fn()
        except (BindingError, ValueError, KeyError, UnicodeError):
            tests.append({'name': name, 'passed': True, 'expected': 'reject'})
        else:
            raise AssertionError('accepted adversarial input: ' + name)
    for name, s in sources.items():
        u, d = bind_window(s)
        url = u['url']
        edits = [
            ('publisher missing', b'itemprop="publisher"', b'itemprop="other"'),
            ('description missing', b'itemprop="description"', b'itemprop="other"'),
            ('duplicate attribute', b'itemprop="description"', b'itemprop="description" itemprop="description"'),
            ('nested Article', b'<div itemprop="description"', b'<tr itemtype="http://schema.org/Article"><div itemprop="description"'),
            ('Google host suffix spoof', b'https://www.google.com/url?', b'https://www.google.com.evil.test/url?'),
            ('Google userinfo spoof', b'https://www.google.com/url?', b'https://www.google.com@evil.test/url?'),
            ('duplicate target query', b'&amp;ct=ga', b'&amp;url=https://evil.test/&amp;ct=ga'),
            ('publisher userinfo spoof', url.encode(), url.replace('https://', 'https://evil.test@').encode()),
            ('publisher protocol downgrade', url.encode(), url.replace('https://', 'http://').encode()),
            ('double encoded target URL', url.encode(), urllib.parse.quote(urllib.parse.quote(url, safe=''), safe='').encode()),
            ('description mismatched close', b'&nbsp;...</div>', b'&nbsp;...</span>'),
            ('unknown entity', b'&nbsp;', b'&unknown;'),
            ('unterminated entity', b'&nbsp;', b'&nbsp'),
            ('script in field', b'<b>', b'<script>'),
        ]
        for label, old, new in edits:
            require(old in d, 'missing test needle: ' + label)
            reject(name + ': ' + label, lambda d=d, old=old, new=new: extract(d.replace(old, new), url))
        reject(name + ': duplicate headline', lambda: extract(d.replace(b'</span> </a>', b'</span><span itemprop="name">Other</span> </a>', 1), url))
        reject(name + ': partial snippet', lambda: extract(d[:-6], url))
        reject(name + ': query banner', lambda: extract(b'new results for [Nobel]'  + d, url))
        reject(name + ': cross article concatenation', lambda: extract(d + d, url))
        reject(name + ': trailing share layout', lambda: extract(d + b'<div>Share</div>', url))
        reject(name + ': invalid UTF8', lambda: extract(d.replace(b'Nobel', b'\xff', 1), url))
        body = bytes.fromhex(s['bodyHex'][2:])
        import copy
        for label, change in [
            ('fullbody outside window tamper', {'bodyHex': '0x' + (body[:100] + bytes([body[100] ^ 1]) + body[101:]).hex()}),
            ('window offset tamper', {'bodyOffset': s['bodyOffset'] + 1}),
            ('window length tamper', {'encodedLength': s['encodedLength'] - 1}),
            ('decoded witness tamper', {'decodedHex': s['decodedHex'][:-2] + '30'}),
        ]:
            bad = copy.deepcopy(s)
            bad.update(change)
            reject(name + ': ' + label, lambda bad=bad: bind_window(bad))
        for field in ['headline', 'publisher', 'snippet', 'url']:
            bad = copy.deepcopy(s)
            bad['evidence']['result'][field] = 'field from another article'
            reject(name + ': mixed frozen ' + field, lambda bad=bad: bind_window(bad))
        equivalent = d.replace(b'&nbsp;', b'&#160;').replace(b'who solved', b'who\t\r\n solved').replace(b'&#39;', b'&#x27;')
        require(extract(equivalent, url) == u, name + ': normalization parity')
        tests.append({'name': name + ': entities/whitespace normalization', 'passed': True, 'expected': 'same fields; original witness unchanged'})
        if name == 'cnn':
            bad = d.replace(b'itemprop="image"', b'itemprop="name"')
            reject('cnn: semantic name hidden in thumbnail', lambda: extract(bad, url))
            bad = d.replace(b'<!--[if gte mso 9]>', b'<!--[if gte mso 9]><span itemprop="name">Other')
            reject('cnn: semantic name hidden in conditional comment', lambda: extract(bad, url))
        # U+200B is real preserved source text, not whitespace to silently delete.
        require(u['snippet'] == s['evidence']['result']['snippet'], 'all original characters preserved')
    for label, d, start, length in [('first nibble', b'x=3Dy', 2, 3), ('second nibble', b'x=3Dy', 3, 2), ('split escape end', b'x=3Dy', 0, 3), ('split softbreak end', b'x=\r\ny', 0, 3), ('split softbreak start', b'x=\r\ny', 3, 2), ('bad hex', b'x=ZZy', 0, 5), ('oversize', b'x'*4097, 0, 4097), ('negative offset', b'abc', -1, 1)]:
        reject('QP ' + label, lambda d=d, start=start, length=length: qp_window(d, start, length))
    require(qp_window(b'x=3Dy=\r\nz', 0, 9) == b'x=yz', 'QP positive')
    tests.append({'name': 'QP hex/softbreak positive', 'passed': True, 'expected': 'accept'})
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
