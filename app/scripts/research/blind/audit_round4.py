"""Audit complete round-four data coverage and actual model inputs, without labels.

The independent fixture directory is deliberately never opened here.
"""
import collections, json
from pathlib import Path
import round4 as r


def verify_generation(directory, public, prompt, context=None, method='baseline'):
    directory=Path(directory); raw=r.read(directory/'generation.json')
    job=r.job_for(public,prompt,context,raw['trial'])
    if raw['requestSha256']!=r.hash_value(job):raise RuntimeError('Generation job hash differs')
    r.verify_model_artifact(directory,job,raw)
    errors=[r.compile_pattern(raw['output'].get(k))[1] for k in r.FIELDS] if isinstance(raw['output'],dict) else []
    required=method!='baseline' and raw['status']=='completed' and any(errors)
    fixdir=directory/'syntax-repair'
    if required!=fixdir.exists():raise RuntimeError('Unexpected or missing syntax repair')
    effective=raw
    if required:
        fixjob={'instructions':r.SYNTAX_REPAIR_INSTRUCTIONS,'input':{'publicMarket':public,'candidate':raw['output'],'syntaxErrors':errors},'effort':'medium','schema':r.SCHEMA}
        parsed=r.read(fixdir/'parsed.json');effective=r.read(fixdir/'effective-record.json')
        r.verify_model_artifact(fixdir,fixjob,parsed)
        if effective['output']!=parsed['output'] or effective['status']!=parsed['status'] or effective['rawOutput']!=raw['output']:
            raise RuntimeError('Effective record differs from original/repair')
        if effective['pipelineUsage']!=[raw['usage'],parsed['usage']]:raise RuntimeError('Repair accounting differs')
    return raw,effective

def audit_gap_controls():
    if not (r.ROOT/'gap-control-seal.json').exists():return None
    import gap_controls as g
    public=r.load('gap-controls-public.json');expected={};seen=[]
    for i in range((len(public)+1)//2):
        chunk=public[2*i:2*i+2];d=r.ROOT/'gap-control-author'/str(i)
        job={'instructions':g.INSTRUCTION,'input':{'publicMarkets':chunk},'effort':'medium','schema':g.CONTROL_SCHEMA}
        parsed=r.read(d/'parsed.json');r.verify_model_artifact(d,job,parsed)
        output=parsed.get('output');rows=output.get('markets',[]) if isinstance(output,dict) else []
        ids=[x['marketId'] for x in rows]
        if len(ids)!=len(set(ids)) or set(ids)-{p['marketId'] for p in chunk}:raise RuntimeError('Duplicate/unrequested control output')
        found={x['marketId']:x['controls'] for x in rows}
        for p in chunk:
            cs=found.get(p['marketId'],[])
            balanced=parsed['status']=='completed' and len(cs)==10 and collections.Counter(c['expected'] for c in cs)=={'A':2,'B':2,'neither':6}
            expected[p['marketId']]=cs if balanced else [];seen.append(p['marketId'])
    if expected!=r.load('gap-controls.private.json'):raise RuntimeError('Gap fixtures differ from author output')
    r.all_development_controls()
    return {'publicOnlyRequests':(len(public)+1)//2,'requestedMarkets':len(seen),'availableMarkets':sum(bool(v) for v in expected.values()),'fixtures':sum(map(len,expected.values()))}

def audit_complete_feedback():
    public={p['marketId']:p for name in ['development-public.json','expansion-public.json','followup-public.json'] for p in r.load(name)}
    controls=r.all_development_controls();coverage={}
    for method_dir in sorted((r.ROOT/'feedback-learning-complete').glob('*')):
        primary={x['marketId']:x for x in r.load('methods/'+method_dir.name+'/development-scores.private.json')}
        gap={x['marketId']:x['controls'] for x in r.load('methods/'+method_dir.name+'/gap-control-scores.private.json')}
        additional={x['marketId']:x for cohort in ['expansion','followup'] for x in r.load('methods/'+method_dir.name+'/'+cohort+'-generations.json')}
        seen=[];fixture_count=0
        for d in sorted(method_dir.iterdir()):
            job=r.read(d/'job.json');parsed,selected_dir=r.selected_teacher_record(d);packet=job['input'];r.verify_model_artifact(selected_dir,job,parsed)
            for attempt_dir in [d]+sorted(d.glob('transport-recovery-*')):
                r.verify_model_artifact(attempt_dir,job,r.read(attempt_dir/'parsed.json'))
            if parsed['status']!='completed':raise RuntimeError('Unfinished complete feedback')
            mids={x['marketId'] for x in packet['rows']};seen += [x['marketId'] for x in packet['rows']]
            if packet['publicMarkets']!=[public[mid] for mid in sorted(mids)]:raise RuntimeError('Complete feedback public input differs')
            if packet['controls']!={mid:controls.get(mid,[]) for mid in sorted(mids)}:raise RuntimeError('Complete feedback controls differ')
            fixture_count+=sum(map(len,packet['controls'].values()))
            for row in packet['rows']:
                original=(primary if row['cohort']=='development' else additional)[row['marketId']]
                for key in ['output','syntaxRepair']:
                    if row[key]!=original.get(key):raise RuntimeError('Complete feedback candidate changed')
                if row['cohort']=='development':
                    if row['factualScore']!=original.get('factualScore') or row['controls']!=original['controls']+gap.get(row['marketId'],[]):raise RuntimeError('Complete feedback scores differ')
        if len(seen)!=len(public) or set(seen)!=set(public) or fixture_count!=sum(map(len,controls.values())):raise RuntimeError('Complete feedback omitted/duplicated data')
        coverage[method_dir.name]={'candidates':len(seen),'fixtures':fixture_count,'batches':len(list(method_dir.iterdir()))}
    return coverage


def audit():
    protocol=r.load('protocol.json'); snapshots={**protocol['inputSnapshots'],**protocol['preservedSnapshots']}
    for path,sha in snapshots.items():
        if r.digest(path)!=sha:raise RuntimeError('Prior snapshot changed: '+path)
    shards=[r.load('lesson-shards/'+str(i)+'.private.json') for i in range(8)]
    coverage={}
    for name,key,expected in [('emails','id',protocol['emails']),('facts','factKey',protocol['factFamilies']),('publicMarkets','marketId',protocol['publicMarkets']),('historicalFeedback','source',protocol['historicalCandidates'])]:
        ids=[item[key] for shard in shards for item in shard[name]]
        if len(ids)!=expected or len(set(ids))!=expected:raise RuntimeError('Incomplete/duplicate lesson coverage: '+name)
        coverage[name]=len(ids)
    controls={mid:cs for s in shards for mid,cs in s['syntheticControls'].items()}
    if controls!={p['marketId']:r.load('controls.json').get(p['marketId'],[]) for p in r.load('development-public.json')}:raise RuntimeError('Lesson controls differ')
    coverage['controlFixtures']=sum(map(len,controls.values()))
    for i,shard in enumerate(shards):
        d=r.ROOT/'learning'/str(i); job=r.read(d/'job.json')
        if job['input']!=shard:raise RuntimeError('Teacher did not receive full shard')
        r.verify_model_artifact(d,job,r.read(d/'parsed.json'))
    feedback_coverage={};public={p['marketId']:p for p in r.load('development-public.json')}
    for method_dir in sorted((r.ROOT/'feedback-learning').glob('*')):
        originals={x['marketId']:x for x in r.load('methods/'+method_dir.name+'/development-scores.private.json')};seen=[]
        for d in sorted(method_dir.iterdir()):
            job=r.read(d/'job.json');parsed=r.read(d/'parsed.json');packet=job['input']
            r.verify_model_artifact(d,job,parsed)
            if parsed['status']!='completed':raise RuntimeError('Unfinished feedback learning')
            mids={x['marketId'] for x in packet['rows']};seen += list(mids)
            if packet['publicMarkets']!=[public[mid] for mid in sorted(mids)]:raise RuntimeError('Feedback public input differs')
            if packet['controls']!={mid:r.load('controls.json').get(mid,[]) for mid in sorted(mids)}:raise RuntimeError('Feedback controls differ')
            for row in packet['rows']:
                for key in ['output','factualScore','controls','syntaxRepair']:
                    if row[key]!=originals[row['marketId']].get(key):raise RuntimeError('Feedback row changed')
        if len(seen)!=189 or set(seen)!=set(public):raise RuntimeError('Feedback coverage incomplete or duplicate')
        feedback_coverage[method_dir.name]={'candidates':len(seen),'batches':len(list(method_dir.iterdir()))}
    gap_audit=audit_gap_controls();complete_coverage=audit_complete_feedback()
    body_supplement=None
    if (r.ROOT/'complete-body-supplement-manifest.json').exists():
        import complete_body_feedback as body
        body_supplement=body.lessons()
    optimizer_counts={}
    for d in sorted((r.ROOT/'optimization').iterdir()):
        if not (d/'parsed.json').exists():raise RuntimeError('Unfinished optimizer')
        job=r.read(d/'job.json');r.verify_model_artifact(d,job,r.read(d/'parsed.json'))
        packet=job['input']
        if 'completeBodySupplement' in packet and packet['completeBodySupplement']!=body_supplement:
            raise RuntimeError('Complete-body supplement omitted or changed')
        if 'additionalSemanticReview' in packet and packet['additionalSemanticReview']!=r.load('semantic-review-followup.private.json'):
            raise RuntimeError('Additional semantic review changed')
        if 'contextExtensionDiagnostic' in packet and packet['contextExtensionDiagnostic']!=r.load('context-extension-diagnostic.private.json'):
            raise RuntimeError('Context diagnostic changed')
        lineage=d/'lineage.json'
        if lineage.exists() and r.read(lineage).get('completeFullBodySupplementUsed')!=('completeBodySupplement' in packet) and 'completeFullBodySupplementUsed' in r.read(lineage):
            raise RuntimeError('Complete-body lineage differs')
        for key,file in [('allLabeledFactsAndMarkets','all-factual-evidence.private.json'),('allDevelopmentPublicMarkets','development-public.json'),('allSyntheticControls','controls.json')]:
            expected=r.compact_facts() if key=='allLabeledFactsAndMarkets' and packet.get('packetVersion')==2 else r.load(file)
            if packet[key]!=expected:raise RuntimeError('Optimizer data omitted: '+key)
        if packet['lessonsFromEveryDataShard']!=[r.read(r.ROOT/'learning'/str(i)/'parsed.json')['output'] for i in range(8)]:raise RuntimeError('Optimizer lesson omitted')
        extra=packet.get('additionalNaturalDevelopmentCautions',[])
        if extra:
            expected=[{k:c[k] for k in ['caseId','publicInput','evidence','classification','assessment','timing','eventFamilyId','humanReviewStatus']} for c in r.load('expansion-cases.private.json')]
            if extra!=expected:raise RuntimeError('Extra data projection differs')
        parsed=r.read(d/'parsed.json')
        followup=packet.get('followupNaturalDevelopmentCautions',[])
        if followup:
            original={c['caseId']:c for c in r.load('followup-cases.private.json')}
            if len(followup)!=len(original) or any(c!={k:original[c['caseId']][k] for k in c} for c in followup):raise RuntimeError('Follow-up projection differs')
        optimizer_counts[d.name]={'naturalCautions':len(extra),'followupNaturalCautions':len(followup),
            'completeBodySupplementUsed':'completeBodySupplement' in packet,
            'containsCachedMarketPayouts':False,'status':parsed['status']}
        for method in set(feedback_coverage)|set(complete_coverage):
            feedback=packet.get(method+'Feedback',{})
            if 'lessonsFromEveryCandidate' in feedback:
                namespace=feedback.get('feedbackNamespace','feedback-learning')
                if namespace not in ['feedback-learning','feedback-learning-complete']:raise RuntimeError('Unknown feedback namespace')
                expected=[(r.selected_teacher_record(p)[0] if namespace=='feedback-learning-complete' else r.read(p/'parsed.json'))['output'] for p in sorted((r.ROOT/namespace/method).iterdir(),key=lambda p:int(p.name))]
                if feedback['lessonsFromEveryCandidate']!=expected:raise RuntimeError('Feedback lesson omitted or changed')
    methods={};contexts=r.load('public-contexts.json');reuse=r.load('baseline-reuse.json')['records']
    for p in sorted((r.ROOT/'methods').glob('*/summary.json')):
        method=p.parent.name;prompt=(r.ROOT/(method+'.txt')).read_text();counts=collections.Counter()
        cohorts=[('development','development-public.json','development-generations.json'),('expansion','expansion-public.json','expansion-generations.json')]
        if (r.ROOT/'followup-import.json').exists():cohorts.append(('followup','followup-public.json','followup-generations.json'))
        for split,pubfile,recordfile in cohorts:
            publics={x['marketId']:x for x in r.load(pubfile)};records=r.read(p.parent/recordfile)
            if len(records)!=len(publics) or {x['marketId'] for x in records}!=set(publics):raise RuntimeError('Incomplete method cohort')
            for record in records:
                mid=record['marketId'];ref=reuse.get(mid) if method=='baseline' and split=='development' else None
                d=Path(ref['path']).parent if ref else p.parent/split/mid/'1'
                raw,effective=verify_generation(d,publics[mid],prompt,contexts.get(mid) if split=='development' else None,method)
                for key in ['output','usage','status','requestSha256']:
                    if record[key]!=effective[key]:raise RuntimeError('Aggregate candidate differs: '+method+'/'+mid+'/'+key)
                counts['reused' if ref else 'newRawGenerations']+=1
                counts['rawStatus:'+raw['status']]+=1;counts['effectiveStatus:'+effective['status']]+=1
                counts['syntaxRepairs']+=raw is not effective
        methods[method]=dict(counts)
    return {'auditedAt':r.now(),'priorSnapshotsVerified':len(snapshots),'coverage':coverage,
        'originalTeacherRepresentation':'All143 email IDs;142 URL/footer-cleaned texts and one complete stored text. Complete HTML was used for scoring.',
        'completeBodySupplement':body_supplement['audit'] if body_supplement else None,
        'feedbackLearningCoverage':feedback_coverage,'completeFeedbackCoverage':complete_coverage,'gapControls':gap_audit,'optimizers':optimizer_counts,'methods':methods,'freshFixtureContentsRead':False,'scope':'Data coverage and public-only per-market generation; optimizers intentionally see private development evidence. This audit never opens sealed evaluation labels.'}


if __name__=='__main__':
    sealed=(r.ROOT/'selection.json').exists()
    if sealed:r.verify_selection()
    result=audit();r.save(r.ROOT/('final-training-audit.json' if sealed else 'training-audit.json'),result)
    print(json.dumps(result,indent=2))
