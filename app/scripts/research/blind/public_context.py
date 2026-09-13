"""Public contender context from archived market questions, never outcome fields."""
import collections, datetime, hashlib, json, re, sqlite3
from experiment import ROOT,load,save

def family(question,deadline):
    m=re.fullmatch(r'Will (.+?) (be the .+|win the .+)\?',question)
    if not m or not re.search(r'nominee|primary',m[2],re.I):return None
    if re.search(r' by |margin|%|percent',m[2],re.I):return None
    try:year=datetime.datetime.fromisoformat(deadline.replace('Z','+00:00')).year
    except (AttributeError,ValueError):return None
    return (m[2].casefold(),year),m[1]

def prepare():
    if (ROOT/'public-contexts.json').exists():raise RuntimeError('Public context is already frozen; do not overwrite')
    public=sum([load(s+'-public-inputs.json') for s in ['train','validation','test']],[])
    # SQL projects public fields only. Settled outcome, prices, closedAt and
    # candidate scores are never returned or consulted by this enrichment step.
    conn=sqlite3.connect('file:'+str(ROOT.parents[1]/'nyt/mail.sqlite')+'?mode=ro',uri=True)
    sql="""SELECT id, json_extract(payload,'$.question'), json_extract(payload,'$.createdAt'), json_extract(payload,'$.endDate')
           FROM coverage_markets WHERE json_extract(payload,'$.question') LIKE 'Will %nominee%'
           OR json_extract(payload,'$.question') LIKE 'Will %primary%'"""
    rows=conn.execute(sql).fetchall();catalog=collections.defaultdict(list);by_id={}
    for id,q,created,deadline in rows:
        by_id[id]=(q,created,deadline);f=family(q,deadline)
        if f:catalog[f[0]].append({'name':f[1],'sourceMarketId':id,'publicQuestion':q,'createdAt':created,'endDate':deadline})
    contexts={}
    for market in public:
        row=by_id.get(market['marketId'])
        if not row:continue
        f=family(row[0],row[2])
        if not f:continue
        end=datetime.datetime.fromisoformat(row[2].replace('Z','+00:00'));cutoff=end-datetime.timedelta(days=30)
        candidates=[]
        for candidate in catalog[f[0]]:
            try:created=datetime.datetime.fromisoformat(candidate['createdAt'].replace('Z','+00:00'))
            except (AttributeError,ValueError):continue
            if created<=cutoff:candidates.append(candidate)
        candidates.sort(key=lambda x:(x['name'].casefold(),x['sourceMarketId']))
        # Keep one earliest public entry per name; don't rank by outcome/volume.
        unique={}
        for candidate in candidates:
            name=candidate['name'].casefold()
            if name not in unique or candidate['createdAt']<unique[name]['createdAt']:unique[name]=candidate
        if not 2<=len(unique)<=50:continue
        contexts[market['marketId']]={'kind':'public_contender_roster','candidateSelection':'Same public contest wording and scheduled year; public creation at least 30 days before the target scheduled end date; sorted by name.',
            'asOfPublicCutoff':cutoff.isoformat(),'contenders':[unique[name] for name in sorted(unique)],
            'containsSettledOutcome':False,'containsEmailEvidence':False,
            'limit':'Archived public metadata, not a contemporaneously captured roster. Absence from this list does not imply nonparticipation or defeat.'}
    conn.close();save(ROOT/'public-contexts.json',contexts)
    save(ROOT/'public-context-manifest.json',{'sqlProjection':sql,'contextMarkets':len(contexts),
        'sha256':hashlib.sha256((ROOT/'public-contexts.json').read_bytes()).hexdigest(),
        'newArm':'Publicly enriched blind generation; distinguish it from the original four-field benchmark.',
        'outcomeFieldsConsulted':False,'emailFieldsConsulted':False})
    print(json.dumps({'publicContexts':len(contexts),'contests':len({family(by_id[id][0],by_id[id][2])[0] for id in contexts})}))

if __name__=='__main__':prepare()
