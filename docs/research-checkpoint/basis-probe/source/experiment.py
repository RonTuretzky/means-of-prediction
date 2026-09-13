"""Resumable Astra/NYT experiment. Progress logs contain counters, not email text."""
import argparse, collections, concurrent.futures, datetime, hashlib, json, os, time
from pathlib import Path
from astra_transport import run
from matcher import score

BASE=Path.home()/'.local/share/means-of-prediction/slides'
ROOT=BASE/'astra-blind-20260910'
SCHEMA={'type':'object','properties':{k:{'type':'string'} for k in ['outcomeARegex','outcomeBRegex','limitations']},
        'required':['outcomeARegex','outcomeBRegex','limitations'],'additionalProperties':False}
PUBLIC_KEYS={'marketId','question','rules','outcomeLabels'}
hash_value=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def load(name):return json.loads((ROOT/name).read_text())
def save(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2));temporary.replace(path)

def output_from(result,directory=None):
    events=result.get('events',[])
    if not events:return None,{},'transport_failed'
    response=events[-1].get('response',{})
    if response.get('model')!='gpt-6-astra':return None,response.get('usage',{}),'model_mismatch'
    status=response.get('status','unknown')
    if status!='completed':return None,response.get('usage',{}),status
    # The Codex SSE service may omit output from the final response envelope;
    # the complete message was already delivered in output_item.done events.
    items=response.get('output') or result.get('outputItems',[])
    raw=''.join(c.get('text','') for item in items if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text')
    if not raw and directory is not None:
        path=Path(directory)/'output.txt'
        if path.exists():raw=path.read_text()
    try:return json.loads(raw),response.get('usage',{}),response.get('status','unknown')
    except ValueError:return None,response.get('usage',{}),'invalid_json'

def base_prompt():
    prompt=(BASE/'blind-regex-20260910/system-prompt.txt').read_text()
    prompt=prompt.replace('with a substantial, explicit regex (usually 200–1600 characters per pattern); length is not itself success.',
        'with an explicit regex as long as needed within the actual contract limit of 10,000 ASCII bytes per pattern. Length is not itself success. There is no 2,000-token generation cap.')
    return prompt+'\nThe intended publisher is The New York Times. Produce a candidate detector for factual reporting; explicitly disclose requirements that source text alone cannot prove. Privately check the JSON escaping, dialect and arithmetic before returning. Do not emit your reasoning trace. No tools or browsing are available.\n'

def select_panel(cases,n=12):
    groups=collections.defaultdict(list)
    for c in cases:groups[c['groupId']].append(c)
    for rows in groups.values():rows.sort(key=lambda c:hash_value(c['publicInput']))
    result=[]
    while len(result)<min(n,len(cases)):
        for group in sorted(groups):
            if groups[group] and len(result)<n:result.append(groups[group].pop(0))
    return result

def generate(case,prompt,effort,target,trial,directory,extra=None,public_context=None):
    assert set(case['publicInput'])==PUBLIC_KEYS
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    final=directory/'generation.json'
    instruction=prompt+f'\nReasoning budget guidance: use up to roughly {target:,} tokens if useful for this problem, without padding. This is guidance, not a forced length or a hard generation cap.\n'
    packet={'publicMarket':case['publicInput'],'independentTrial':trial}
    if extra:packet['blindSelfReview']=extra
    if public_context is not None:packet['publicContext']=public_context
    job={'instructions':instruction,'input':packet,'effort':effort,'schema':SCHEMA}
    if final.exists():
        cached=json.loads(final.read_text())
        if cached['requestSha256']!=hash_value(job):raise RuntimeError('Cached request differs; use a new method/attempt name')
        return cached
    if (directory/'process.json').exists() and not (directory/'transport-result.json').exists():
        process=json.loads((directory/'process.json').read_text())
        try:os.kill(process['pid'],0)
        except ProcessLookupError:raise RuntimeError('Interrupted generation has uncertain completion; retain and reconcile it before an explicit new attempt')
        else:raise RuntimeError('A generation process is still live; inspect it instead of restarting')
    save(directory/'job.json',job)
    result=json.loads((directory/'transport-result.json').read_text()) if (directory/'transport-result.json').exists() else run(job,directory)
    output,usage,status=output_from(result,directory)
    record={'marketId':case['marketId'],'groupId':case['groupId'],'split':case['split'],'trial':trial,
        'effort':effort,'requestedTokenGuidance':target,'hardOutputCap':None,'output':output,'usage':usage,
        'status':status,'seconds':result.get('seconds'),'requestSha256':hash_value(job),'instructionsSha256':hash_value(instruction),
        'directory':str(directory),'toolsExposed':0}
    if public_context is not None:record['publicContextSha256']=hash_value(public_context)
    save(final,record);return record

def pilot(workers=3):
    cases=load('train-cases.private.json');panel=select_panel(cases,8)
    panel=panel[:4] # Four event groups, identical across paired effort arms.
    prompt=base_prompt();(ROOT/'prompt-v0.txt').write_text(prompt)
    save(ROOT/'pilot-plan.json',{'createdAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'caseIds':[c['marketId'] for c in panel],'split':'train','efforts':['medium','high','xhigh','max'],
        'targets':[4000,8000,16000,32000],'trialsPerArm':2,'emailFeedbackUsed':False,'promptSha256':hash_value(prompt)})
    tasks=[]
    for effort,target in [('medium',4000),('high',8000),('xhigh',16000),('max',32000)]:
        for trial in [1,2]:
            for c in panel:tasks.append((c,prompt,effort,target,trial,ROOT/'pilot'/effort/str(c['marketId'])/str(trial)))
    corpus={e['id']:e for e in json.loads((BASE/'blind-regex-20260910/corpus.json').read_text())}
    completed=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future={pool.submit(generate,*args):args[0] for args in tasks}
        for f in concurrent.futures.as_completed(future):
            record=f.result();case=future[f];record['score']=score(record['output'],corpus[case['emailId']],case)
            completed.append(record);save(ROOT/'pilot-progress.json',completed)
            print(json.dumps({'completed':len(completed),'total':len(tasks),'effort':record['effort'],
                'status':record['score']['status'],'outputTokens':record['usage'].get('output_tokens')}),flush=True)
    summary=[]
    for effort in ['medium','high','xhigh','max']:
        rows=[r for r in completed if r['effort']==effort]
        summary.append({'effort':effort,'attempts':len(rows),'statuses':dict(collections.Counter(r['score']['status'] for r in rows)),
            'outputTokens':sum(r['usage'].get('output_tokens',0) for r in rows),
            'reasoningTokens':sum(r['usage'].get('output_tokens_details',{}).get('reasoning_tokens',0) for r in rows)})
    save(ROOT/'pilot-summary.json',summary);print(json.dumps({'pilotComplete':True,'summary':summary}),flush=True)

if __name__=='__main__':
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['pilot']);p.add_argument('--workers',type=int,default=3);a=p.parse_args()
    pilot(a.workers)
