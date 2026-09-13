"""Generate a new-market candidate with the frozen NYT method, without mail input."""
import argparse, json, os
from pathlib import Path
from experiment import ROOT,PUBLIC_KEYS,generate,hash_value,load,save
from improve import recover,review_packet
from matcher import compile_pattern
from finalize import verify_selection

def generate_new(public,output_dir):
    if set(public)!=PUBLIC_KEYS:raise ValueError('Input must contain only marketId, question, rules and outcomeLabels')
    if not all(isinstance(public[k],str) and public[k] for k in ['marketId','question','rules']):raise ValueError('Public ID/question/rules must be nonempty strings')
    if not isinstance(public['outcomeLabels'],list) or len(public['outcomeLabels'])!=2 or not all(isinstance(x,str) and x for x in public['outcomeLabels']):raise ValueError('Exactly two outcome labels are required')
    selected=load('frozen-selection.json')
    verify_selection(selected)
    method=selected['method'];prompt=(ROOT/(method+'.txt')).read_text()
    if hash_value(prompt)!=selected['promptHashes'][method+'.txt']:raise RuntimeError('The frozen prompt hash changed')
    case={'marketId':public['marketId'],'publicInput':public,'groupId':'new-market','split':'unseen'}
    output_dir=Path(output_dir)
    previous=None;usage=[]
    steps=selected.get('steps',[{'method':method,'effort':selected['effort'],'tokenGuidance':selected['tokenGuidance']}])
    for i,step in enumerate(steps):
        current=(ROOT/(step['method']+'.txt')).read_text()
        if hash_value(current)!=selected['promptHashes'][step['method']+'.txt']:raise RuntimeError('A frozen step prompt changed')
        context=load('public-contexts.json').get(public['marketId']) if step.get('publicContext') else None
        r=generate(case,current,step['effort'],step['tokenGuidance'],1,output_dir/('step-'+str(i)),extra=review_packet(previous) if i else None,public_context=context)
        r=recover(Path(r['directory'])/'generation.json');previous=r['output'];usage.append(r['usage'])
    output=r['output'];errors=[compile_pattern(output.get(k) if isinstance(output,dict) else None)[1] for k in ['outcomeARegex','outcomeBRegex']]
    result={'publicMarket':public,'candidate':output,'model':'gpt-6-astra','method':method,'promptSha256':hash_value(prompt),
            'generationStatus':r['status'],'tokenUsageByStep':usage,'syntaxErrors':errors,'targetEmailProvided':False,
            'automaticSettlementAuthorized':False,
            'reviewRequired':'Candidate text predicates only. Verify original resolution conditions, false positives and native contract costs before creating a market.'}
    save(output_dir/'candidate.json',result)
    return result

if __name__=='__main__':
    os.umask(0o077);p=argparse.ArgumentParser();p.add_argument('public_market_json');p.add_argument('private_output_directory');a=p.parse_args()
    result=generate_new(json.loads(Path(a.public_market_json).read_text()),a.private_output_directory)
    print(json.dumps({'candidateFile':str(Path(a.private_output_directory).resolve()/'candidate.json'),'model':result['model'],
                      'method':result['method'],'generationStatus':result['generationStatus'],'syntaxErrors':result['syntaxErrors']}))
