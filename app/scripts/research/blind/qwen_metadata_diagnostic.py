"""Post-selection paired metadata diagnostic; never alters the scored cohort.

Preparation reads only the 12 explicitly identified development source files.
Inference waits for both independent fresh and supplemental evaluations.
"""
import argparse,collections,concurrent.futures,datetime,email.parser,email.policy,email.utils,hashlib,json,math,os,sqlite3,subprocess
from pathlib import Path
import qwen_round1 as q

ROOT=q.ROOT/'metadata-diagnostic'
REVIEW=q.ROOT.parent/'parallel-track-review-20260913/development-date-provenance.private.json'
MAIL=q.ROOT.parent.parent/'nyt'
SUPPLEMENT=q.ROOT.parent/'paired-natural-evaluation-20260913'
FIELDS=('subject','dkimDomain','signedDate','receivedAt')

def require(value,message):
    if not value:raise RuntimeError(message)

def once(name,value):q.once('metadata-diagnostic/'+name,value)
def load(name):return q.r.read(ROOT/name)

def timestamp(value):
    parsed=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
    require(parsed.tzinfo is not None,'Metadata timestamp lacks timezone')
    return parsed

def verified_metadata(raw,raw_sha,subject,metadata):
    """Link retained intake observation to exact raw headers; no new DNS/RSA."""
    require(hashlib.sha256(raw).hexdigest()==raw_sha,'Raw source hash differs')
    headers=email.parser.BytesHeaderParser(policy=email.policy.default).parsebytes(raw)
    require(len(headers.get_all('Date',[]))==1 and len(headers.get_all('Subject',[]))==1,'Ambiguous Date/Subject headers')
    require(str(headers['Subject'])==subject,'Parsed raw subject differs from intake')
    date=email.utils.parsedate_to_datetime(str(headers['Date']))
    require(date.tzinfo is not None and date==timestamp(metadata['date'])==timestamp(metadata['proof']['signedAt']),'Raw Date differs from intake date/proof')
    candidates=[]
    for sig in metadata['signatures']:
        if not (sig.get('result')=='pass' and sig.get('algorithm')=='rsa-sha256' and sig.get('bodyLengthLimited') is False):continue
        matches=[]
        for header in headers.get_all('DKIM-Signature',[]):
            tags={}
            for part in str(header).split(';'):
                if '=' not in part:continue
                key,value=part.split('=',1);key=key.strip().lower()
                require(key not in tags,'Duplicate DKIM tag')
                tags[key]=value.strip()
            if tags.get('d')==sig.get('domain') and tags.get('s')==sig.get('selector'):matches.append(tags)
        require(len(matches)==1,'Ambiguous raw/intake signature linkage')
        tags=matches[0]
        names=lambda value:[x.strip().lower() for x in value.split(':') if x.strip()]
        require(tags.get('a')=='rsa-sha256' and 'l' not in tags,'Raw signature algorithm/body coverage differs')
        # Intake records the existing signed fields; DKIM h may additionally
        # oversign absent duplicate fields. Resolve bottom-up consumption.
        available=collections.Counter(name.lower() for name in headers.keys());selected=[]
        # The signature under verification is not selected through its own h.
        available['dkim-signature']=max(0,available['dkim-signature']-1)
        for name in names(tags['h']):
            if available[name]:selected.append(name);available[name]-=1
        require(selected==names(sig['signedHeaders']),'Raw/intake selected signed headers differ')
        require({'date','subject'}<=set(names(tags['h'])),'Restored headers lack retained signature coverage')
        # Full raw hash is unchanged since the retained successful RSA intake.
        candidates.append(sig)
    domains={x['domain'] for x in candidates}
    require(len(domains)==1 and candidates,'No unique retained full-body signing domain')
    domain=next(iter(domains))
    require(metadata['proof']['domain']==domain,'Proof/signature domain differs')
    timestamp(metadata['receivedAt'])
    return {'subject':subject,'dkimDomain':domain,'signedDate':metadata['date'],'receivedAt':metadata['receivedAt']}, {
        'rawSha256':raw_sha,'retainedSignatureObservations':candidates,'rawDateSubjectMatched':True,
        'newRsaOrDnsVerification':False,'meaning':'Exact raw hash/header linkage to retained successful full-body RSA-SHA256 intake. Date and receipt do not prove event time.'}

def restore_missing(packet,values):
    require(set(values)==set(FIELDS),'Unexpected restored metadata field')
    restored=dict(packet);changed=[]
    for field in FIELDS:
        if not packet[field]:restored[field]=values[field];changed.append(field)
    require(q.evidence_text(restored)==q.evidence_text(packet),'Body changed during metadata restoration')
    require(all(restored[k]==v for k,v in packet.items() if k not in changed),'Populated value changed')
    return restored,changed

def replay_comparison(rows,development):
    groups=collections.defaultdict(list)
    for entry in rows:
        replay=entry['record']
        if replay['variant']=='original':groups[replay['kind']].append((replay,development[replay['caseId']]))
    def counts(pairs):
        both=[(a,b) for a,b in pairs if a['status']==b['status']=='completed' and q.valid_judgment(a['output']) and q.valid_judgment(b['output'])]
        return {'rows':len(pairs),'statusAgreement':sum(a['status']==b['status'] for a,b in pairs),'bothCompleted':len(both),
            'strictDecisionAgreement':sum(q.settlement(a['output'])==q.settlement(b['output']) for a,b in both),
            'factualDecisionAgreement':sum(a['output']['factualOutcome']==b['output']['factualOutcome'] for a,b in both),
            'canonicalParsedJsonAgreement':sum(a['output']==b['output'] for a,b in both)}
    return {'all':counts([pair for pairs in groups.values() for pair in pairs]),'byKind':{kind:counts(pairs) for kind,pairs in sorted(groups.items())},
        'qualification':'Original-packet replay versus its earlier development draw; decision/JSON agreement uses only both-completed pairs. Status agreement includes unavailable rows. This measures repeat variation, separately from restored-versus-contemporaneous-original transitions.'}

def execution_counts(records):
    attempted=[x for x in records if x['status']!='rule_unavailable']
    known=lambda value:type(value) in (int,float) and math.isfinite(value) and value>=0
    times=[x['seconds'] for x in attempted if known(x.get('seconds'))]
    fields={field:[x['usage'][field] for x in attempted if isinstance(x.get('usage'),dict) and known(x['usage'].get(field))] for field in ['prompt_tokens','completion_tokens']}
    return {'attemptedRequests':len(attempted),'unavailableRuleRows':len(records)-len(attempted),
        'knownInputTokens':sum(fields['prompt_tokens']),'knownOutputTokens':sum(fields['completion_tokens']),
        'requestsWithInputUsage':len(fields['prompt_tokens']),'attemptedWithoutInputUsage':len(attempted)-len(fields['prompt_tokens']),
        'requestsWithOutputUsage':len(fields['completion_tokens']),'attemptedWithoutOutputUsage':len(attempted)-len(fields['completion_tokens']),
        'summedRequestSeconds':sum(times),'requestsWithRecordedDuration':len(times),'attemptedWithoutDuration':len(attempted)-len(times),
        'qualification':'Known totals are lower bounds when usage/duration is missing; absent usage is not zero. Concurrent summed request time is not wall time.'}

def prepare():
    q.closed()
    review=q.r.read(REVIEW);items={x['caseId']:x for x in q.load(q.ITEMS)}
    affected=review['affectedItems'];email_ids=sorted({x['emailId'] for x in affected})
    require(len(affected)==28 and len(email_ids)==12,'Affected cohort differs')
    actual=[x for x in items.values() if x['kind']!='control' and not x['email']['signedDate']]
    require({x['caseId'] for x in actual}=={x['caseId'] for x in affected},'Missing-date cohort differs')
    once('protocol.json',{'declaredAt':q.r.now(),'pairs':28,'variants':['original','restored'],'rowsPerMethod':56,
        'methods':'Unique baseline plus final selected method; failed existing rule draws remain unavailable. No new Astra rules.',
        'fields':list(FIELDS),'policy':'Fill only empty allowed packet metadata, preserving every populated value and complete body. Verify exact raw SHA256, unique raw Date/Subject, retained successful full-body RSA-SHA256 signature/header linkage and intake timestamp agreement. No new RSA/DNS assertion.',
        'gate':'Run only after final method selection, independent fresh output audit, and supplemental evaluation completion. No reselection or further training.',
        'dispatch':'Each existing case gets one original and one restored request in a deterministic balanced variant order, grouped by original email hash. Four workers; no retries or history.',
        'scoring':'Only12 retrospective factual rows have diagnostic expected sides. Four weak and12 unlabeled rows remain unscored. Compare contemporaneous strict decisions, factual/quote diagnostics and failures. No original-rule settlement gold is created.',
        'reviewSha256':q.r.digest(REVIEW),'sourceItemsSha256':q.r.digest(q.ROOT/q.ITEMS)})
    db=sqlite3.connect('file:'+str(MAIL/'mail.sqlite')+'?mode=ro',uri=True)
    provenance={};packets={}
    try:
        for eid in email_ids:
            require(len(eid)==64 and all(c in '0123456789abcdef' for c in eid),'Invalid explicit source ID')
            row=db.execute('SELECT subject, metadata FROM messages WHERE id=?',(eid,)).fetchone()
            require(row is not None,'Development intake source unavailable')
            metadata=json.loads(row[1]);require(metadata==review['oldMetadataForAffectedSources'][eid],'Current intake metadata differs from prior review')
            raw_path=MAIL/'raw'/(eid+'.eml');values,audit=verified_metadata(raw_path.read_bytes(),eid,row[0],metadata)
            provenance[eid]={**audit,'rawPath':str(raw_path),'intakeMetadata':metadata,'intakeSubject':row[0]}
            packets[eid]=values
    finally:db.close()
    rows=[]
    for entry in sorted(affected,key=lambda x:x['caseId']):
        item=items[entry['caseId']];require(item['metadata']['emailId']==entry['emailId'],'Affected source identity differs')
        restored,changed=restore_missing(item['email'],packets[entry['emailId']])
        rows.append({'item':item,'original':item['email'],'restored':restored,'changedFields':changed})
    once('prepared.private.json',{'rows':rows,'provenance':provenance})
    once('prepared-seal.json',{'at':q.r.now(),'protocolSha256':q.r.digest(ROOT/'protocol.json'),'preparedSha256':q.r.digest(ROOT/'prepared.private.json'),
        'rows':28,'emailSources':12,'changedFields':dict(collections.Counter(k for x in rows for k in x['changedFields'])),'scoredCohortChanged':False})
    print(json.dumps({'preparedRows':28,'sources':12,'inferenceStarted':False,'changedFields':load('prepared-seal.json')['changedFields']}),flush=True)

def gates():
    selection=q.verify_selection();q.verify_challenge_freeze()
    require(Path(q.__file__).resolve().parent==q.ROOT/'sealed-source','Run the final sealed source copy')
    final=q.load('final-raw-output-audit.private.json')
    require(all('challenge' in final['methods'][m] for m in selection['freshMethods']),'Main independent fresh audit incomplete')
    require((SUPPLEMENT/'evaluation.private.json').exists(),'Supplemental evaluation incomplete')
    supplemental=q.r.read(SUPPLEMENT/'evaluation.private.json')
    require(supplemental['adapterFreezeSha256']==q.r.digest(SUPPLEMENT/'adapter-freeze.json'),'Supplemental completion seal differs')
    seal=load('prepared-seal.json')
    require(seal['protocolSha256']==q.r.digest(ROOT/'protocol.json') and seal['preparedSha256']==q.r.digest(ROOT/'prepared.private.json'),'Prepared diagnostic changed')
    return list(dict.fromkeys(['baseline',selection['selected']]))

def run(method):
    require(method in gates(),'Unselected metadata diagnostic method')
    data=load('prepared.private.json');runtime=q.load('runtime.json');prompt=(q.ROOT/(method+'-judge.txt')).read_text()
    rules={x['marketId']:x for x in q.load('methods/'+method+'/rules.json')};directory=ROOT/'methods'/method
    development={x['caseId']:x for x in q.load('methods/'+method+'/development-judgments.private.json')}
    tasks=[];requests=[]
    for entry in data['rows']:
        item=entry['item'];rule=rules[item['marketId']]
        variants=['original','restored'] if int(item['caseId'][:2],16)%2==0 else ['restored','original']
        for order,variant in enumerate(variants):
            key=item['caseId']+'/'+variant
            request=q.judge_request(rule['output'],q.restore_email(entry[variant]),prompt,runtime) if rule['status']=='completed' else None
            if variant=='original' and request is not None:
                require(q.r.read(Path(development[item['caseId']]['directory'])/'request.json')==request,'Repeated original request differs from development draw')
            tasks.append((entry,variant,order,key,request))
            if request is not None:requests.append({'caseId':key,'request':request})
    request_path=directory/'requests.private.json'
    if request_path.exists():require(q.r.read(request_path)=={'identifier':runtime['identifier'],'requests':requests},'Diagnostic requests changed')
    else:once('methods/'+method+'/requests.private.json',{'identifier':runtime['identifier'],'requests':requests})
    preflight_path=directory/'preflight.json'
    if not preflight_path.exists():subprocess.run(['node',str(Path(__file__).with_name('qwen_preflight.mjs')),str(request_path),str(preflight_path)],check=True)
    preflight=q.r.read(preflight_path);q.verify_preflight_runtime(preflight,runtime)
    require(preflight['allFullInputsFit'] and preflight['inputSha256']==q.r.digest(request_path),'Full diagnostic preflight failed')
    counts={x['caseId']:x['inputTokens'] for x in preflight['counts']}
    require(set(counts)=={x['caseId'] for x in requests},'Diagnostic preflight coverage differs')
    tasks.sort(key=lambda t:(q.r.hash_value(t[0]['original']),t[0]['item']['marketId'],t[0]['item']['caseId'],t[2]))
    dispatch={'workers':4,'order':[x[3] for x in tasks],'requestsSha256':q.r.digest(request_path)}
    path=directory/'dispatch.json'
    if path.exists():require(q.r.read(path)==dispatch,'Diagnostic dispatch changed')
    else:once('methods/'+method+'/dispatch.json',dispatch)
    def one(task):
        entry,variant,_,key,request=task;item=entry['item'];d=directory/'calls'/key
        result=q.local_call(request,d) if request is not None else {'status':'rule_unavailable','output':None}
        record={'caseId':item['caseId'],'marketId':item['marketId'],'kind':item['kind'],'variant':variant,'trial':1,'directory':str(d),**result}
        if request is not None:
            import qwen_final_audit as audit
            require(Path(audit.__file__).resolve().parent==q.ROOT/'sealed-source','Use the sealed raw-response auditor')
            audit.verify_local(record,request)
            if result['status']=='completed':require(result['usage']['prompt_tokens']==counts[key],'Diagnostic input token count differs')
        return {'record':record,'score':q.score_record({**item,'email':entry[variant]},record)}
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for future in concurrent.futures.as_completed([pool.submit(one,t) for t in tasks]):
            rows.append(future.result());print(json.dumps({'metadataMethod':method,'completedRows':len(rows),'total':56}),flush=True)
    once('methods/'+method+'/results.private.json',rows)
    paired={}
    for row in rows:paired.setdefault(row['record']['caseId'],{})[row['record']['variant']]=row['score']
    summary={'at':q.r.now(),'method':method,'rows':len(rows),'statuses':dict(collections.Counter(x['record']['status'] for x in rows)),
        'strictTransitions':dict(collections.Counter(x['original']['settlementOutcome']+'→'+x['restored']['settlementOutcome'] for x in paired.values())),
        'factual':{v:{'rows':12,'rawPasses':sum(x[v]['factualPass'] is True for x in paired.values()),'groundedPasses':sum(x[v]['groundedFactualPass'] is True for x in paired.values())} for v in ['original','restored']},
        'originalReplay':replay_comparison(rows,development),'developmentJudgmentsSha256':q.r.digest(q.ROOT/'methods'/method/'development-judgments.private.json'),
        'execution':execution_counts([x['record'] for x in rows]),
        'resultsSha256':q.r.digest(directory/'results.private.json'),'selectionUnchanged':True,'qualification':'Contemporaneous paired development diagnostic; no independent original-rule settlement gold, no reselection or input replacement. Separate calls occur after the main final usage snapshot and are accounted here.'}
    once('methods/'+method+'/summary.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':
    os.umask(0o077);parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run']);parser.add_argument('--method');args=parser.parse_args()
    if args.mode=='prepare':prepare()
    else:run(args.method)
