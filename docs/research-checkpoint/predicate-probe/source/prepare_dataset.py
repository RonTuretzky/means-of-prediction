"""Seal an event/email-disjoint NYT prompt-training, validation and test split."""
import collections, datetime, hashlib, html, json, os, re, sqlite3
from pathlib import Path
BASE=Path.home()/'.local/share/means-of-prediction'
OUT=BASE/'slides/astra-blind-20260910'
OLD=BASE/'slides/blind-regex-20260910'
digest=lambda b: hashlib.sha256(b).hexdigest()

def source_window(email, fact):
    anchor=email['text'][fact['normalizedBodyOffset']:fact['normalizedBodyOffset']+fact['normalizedBodyLength']]
    source=email['html']
    # Keep source offsets: blank tags instead of collapsing them.
    visible=re.sub(r'<[^>]*>',lambda m:' '*len(m[0]),source)
    tokens=list(re.finditer(r'[A-Za-z0-9]+',visible))
    words=[m[0].lower() for m in tokens]
    needle=re.findall(r'[a-z0-9]+',anchor.lower())
    found=None
    for size in [8,6,4]:
        for start in range(max(1,len(needle)-size+1)):
            fragment=needle[start:start+size]
            if len(fragment)<size:continue
            for i in range(len(words)-size+1):
                if words[i:i+size]==fragment:
                    a=max(0,tokens[i].start()-700)
                    b=min(len(source),tokens[min(len(tokens)-1,i+max(len(needle),40))].end()+700)
                    found=source[a:b][:10000];break
            if found:break
        if found:break
    return {'readableEvidence':anchor,'htmlSourceExcerpt':found,
            'sourceExcerptLocated':found is not None}

def prepare():
    os.umask(0o077);OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (OUT/'split-manifest.json').exists():raise RuntimeError('Existing split is immutable; inspect or use a new experiment directory')
    audit=json.loads((BASE/'nyt/reviewed-audit.json').read_text())
    corpus=json.loads((OLD/'corpus.json').read_text());emails={e['id']:e for e in corpus}
    facts={f['key']:f for f in audit['facts']};parent={k:k for k in facts}
    def root(k):
        while parent[k]!=k:k=parent[k]
        return k
    def union(a,b):parent[root(b)]=root(a)
    by_email=collections.defaultdict(list)
    for f in facts.values():by_email[f['emailId']].append(f['key'])
    for keys in by_email.values():
        for k in keys[1:]:union(keys[0],k)
    # All 2026 US Open outcomes are one related event, including earlier/later
    # rounds. Shared newsletters pull their other stories into this component.
    tennis=[]
    for finding in audit['findings']:
        if re.search(r'U[.]?S[.]? Open',finding['question']+' '+finding['rules'],re.I):tennis.append(finding['fact'])
    for k in tennis[1:]:union(tennis[0],k)
    components=collections.defaultdict(list)
    for k in facts:components[root(k)].append(k)
    groups=[]
    for keys in components.values():
        group_id=digest('|'.join(sorted(keys)).encode())
        findings=[r for r in audit['findings'] if r['fact'] in keys]
        groups.append({'id':group_id,'factKeys':sorted(keys),'emailIds':sorted({facts[k]['emailId'] for k in keys}),
                       'marketIds':sorted({r['marketId'] for r in findings}),'marketCount':len(findings)})
    # Place the giant correlated tournament component in training, then assign
    # remaining groups using a fixed hash order, without consulting performance.
    largest=max(groups,key=lambda g:g['marketCount']);remaining=[g for g in groups if g is not largest]
    remaining.sort(key=lambda g:digest(('nyt-astra-split-v1|'+g['id']).encode()))
    for i,g in enumerate(remaining):g['split']='test' if i<3 else 'validation' if i<6 else 'train'
    largest['split']='train'
    group_for={k:g for g in groups for k in g['factKeys']}
    conn=sqlite3.connect('file:'+str(BASE/'nyt/mail.sqlite')+'?mode=ro',uri=True)
    cases=[]
    for finding in audit['findings']:
        market=json.loads(conn.execute('SELECT payload FROM coverage_markets WHERE id=?',(finding['marketId'],)).fetchone()[0])
        if len(market['outcomes'])!=2 or finding['emailId'] not in emails:raise RuntimeError('Unexpected benchmark case')
        if digest(finding['rules'].encode())!=finding['rulesSha256']:raise RuntimeError('Rules hash mismatch')
        g=group_for[finding['fact']]
        cases.append({'marketId':finding['marketId'],'groupId':g['id'],'split':g['split'],
            'publicInput':{'marketId':finding['marketId'],'question':finding['question'],'rules':finding['rules'],'outcomeLabels':market['outcomes']},
            'expectedOutcome':finding['outcome'],'emailId':finding['emailId'],'factKey':finding['fact'],
            'availableByClosure':finding['availableByClosure'],'closedAt':finding['closedAt']})
    conn.close()
    # Only training excerpts are materialized in a model-visible packet.
    train=[]
    for case in cases:
        if case['split']!='train':continue
        train.append({**case,**source_window(emails[case['emailId']],facts[case['factKey']])})
    manifest={'createdAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'splitSeed':'nyt-astra-split-v1','groups':groups,'counts':dict(collections.Counter(c['split'] for c in cases)),
        'corpusSha256':digest((OLD/'corpus.json').read_bytes()),'auditSha256':digest((BASE/'nyt/reviewed-audit.json').read_bytes()),
        'instructionAmendment':'User authorized NYT email-result feedback for prompt optimization. Only training emails/results may enter optimization; validation chooses the method and final test stays hidden.',
        'selectionLimit':'149 retrospectively selected known factual matches. Group-disjoint prompt holdout, not random market coverage or a new externally pristine benchmark.',
        'testPolicy':'Do not evaluate test until prompt/effort/pass selection and final generations are frozen. Do not feed test emails, outcomes or results to any model.'}
    for split in ['train','validation','test']:
        case_set=[c for c in cases if c['split']==split]
        (OUT/(split+'-cases.private.json')).write_text(json.dumps(case_set,indent=2))
        (OUT/(split+'-public-inputs.json')).write_text(json.dumps([c['publicInput'] for c in case_set],indent=2))
    (OUT/'training-examples.json').write_text(json.dumps(train,ensure_ascii=False,indent=2))
    (OUT/'split-manifest.json').write_text(json.dumps(manifest,indent=2))
    for a in ['train','validation','test']:
        for b in ['train','validation','test']:
            if a==b:continue
            assert not {c['emailId'] for c in cases if c['split']==a}&{c['emailId'] for c in cases if c['split']==b}
    print(json.dumps({'counts':manifest['counts'],'groups':len(groups),'trainingExcerptsLocated':sum(c['sourceExcerptLocated'] for c in train),'trainingCases':len(train)}))

if __name__=='__main__':prepare()
