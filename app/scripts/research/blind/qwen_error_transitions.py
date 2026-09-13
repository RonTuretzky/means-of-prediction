"""Read-only paired error classification after a complete development method."""
import collections,json,sys
import qwen_round1 as q

def classify(old,new):
    if old['caseId']!=new['caseId'] or old['expected']!=new['expected'] or old['kind']!=new['kind']:
        raise ValueError('Paired development labels differ')
    if not new['valid']:return 'unscorable'
    if new['strictPass']:return 'correct_predicate_outcome'
    if new['settlementOutcome']=='NEITHER':return 'abstained'
    if new['settlementOutcome']=='CONFLICT':return 'conflict'
    return 'wrong_predicate_outcome'

def compare(method):
    if not (q.ROOT/'methods'/method/'development-summary.json').exists():
        raise RuntimeError('A complete method is required; no partial accuracy inspection')
    old={x['caseId']:x for x in q.load('methods/baseline/development-scores.private.json')}
    new={x['caseId']:x for x in q.load('methods/'+method+'/development-scores.private.json')}
    if set(old)!=set(new):raise RuntimeError('Cohort differs')
    changes={key:classify(row,new[key]) for key,row in old.items()}
    output={'at':q.r.now(),'method':method,'cohortRows':len(old),
        'sourceHashes':{m:q.r.digest(q.ROOT/'methods'/m/'development-scores.private.json') for m in ['baseline',method]},
        'qualification':'Development diagnostics only. Correct predicate outcomes use provisional synthetic labels. Abstention is distinct from repairing a wrong positive side. Natural factual labels do not establish strict settlement.'}
    for name,field in [('oldWrongPositiveSide','wrongOutcome'),('oldNegativeFalseClaim','falsePositive')]:
        selected=[row for row in old.values() if row['kind']=='control' and row[field] is True]
        output[name]={'cases':len(selected),'transitions':dict(collections.Counter(changes[x['caseId']] for x in selected)),
            'rows':[{'caseId':x['caseId'],'marketId':x['marketId'],'expected':x['expected'],
                'baseline':x['settlementOutcome'],'candidate':new[x['caseId']]['settlementOutcome'],'transition':changes[x['caseId']]} for x in selected]}
        introduced=[row for row in new.values() if row['kind']=='control' and row[field] is True and old[row['caseId']][field] is not True]
        output[name]['introduced']={'total':len(introduced),'baselineCompleted':sum(old[x['caseId']]['valid'] for x in introduced),
            'baselineUnavailable':sum(not old[x['caseId']]['valid'] for x in introduced),'caseIds':[x['caseId'] for x in introduced]}
    natural=[row for row in old.values() if row['kind']=='factual' and row['factualPass'] and not row['groundedFactualPass']]
    def quote_transition(row):
        target=new[row['caseId']]
        return 'unscorable' if not target['valid'] else 'correct_exact_quote' if target['groundedFactualPass'] else 'correct_fact_without_exact_quote' if target['factualPass'] else 'factual_recall_lost'
    output['oldCorrectFactualWithoutQuote']={'cases':len(natural),'transitions':dict(collections.Counter(quote_transition(x) for x in natural)),
        'rows':[{'caseId':x['caseId'],'transition':quote_transition(x)} for x in natural]}
    return output

if __name__=='__main__':
    method=sys.argv[1];value=compare(method);name='methods/'+method+'/paired-error-transitions.private.json'
    if (q.ROOT/name).exists():raise RuntimeError('Prior diagnostic already exists')
    q.once(name,value)
    print(json.dumps({'method':method,'report':str(q.ROOT/name),
        'counts':{key:{k:v for k,v in value[key].items() if k not in ['rows','introduced']} for key in
            ['oldWrongPositiveSide','oldNegativeFalseClaim','oldCorrectFactualWithoutQuote']}},ensure_ascii=False))
