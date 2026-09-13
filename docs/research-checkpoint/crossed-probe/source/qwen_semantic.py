"""Deterministic complete semantic HTML rendering for private email research.

No excerpts, URL removal, footer removal, or length clipping. This is a declared
research representation, not an authenticated onchain rendering protocol.
"""
from html.parser import HTMLParser
import hashlib,json,re,urllib.parse

VERSION='mop-complete-semantic-html-v2-routing-references'
BLOCKS=set('address article aside blockquote caption dd details div dl dt fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section summary table tbody td tfoot th thead tr ul'.split())
VOID=set('area base br col embed hr img input link meta param source track wbr'.split())

def normalize(value):return re.sub(r'\s+',' ',value).strip()

class Renderer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output=[];self.suppressed=None;self.links=[];self.fragments=[];self.attributes=[]
        self.omitted={'script':0,'style':0};self.comments=0
        self.url_references={}
    def url_value(self,value):
        u=urllib.parse.urlsplit(value)
        if u.hostname=='nl.nytimes.com' and re.match(r'^/[fq]/',u.path) and re.search(r'[A-Za-z0-9_-]{64,}',value):
            sha=hashlib.sha256(value.encode()).hexdigest();key=sha[:16]
            existing=self.url_references.get(key)
            if existing and existing['url']!=value:raise ValueError('Routing reference collision')
            self.url_references[key]={'url':value,'sha256':sha,'destinationKnown':False}
            # The full routing URL remains in the immutable sidecar. Its opaque
            # delivery bytes are not presented as an article destination.
            return f'{u.scheme}://{u.netloc}/[opaque-route:{key};destination-unknown]'
        return value
    def marker(self,kind,attributes):
        if attributes:
            shown={k:self.url_value(v) if k in ['href','src','data'] else v for k,v in attributes.items()}
            text='['+kind+' '+json.dumps(shown,ensure_ascii=False,sort_keys=True)+']'
            self.output.extend([' ',text,' ']);self.attributes.append({'kind':kind,'values':attributes})
    def handle_starttag(self,tag,attrs):
        tag=tag.lower();a=dict(attrs)
        if self.suppressed:return
        if tag in ['script','style']:self.suppressed=tag;return
        if tag in BLOCKS or tag=='br':self.output.append('\n')
        if tag=='a':self.links.append({k:a[k] for k in ['href','title'] if a.get(k)})
        elif tag=='img':self.marker('IMAGE',{k:a[k] for k in ['alt','title','src','srcset','aria-label','aria-description'] if a.get(k)})
        elif tag in ['audio','video','source','track','iframe','object','embed']:
            self.marker(tag.upper(),{k:v for k,v in a.items() if k in ['src','srcset','data','title','aria-label','aria-description'] and v})
        else:self.marker('ACCESSIBLE',{k:a[k] for k in ['title','aria-label','aria-description','alt'] if a.get(k)})
        if tag=='input':self.marker('INPUT',{k:a[k] for k in ['type','value','placeholder'] if a.get(k)})
    def handle_endtag(self,tag):
        tag=tag.lower()
        if self.suppressed:
            if tag==self.suppressed:self.suppressed=None
            return
        if tag=='a' and self.links:self.marker('LINK',self.links.pop())
        if tag in BLOCKS:self.output.append('\n')
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_data(self,data):
        if self.suppressed:self.omitted[self.suppressed]+=len(data);return
        self.output.append(data)
        if normalize(data):self.fragments.append(normalize(data))
    def handle_comment(self,data):self.comments+=len(data)
    def finish(self):
        while self.links:self.marker('LINK',self.links.pop())
        text='\n'.join(line for line in (normalize(x) for x in ''.join(self.output).splitlines()) if line)
        whole=normalize(text)
        missing=[x for x in self.fragments if x not in whole]
        if missing:raise ValueError('Semantic renderer omitted body text fragments')
        if self.suppressed:raise ValueError('Unclosed script/style: completeness cannot be established')
        return text,{'version':VERSION,'semanticCharacters':len(text),'textFragments':len(self.fragments),
            'allNonScriptStyleTextFragmentsPresent':True,'preservedAttributeMarkers':len(self.attributes),
            'omittedNonContentCharacters':self.omitted,'omittedCommentCharacters':self.comments,
            'opaqueRoutingReferences':self.url_references,
            'policy':'All text outside script/style, including hidden preheaders and footers, is retained. Whitespace is normalized. Opaque nl.nytimes.com /f/ and /q/ delivery routes use origin+stable reference with destination explicitly unknown; full URLs are preserved in the sidecar. Other links and image/accessibility descriptions retain complete attribute values. No clipping or remote resources are fetched.'}

def render(html):
    parser=Renderer();parser.feed(html);parser.close();text,audit=parser.finish()
    audit.update({'sourceHtmlCharacters':len(html),'sourceHtmlSha256':hashlib.sha256(html.encode()).hexdigest(),
        'semanticSha256':hashlib.sha256(text.encode()).hexdigest()})
    return text,audit
