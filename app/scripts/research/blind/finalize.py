"""Freeze and evaluate final replications; never feed test scores into generation."""
import argparse, collections, datetime, hashlib, json, os
from pathlib import Path
from experiment import BASE,ROOT,load,save,hash_value
from improve import corpus,evaluate,recover,summarize
from matcher import compile_pattern,search
from witness import witness

def verify_selection(selected):
    for name,digest in selected['promptHashes'].items():
        if hash_value((ROOT/name).read_text())!=digest:raise RuntimeError('Selected prompt changed after freeze')
    files={'split-manifest.json':'splitManifestSha256','controls.json':'controlsSha256',
           'public-contexts.json':'publicContextsSha256',
           'public-inputs.json':'originalPublicInputsSha256','test-public-inputs.json':'testPublicInputsSha256'}
    for name,key in files.items():
        if selected.get(key) and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=selected[key]:
            raise RuntimeError('Frozen input changed: '+name)

def verify_frozen_artifacts(frozen):
    # recover() reads the raw transport and, occasionally, output.txt. Seal those
    # sources as well as generation.json so scoring cannot silently change output.
    for relative,digest in {**frozen['files'],**frozen.get('artifacts',{})}.items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frozen final artifact changed: '+relative)

def freeze_selection(method,effort,target,review_chain=None):
    path=ROOT/'frozen-selection.json'
    if path.exists():raise RuntimeError('Selection already frozen; do not overwrite')
    pilot=list((ROOT/'pilot').glob('*/*/*/generation.json'))
    if len(pilot)!=32:raise RuntimeError('Complete the 32-call budget pilot first')
    for version in ['prompt-v1','prompt-v2']:
        if not (ROOT/'optimization'/version/'lineage.json').exists():raise RuntimeError('Two measured prompt revisions are required')
        if not (ROOT/'methods'/version/'train-summary.json').exists():raise RuntimeError('Training measurement missing for '+version)
    selection_split='calibration' if (ROOT/'calibration-release.json').exists() else 'validation'
    selection=load('methods/'+method+'/'+selection_split+'-summary.json')
    if selection['attempts']!=19:raise RuntimeError('Full development selection set required')
    chain=review_chain or []
    files=[ROOT/(name+'.txt') for name in chain+[method]]
    steps=[]
    for name in chain+[method]:
        examples=list((ROOT/'methods'/name/selection_split).glob('*/*/generation.json'))
        if not examples:raise RuntimeError('Validation step configuration missing for '+name)
        settings={(json.loads(p.read_text())['effort'],json.loads(p.read_text())['requestedTokenGuidance']) for p in examples}
        if len(settings)!=1:raise RuntimeError('Mixed step settings need an explicit selection configuration')
        e,t=next(iter(settings));config=load('methods/'+name+'/method.json')
        steps.append({'method':name,'effort':e,'tokenGuidance':t,'publicContext':config.get('publicContext',False)})
    if (steps[-1]['effort'],steps[-1]['tokenGuidance'])!=(effort,target):raise RuntimeError('Requested selection settings differ from measured validation settings')
    save(path,{'frozenAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':method,'effort':effort,
               'tokenGuidance':target,'hardOutputCap':None,'reviewChain':chain,'steps':steps,'selectionSummary':selection,
               'selectionSplit':selection_split,'selectionDataAreTraining':selection_split=='calibration',
               'promptHashes':{p.name:hash_value(p.read_text()) for p in files},
               'splitManifestSha256':hashlib.sha256((ROOT/'split-manifest.json').read_bytes()).hexdigest(),
               'controlsSha256':hashlib.sha256((ROOT/'controls.json').read_bytes()).hexdigest(),
               'originalPublicInputsSha256':hashlib.sha256((ROOT/'public-inputs.json').read_bytes()).hexdigest(),
               'testPublicInputsSha256':hashlib.sha256((ROOT/'test-public-inputs.json').read_bytes()).hexdigest(),
               'publicContextsSha256':hashlib.sha256((ROOT/'public-contexts.json').read_bytes()).hexdigest() if any(s['publicContext'] for s in steps) else None,
               'finalPlan':{'originalMarkets':10,'originalTrials':10,'testMarkets':26,'testTrials':3}})

def freeze_generations():
    selected=load('frozen-selection.json');method=selected['method']
    if (ROOT/'frozen-final-generations.json').exists():raise RuntimeError('Final generations already frozen')
    verify_selection(selected)
    files=[];artifacts={}
    for split,trials,public_file in [('original',10,'public-inputs.json'),('test',3,'test-public-inputs.json')]:
        public={p['marketId']:p for p in load(public_file)}
        expected={(id,i) for id in public for i in range(1,trials+1)}
        paths=list((ROOT/'methods'/method/split).glob('*/*/generation.json'))
        got={(p.parent.parent.name,int(p.parent.name)) for p in paths}
        if expected!=got:raise RuntimeError('Incomplete or extra final attempts in '+split)
        files+=paths
        for step in selected['steps']:
            step_root=ROOT/'methods'/step['method']
            step_paths=list((step_root/split).glob('*/*/generation.json'))
            if {(p.parent.parent.name,int(p.parent.name)) for p in step_paths}!=expected:
                raise RuntimeError('Incomplete final review lineage: '+step['method'])
            for p in step_paths:
                r=json.loads(p.read_text())
                if (r['effort'],r['requestedTokenGuidance'])!=(step['effort'],step['tokenGuidance']):
                    raise RuntimeError('Final generation settings differ from selection')
                job=json.loads((p.parent/'job.json').read_text())
                if hash_value(job)!=r['requestSha256']:raise RuntimeError('Final request changed')
                instructions=(ROOT/(step['method']+'.txt')).read_text()+f'\nReasoning budget guidance: use up to roughly {step["tokenGuidance"]:,} tokens if useful for this problem, without padding. This is guidance, not a forced length or a hard generation cap.\n'
                if job['instructions']!=instructions:raise RuntimeError('Final generation used a different prompt')
                packet=job['input']
                if packet['publicMarket']!=public[r['marketId']] or packet['independentTrial']!=r['trial']:
                    raise RuntimeError('Final public input mismatch')
                if set(packet)-{'publicMarket','independentTrial','blindSelfReview','publicContext'}:
                    raise RuntimeError('Unexpected final generator input')
                expected_context=load('public-contexts.json').get(r['marketId']) if step.get('publicContext') else None
                if packet.get('publicContext')!=expected_context:raise RuntimeError('Final public context mismatch')
                for filename in ['generation.json','job.json','model-request.json','transport-result.json','output.txt']:
                    source=p.parent/filename
                    if filename in ['generation.json','job.json','transport-result.json'] and not source.exists():
                        raise RuntimeError('Final source missing: '+str(source))
                    if source.exists():artifacts[str(source.relative_to(ROOT))]=hashlib.sha256(source.read_bytes()).hexdigest()
            config=step_root/'method.json'
            artifacts[str(config.relative_to(ROOT))]=hashlib.sha256(config.read_bytes()).hexdigest()
    save(ROOT/'frozen-final-generations.json',{'frozenAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'count':len(files),'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
        'artifacts':artifacts,
        'testEmailScoringHasNotStarted':True})

def final_scores():
    frozen=load('frozen-final-generations.json');selected=load('frozen-selection.json')
    if frozen['count']!=178:raise RuntimeError('Expected all 178 final attempts')
    verify_selection(selected);verify_frozen_artifacts(frozen)
    if hashlib.sha256((BASE/'blind-regex-20260910/corpus.json').read_bytes()).hexdigest()!=load('split-manifest.json')['corpusSha256']:raise RuntimeError('Corpus changed')
    cases=[]
    for split in ['train','validation','test']:cases+=load(split+'-cases.private.json')
    emails=corpus();controls=load('controls.json');reports={};patterns=set();windows={}
    for split in ['original','test']:
        records=[recover(ROOT/p) for p in frozen['files'] if '/'+split+'/' in p]
        rows=evaluate(records,cases,controls)
        for row in rows:
            c=next(c for c in cases if c['marketId']==row['marketId']);e=emails[c['emailId']]
            row['question']=c['publicInput']['question'];row['rules']=c['publicInput']['rules'];row['knownEmailId']=e['id']
            row['evaluationGroupId']=c['groupId'];row['factKey']=c['factKey']
            row['emailReceivedAt']=e['receivedAt'];row['emailSignedDate']=e.get('signedDate');row['marketClosedAt']=c['closedAt']
            row['expectedOutcome']=c['expectedOutcome'];row['initialDataSplit']=c['split']
            row['dataSplit']='calibration' if c['split']=='validation' and (ROOT/'calibration-release.json').exists() else c['split']
            row['archiveCandidates']=[];row['archiveTimeouts']=0
            compiled=[]
            for key in ['outcomeARegex','outcomeBRegex']:
                pattern=row['output'].get(key) if isinstance(row['output'],dict) else None
                if pattern:patterns.add(pattern)
                compiled.append(compile_pattern(pattern)[0])
            actual=row['score']['actualIndex']
            row['knownWitness']=witness(e,row['score']['matches'][actual],compiled[actual])
            if row['score']['status']=='hit' and row['knownWitness']['compatible']:
                p=row['output'][['outcomeARegex','outcomeBRegex'][actual]];text=row['knownWitness']['decodedSource']
                windows[(p,text)]={'pattern':p,'decodedSource':text}
            if row['score']['validPair']:
                for mail in emails.values():
                    matches=[search(p,mail['html']) for p in compiled]
                    row['archiveTimeouts']+=sum(t for m,t in matches)
                    if any(m for m,t in matches):row['archiveCandidates'].append({'emailId':mail['id'],
                        'outcomes':[i for i,(m,t) in enumerate(matches) if m],'matches':[m for m,t in matches]})
        summary=summarize(rows)
        summary.update(timelyHits=sum(r['score']['status']=='hit' and r['availableByClosure'] for r in rows),
            windowCompatibleHits=sum(r['score']['status']=='hit' and r['knownWitness']['compatible'] for r in rows),
            distinctMarkets=len({r['marketId'] for r in rows}),
            marketsWithHit=len({r['marketId'] for r in rows if r['score']['status']=='hit'}),
            archiveCandidatePairs=sum(len(r['archiveCandidates']) for r in rows),
            note='Known factual-match cases selected retrospectively. Archive candidates are unreviewed. This is not a market settlement rate.')
        reports[split]={'summary':summary,
            'byGroup':{id:summarize([r for r in rows if r['evaluationGroupId']==id]) for id in sorted({r['evaluationGroupId'] for r in rows})},
            'byMarket':{id:summarize([r for r in rows if r['marketId']==id]) for id in sorted({r['marketId'] for r in rows})},'rows':rows}
        print(json.dumps({'finalSplit':split,'summary':summary}),flush=True)
    save(ROOT/'final-scores.private.json',reports)
    save(ROOT/'native-input.private.json',{'patterns':sorted(patterns),'witnesses':list(windows.values())})

if __name__=='__main__':
    os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('mode',choices=['selection','freeze','score']);p.add_argument('--method');p.add_argument('--effort',default='high');p.add_argument('--target',type=int,default=8000);p.add_argument('--review-chain',nargs='*');a=p.parse_args()
    if a.mode=='selection':freeze_selection(a.method,a.effort,a.target,a.review_chain)
    elif a.mode=='freeze':freeze_generations()
    else:final_scores()
