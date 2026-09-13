"""Read completed development outputs; no model calls or fresh fixture access."""
import argparse, collections, datetime, hashlib, json, os, statistics
from pathlib import Path
BASE=Path('/Users/wk/.local/share/means-of-prediction/slides')
REGEX=BASE/'astra-nyt-round4-20260912'
QWEN=BASE/'astra-qwen-nyt-round1-20260912'
OUT=BASE/'parallel-track-review-20260913'

def compare(method):
    hashes={}
    def read(path):
        data=path.read_bytes();hashes[str(path)]=hashlib.sha256(data).hexdigest();return json.loads(data)
    rx=read(REGEX/'methods/baseline/development-scores.private.json')
    gap=read(REGEX/'methods/baseline/gap-control-scores.private.json')
    qs=read(QWEN/f'methods/{method}/development-scores.private.json')
    summary=read(QWEN/f'methods/{method}/development-summary.json')
    baseline_calls={x['caseId']:x for x in read(QWEN/'methods/baseline/development-judgments.private.json')}
    method_calls={x['caseId']:x for x in read(QWEN/f'methods/{method}/development-judgments.private.json')}
    assert len(baseline_calls)==len(method_calls)==1915 and set(baseline_calls)==set(method_calls)
    items={x['caseId']:x for x in read(QWEN/'development-items-semantic.private.json')}
    cases={x['marketId']:x for x in read(REGEX/'development-cases.private.json')}
    rf=read(REGEX/'controls.json');gf=read(REGEX/'gap-controls.private.json')
    for mid,cs in gf.items():
        if cs:
            assert not rf.get(mid),'Overlapping fixture cohorts';rf[mid]=cs
    assert rf==read(QWEN/'controls.private.json'),'Control contents changed between tracks'
    assert len(qs)==len({x['caseId'] for x in qs})==1915
    rindex={x['marketId']:x for x in rx}
    rc={}
    for x in rx+gap:
        for c in x.get('controls',[]):
            key=(x['marketId'],c['name']);assert key not in rc;rc[key]=c
    fact=[];ctrl=[]
    for q in qs:
        if q['kind']=='factual':
            c=cases[q['marketId']];assert c['emailId']==q['metadata']['emailId']
            labels=c['publicInput']['outcomeLabels'];assert q['expected']==('A' if c['expectedOutcome']==labels[0] else 'B')
            r=rindex[q['marketId']]['factualScore']
            if q['valid'] and r['status'] in ['hit','miss']:
                fact.append((r['status']=='hit',q['factualPass'],q['groundedFactualPass']))
        elif q['kind']=='control':
            i=items[q['caseId']];r=rc[(q['marketId'],i['metadata']['name'])];assert r['expected']==q['expected']
            if q['valid'] and r['scorable']:ctrl.append((r,q))
    pos=[(r,q) for r,q in ctrl if q['expected'] in ['A','B']]
    neg=[(r,q) for r,q in ctrl if q['expected'] not in ['A','B']]
    result={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'regexMethod':'baseline','qwenMethod':method,
      'scope':'Matched completed development cases only; retrospective factual reports are not verified admissible settlements. No fresh test read.',
      'sourceHashes':hashes,'qwenFullDenominators':summary['metrics'],
      'factual':{'fullDenominator':161,'commonCompleted':len(fact),'regexHits':sum(a for a,b,c in fact),'qwenRawHits':sum(b for a,b,c in fact),'qwenExactQuoteGroundedHits':sum(c for a,b,c in fact),'both':sum(a and c for a,b,c in fact),'regexOnly':sum(a and not c for a,b,c in fact),'qwenOnly':sum(not a and c for a,b,c in fact),'neither':sum(not a and not c for a,b,c in fact)},
      'controls':{'fullDenominator':1520,'identicalFixturesVerified':True,'commonScorable':len(ctrl),'positives':len(pos),'negatives':len(neg),'regexPositivePasses':sum(r['passed'] for r,q in pos),'qwenStrictPositivePasses':sum(q['strictPass'] for r,q in pos),'regexNegativeFalsePositives':sum(r['falsePositive'] for r,q in neg),'qwenNegativeFalsePositives':sum(q['falsePositive'] for r,q in neg)},
      'limitations':['Different body representations: complete decoded HTML for regex; complete semantic rendering for Qwen.','Common-completed restriction is not a random sample; full-denominator metrics remain visible.','Exact quote presence is not an entailment check.','Synthetic controls require human review; no measured prompt-injection robustness.','Independent fresh tests use different cohorts and are not a matched comparison.']}
    timing=collections.defaultdict(list)
    for case, b in baseline_calls.items():
        a=method_calls[case]
        if a['status']=='completed' and b['status']=='completed':
            assert a['kind']==b['kind'] and a['marketId']==b['marketId']
            timing[a['kind']].append((b,a));timing['all'].append((b,a))
    result['pairedQwenRuntime']={'scope':'Observed same-case request durations. Both cohorts use four local workers, but scheduling, prefix-cache reuse and added previously unavailable rules can affect durations; this is not a controlled causal speed test.', 'byKind':{}}
    for kind, pairs in sorted(timing.items()):
        measures={'commonCompleted':len(pairs)}
        for name,index in [('baseline',0),('candidate',1)]:
            calls=[pair[index] for pair in pairs]
            durations=[x['seconds'] for x in calls]
            usages=[x.get('usage') or {} for x in calls]
            measures[name]={'medianRequestSeconds':statistics.median(durations),'sumRequestSeconds':sum(durations),
                'knownPromptTokens':sum(u.get('prompt_tokens') or 0 for u in usages),
                'knownCompletionTokens':sum(u.get('completion_tokens') or 0 for u in usages),
                'callsWithPromptUsage':sum(u.get('prompt_tokens') is not None for u in usages),
                'callsWithCompletionUsage':sum(u.get('completion_tokens') is not None for u in usages)}
        measures['medianPairedDurationRatio']=statistics.median(a['seconds']/b['seconds'] for b,a in pairs if b['seconds']>0)
        result['pairedQwenRuntime']['byKind'][kind]=measures
    if method=='baseline':
        old=read(REGEX/'parallel-baseline-comparison.private.json')
        assert result['factual']==old['factual'] and result['controls']==old['controls'],'Baseline reconciliation failed'
    return result

if __name__=='__main__':
    os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('method');a=p.parse_args()
    result=compare(a.method);target=OUT/f'comparison-regex-baseline-qwen-{a.method}.private.json'
    if target.exists():raise SystemExit('Refusing to overwrite an existing comparison')
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'path':str(target),'factual':result['factual'],'controls':result['controls']}))
