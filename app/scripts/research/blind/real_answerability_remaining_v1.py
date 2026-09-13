"""Separate 101-pair extension of the frozen real-answerability protocol.

No old globals or artifacts are mutated. Preparation and auditing are read-only
with respect to prior studies. Launch requires a separately reviewed exact plan.
"""
import argparse
import collections
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys

import real_answerability_v1 as original
import real_answerability_audit_v1 as prior_audit
import real_answerability_score_v1 as prior_scoring
from astra_transport import build_request

q, h = original.q, original.h
HERE = Path(__file__).resolve().parent
ROOT = q.r.BASE/'real-answerability-remaining-v1-20260913'
PRIOR = original.ROOT
PRIOR_PINS = {
    PRIOR/'plan.private.json':'bf5ae169adbae28b430c516c85b368041e0eb47d70adb7969a7a6df73dd53474',
    PRIOR/'adjudicated-labels.private.json':'f5a89076ae95dc93c0adbac4e7b3725dd525abb8db38d4c8da87811c34c446fa',
    PRIOR/'adjudicated-labels-seal.json':'3fdbfd9c9756ff21bba09c58c16b4258d9a7be86beb98f342e09fc7bcba6686f',
    PRIOR/'raw-audit.private.json':'749f13b5b35f32a7f66969b66fe89bf9017914025469b7587fcf783bea79d498',
}


def once(path, value):
    original.write_once(path,value)
    Path(path).chmod(0o600)


def check_hashes(pins):
    for path, sha in pins.items():
        if q.r.digest(path) != sha:
            raise RuntimeError('Pinned source/artifact changed: '+str(path))


def select_remaining(items, prior_selected):
    factual = [x for x in items if x['kind']=='factual']
    ids = {x['caseId'] for x in factual}
    used = {x['caseId'] for x in prior_selected}
    if len(factual)!=161 or len(ids)!=161 or len(prior_selected)!=60 or len(used)!=60 or not used <= ids:
        raise ValueError('Expected exactly161 natural pairs and60 unique prior members')
    index = {x['caseId']:x for x in factual}
    for old in prior_selected:
        item = index[old['caseId']]
        if any(old[k]!=v for k,v in {'marketId':item['marketId'],'emailId':item['metadata']['emailId'],
              'family':item['metadata']['factKey'],'legacyTimingStratum':item['metadata']['availableByClosure']}.items()):
            raise ValueError('Prior panel member identity differs')
    remaining = sorted((x for x in factual if x['caseId'] not in used),key=lambda x:x['caseId'])
    if len(remaining)!=101 or {x['caseId'] for x in remaining} & used or {x['caseId'] for x in remaining} | used != ids:
        raise ValueError('Extension must be the exact disjoint complement')
    return remaining


def job_for(item, public, which):
    if which not in original.PASSES:
        raise ValueError('Unknown review pass')
    job = original.make_job(item,public,which)
    if set(job)!= {'instructions','input','effort','schema'} or set(job['input'])!={'publicMarket','completeEmail'}:
        raise ValueError('Unexpected model-job fields')
    if set(job['input']['publicMarket'])!=q.r.PUBLIC_KEYS or job['schema']!=original.SCHEMA or job['instructions']!=original.PASSES[which] or job['effort']!='high':
        raise ValueError('Original blind procedure differs')
    request = build_request(job)
    if request['tools']!=[] or request['tool_choice']!='none' or request['store'] is not False or request['model']!='gpt-6-astra' or 'max_output_tokens' in request:
        raise ValueError('Transport tools/model/cap differ')
    return job


def local_sources():
    paths = {Path(__file__).resolve(), HERE/'test_real_answerability_remaining_v1.py',
             HERE/'real_answerability_remaining_audit_v1.py'}
    for module in list(sys.modules.values()):
        value = getattr(module,'__file__',None)
        if value:
            path = Path(value).resolve()
            if path.parent==HERE and path.suffix=='.py':
                paths.add(path)
    return paths


def identity(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':q.r.digest(path)}


def prior_inventory():
    return {str(p):q.r.digest(p) for p in sorted(PRIOR.rglob('*')) if p.is_file()}


def prepare():
    import tiktoken
    if ROOT.exists():
        raise RuntimeError('Extension already prepared; never overwrite')
    check_hashes(PRIOR_PINS)
    prior=original.verify_plan()
    selected=select_remaining(q.load(q.ITEMS),prior['selected'])
    public={x['marketId']:x for x in q.load('public-inputs.json')}
    enc=tiktoken.get_encoding('o200k_base');entries=[]
    for item in selected:
        for which in original.PASSES:
            name=which+'/'+item['caseId'];job=job_for(item,public[item['marketId']],which)
            count=h.known_tokens(job,enc)
            if count>120000 or count+20000>258400:
                raise RuntimeError('Full request exceeds original token budget; no truncation')
            path=ROOT/'jobs'/(name+'.json');once(path,job)
            entries.append({'name':name,'caseId':item['caseId'],'pass':which,'jobSha256':q.r.digest(path),'knownInputTokens':count})
    pins={str(p):sha for p,sha in PRIOR_PINS.items()}
    pins.update({str(p):q.r.digest(p) for p in local_sources() | {q.ROOT/q.ITEMS,q.ROOT/'public-inputs.json'}})
    for path,sha in pins.items():
        source=Path(path)
        if source.parent==HERE:
            dest=ROOT/'source'/source.name;dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('xb') as stream:stream.write(source.read_bytes())
            if q.r.digest(dest)!=sha:raise RuntimeError('Source snapshot differs')
    plan={'at':q.r.now(),'version':'real-answerability-remaining-v1','pins':pins,'priorInventory':prior_inventory(),
        'priorPlanSha256':q.r.digest(PRIOR/'plan.private.json'),
        'selected':[{'caseId':i['caseId'],'marketId':i['marketId'],'emailId':i['metadata']['emailId'],
            'family':i['metadata']['factKey'],'legacyTimingStratum':i['metadata']['availableByClosure']} for i in selected],
        'entries':entries,'workers':4,'model':'gpt-6-astra','oneAttemptPerJob':True,
        'executables':{'python':identity(sys.executable),'codex':identity(shutil.which('codex'))},
        'pythonVersion':sys.version,'tokenizer':{'version':tiktoken.__version__,'encoding':'o200k_base'},
        'knownInputTokens':sum(x['knownInputTokens'] for x in entries),'maxKnownInputTokens':max(x['knownInputTokens'] for x in entries),
        'scope':'Exact remaining101 of161 old natural pairs. Same public-only market fields and complete email. No original labels, generated rules, prior reviews, model outputs, payouts or reserved material in requests.',
        'originalProcedureSha256':q.r.hash_value({'passes':original.PASSES,'schema':original.SCHEMA}),
        'adjudication':'Two same-model passes are correlated model annotations. Complete raw audit and explicit root adjudication/label seal are required before any model comparison. Failed, unknown or unattempted passes cannot justify an adjudicated answerable label.',
        'usageSnapshot':{'observedAt':'2026-09-13T22:57:59+00:00','weeklyUsedPercent':62,'reachedFlag':False,'persistentStopObserved':h.stopped(),
            'qualification':'Read-only account snapshot from preparation turn; not a promised budget. No capacity probe or reset. Shared persistent usage stop remains authoritative.'},
        'limitations':['Exposed correlated development set; not population coverage or independent human gold.',
            'All19 legacy timing-screen pairs were in prior60; remaining101 contain none. This is exhaustive completion, not a second representative sample.',
            'Metadata omissions and same annotation prompt ambiguities are preserved, including the need to review sufficient ordinary versus triggered fallback branches.',
            'Known token count excludes server framing; same120k budget and20k output reserve, no hard output cap.',
            'No local inference or hosted rule generation; no mutation of prior60 artifacts, labels or source files.']}
    once(ROOT/'plan.private.json',plan)
    print(json.dumps({'root':str(ROOT),'planSha256':q.r.digest(ROOT/'plan.private.json'),'pairs':len(selected),'calls':len(entries),'knownInputTokens':plan['knownInputTokens'],'maxKnownInputTokens':plan['maxKnownInputTokens']},indent=2))


def verify_plan():
    plan=q.r.read(ROOT/'plan.private.json');check_hashes(plan['pins'])
    if prior_inventory()!=plan['priorInventory']:
        raise RuntimeError('Original60 study changed or gained files')
    if not {str(p) for p in local_sources()} <= set(plan['pins']):
        raise RuntimeError('Imported local dependency lacks a pin')
    for path,sha in plan['pins'].items():
        if Path(path).parent==HERE and q.r.digest(ROOT/'source'/Path(path).name)!=sha:
            raise RuntimeError('Captured source differs')
    if identity(sys.executable)!=plan['executables']['python'] or identity(shutil.which('codex'))!=plan['executables']['codex']:
        raise RuntimeError('Use pinned Python/Codex executables')
    if plan['workers']!=4 or plan['model']!='gpt-6-astra' or not plan['oneAttemptPerJob']:
        raise RuntimeError('Dispatch procedure differs')
    prior=q.r.read(PRIOR/'plan.private.json')
    selected=select_remaining(q.load(q.ITEMS),prior['selected'])
    expected_selected=[{'caseId':i['caseId'],'marketId':i['marketId'],'emailId':i['metadata']['emailId'],
        'family':i['metadata']['factKey'],'legacyTimingStratum':i['metadata']['availableByClosure']} for i in selected]
    if plan['selected']!=expected_selected or plan['originalProcedureSha256']!=q.r.hash_value({'passes':original.PASSES,'schema':original.SCHEMA}):
        raise RuntimeError('Complement or annotation procedure differs')
    public={x['marketId']:x for x in q.load('public-inputs.json')}
    expected=[(i,w) for i in selected for w in original.PASSES]
    if len(plan['entries'])!=202 or len({x['name'] for x in plan['entries']})!=202:
        raise RuntimeError('Exact202 unique entries required')
    counts=[e['knownInputTokens'] for e in plan['entries']]
    if any(type(n) is not int or n<=0 or n>120000 or n+20000>258400 for n in counts) or sum(counts)!=plan['knownInputTokens'] or max(counts)!=plan['maxKnownInputTokens']:
        raise RuntimeError('Recorded complete-input budget differs')
    for e,(item,which) in zip(plan['entries'],expected):
        if (e['name'],e['caseId'],e['pass'])!=(which+'/'+item['caseId'],item['caseId'],which):
            raise RuntimeError('Entry identity/order changed')
        path=ROOT/'jobs'/(e['name']+'.json')
        if q.r.digest(path)!=e['jobSha256'] or q.r.read(path)!=job_for(item,public[item['marketId']],which):
            raise RuntimeError('Blind request changed')
    actual={str(p.relative_to(ROOT/'jobs')) for p in (ROOT/'jobs').rglob('*.json')}
    if actual!={e['name']+'.json' for e in plan['entries']}:
        raise RuntimeError('Extra or missing job')
    return plan


def review_one(e):
    if h.stopped():raise RuntimeError('Shared hosted usage stop active before attempt')
    directory=ROOT/'responses'/e['name']
    if directory.exists():raise RuntimeError('Existing attempt; never reuse uncertain or completed work')
    once(directory/'attempt-started.json',{'at':q.r.now(),'pid':os.getpid(),'jobSha256':e['jobSha256']})
    job=q.r.read(ROOT/'jobs'/(e['name']+'.json'))
    try:
        effective=h.single_attempt(job,directory)
        output=effective.get('output');errors=original.validate_output(output,job)
        record={'name':e['name'],'caseId':e['caseId'],'pass':e['pass'],'status':'invalid_annotation' if errors else 'completed','output':output,'validationErrors':errors}
    except Exception as exc:
        record={'name':e['name'],'caseId':e['caseId'],'pass':e['pass'],'status':'failed','error':str(exc)}
    once(directory/'review.private.json',record)
    return record


def feed(entries,workers,worker=review_one,stopped=h.stopped,progress=None):
    todo=iter(entries);records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pending={}
        def submit():
            if stopped():return
            e=next(todo,None)
            if e is not None:pending[pool.submit(worker,e)]=e
        for _ in range(workers):submit()
        while pending:
            done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                e=pending.pop(future)
                try:record=future.result()
                except Exception as exc:record={**{k:e[k] for k in ['name','caseId','pass']},'status':'not_started_or_uncertain','error':str(exc)}
                records.append(record)
                if progress:progress(records)
                submit()
    return records


def run():
    plan=verify_plan();review=q.r.read(ROOT/'launch-review.json')
    if review.get('approved') is not True or review.get('planSha256')!=q.r.digest(ROOT/'plan.private.json') or review.get('noCompetingHostedOwner') is not True:
        raise RuntimeError('Exact launch/source/hosted-ownership review required')
    with (q.ROOT/'hosted-answerability-owner.lock').open('a') as shared, (ROOT/'runner.lock').open('a') as lock:
        fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (ROOT/'responses').exists() or (ROOT/'run-started.json').exists():
            raise RuntimeError('Prior attempt set exists; explicit reconciliation required')
        if h.stopped():raise RuntimeError('Shared hosted usage stop active')
        once(ROOT/'run-started.json',{'at':q.r.now(),'pid':os.getpid(),'planSha256':q.r.digest(ROOT/'plan.private.json')})
        def progress(rows):
            value={'at':q.r.now(),'finalized':len(rows),'planned':202,'statuses':dict(collections.Counter(r['status'] for r in rows))}
            q.r.save(ROOT/'progress.json',value);print(json.dumps(value),flush=True)
        rows=feed(plan['entries'],4,progress=progress)
        once(ROOT/'run-finished.json',{'at':q.r.now(),'records':rows,'usageStopped':h.stopped(),'qualification':'Unattempted entries are not fabricated response records. Audit all202 planned dispositions separately.'})


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','verify','run'])
    args=parser.parse_args();{'prepare':prepare,'verify':verify_plan,'run':run}[args.command]()
