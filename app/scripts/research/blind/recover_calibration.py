"""Explicit new attempts after the service's previous quota failures; keep originals."""
import concurrent.futures,copy,json,os
from pathlib import Path
from experiment import ROOT,SCHEMA,load,save,hash_value
from improve import invoke,corpus,score_controls
from matcher import score

def recover_calibration():
    cases={c['marketId']:c for c in load('calibration-cases.private.json')};emails=corpus();controls=load('controls.json')
    old_jobs=[]
    for p in (ROOT/'teacher').glob('*/0/job.json'):
        id=p.parent.parent.name
        if id not in cases:continue
        status=json.loads((p.parent/'parsed.json').read_text())['status']
        if status!='completed':old_jobs.append((id,json.loads(p.read_text())))
    def one(id,original):
        case=cases[id];attempts=[];prior=None
        for revision in range(3):
            job=copy.deepcopy(original);job['effort']='medium'
            job['input']['trainingDiagnostics']=[
                'NYT factual headlines use third-person PRESENT tense: defeats, beats, wins, clinches, captures, secures. These may report completed results; do not require past tense in every branch.',
                'NYT often inserts a title, possessive description or appositive between the result verb and the named loser. Preserve who defeated whom while accommodating that grammar and inline tags.',
                'Distinguish a forecast that a nomination may happen from a definitive future general-election matchup after the preceding text reports completed nominations. Such a matchup can supply inferential evidence of qualification when public contender/party context supports it; state any remaining identity or event assumptions, never claim an unqualified settlement proof.',
                'Use the supplied source as a training example, not an excuse to memorize one score or choose only the known outcome. Both patterns must generalize from public rules.']
            if prior:job['input']['repairFeedback']=prior
            directory=ROOT/'calibration-recovery-20260912'/id/str(revision)
            try:p=invoke(job,directory)
            except RuntimeError:
                if not (directory/'parsed.json').exists():raise
                p=json.loads((directory/'parsed.json').read_text())
                if p['status']=='completed':raise
            s=score(p['output'],emails[case['emailId']],case);checked=score_controls(p['output'],controls.get(id,[]))
            attempt={'revision':revision,'output':p['output'],'usage':p['usage'],'status':p['status'],'score':s,'controls':checked,'directory':str(directory)}
            attempts.append(attempt);save(ROOT/'calibration-recovery-20260912'/id/'attempts.private.json',attempts)
            if s['status']=='hit' or p['status']!='completed':break
            prior={'candidate':p['output'],'trainingSourceScore':s,'instruction':'Fix the actual training mismatch while preserving role/threshold semantics. Do not replace a necessary named person with an anonymous headline.'}
        return {'marketId':id,'publicMarket':case['publicInput'],'trainingOutcome':case['expectedOutcome'],'attempts':attempts,'final':attempts[-1],'wasSupervised':True}
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(one,*args) for args in old_jobs]
        for f in concurrent.futures.as_completed(futures):
            r=f.result();results.append(r);save(ROOT/'calibration-recovery-results.private.json',results)
            print(json.dumps({'calibrationTeacherFinished':len(results),'total':len(old_jobs),'status':r['final']['score']['status']}),flush=True)
    good=[r for r in results if r['final']['score']['status']=='hit']
    if not good:raise RuntimeError('No successful calibration demonstration; keep previous prompt')
    packet=[]
    for r in sorted(good,key=lambda r:r['marketId']):
        s=r['final']['score'];packet.append({'developmentPublicMarket':r['publicMarket'],'knownDevelopmentOutcome':r['trainingOutcome'],
            'matchedDevelopmentSource':s['matches'][s['actualIndex']]['text'],'developmentCandidate':r['final']['output'],
            'supervisedTrainingFitNotBlindSuccess':True,'controlsAvailable':bool(r['final']['controls'])})
    prompt=(ROOT/'prompt-nyt-public-context.txt').read_text()+'\nADDITIONAL SUPERVISED CALIBRATION EXAMPLES\nThese cases were initially held out for method selection, then explicitly released as development data after all initial methods missed them. They are NOT final-test cases. Learn headline present tense, title/appositive grammar, active/passive loser roles, and the distinction between a future consequence of a completed nomination and a prediction about that nomination. Do not copy their names or known outcomes into an unrelated new market.\n'+json.dumps(packet,ensure_ascii=False,indent=2)+'\nNow generate the pair for the supplied new publicMarket. Return only the required JSON.'
    (ROOT/'prompt-nyt-calibrated.txt').write_text(prompt)
    save(ROOT/'calibrated-prompt-lineage.json',{'promptSha256':hash_value(prompt),'calibrationMarketIds':[r['marketId'] for r in good],
        'previousFailedAttemptsRetained':True,'calibrationIsTraining':True,'finalTestEvidenceUsed':False,'newSuccessfulDemonstrations':len(good)})
    print(json.dumps({'calibratedPromptReady':True,'successfulDemonstrations':len(good)}),flush=True)

if __name__=='__main__':os.umask(0o077);recover_calibration()
