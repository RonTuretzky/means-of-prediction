"""Score the predeclared runtime capability panel mechanically, outside benchmark selection."""
import argparse,json
import qwen_round1 as q


def summarize(extended=False):
    panel=q.load('runtime-mode-diagnostic-panel.json')['cases']
    items={x['caseId']:x for x in q.load(q.ITEMS)}
    baseline={x['caseId']:x for x in q.load('methods/baseline/development-judgments.private.json')}
    rows=[]
    for entry in panel:
        item=items[entry['caseId']]
        row={**entry,'kind':item['kind'],'expected':item['expected'],'variants':{}}
        for variant in ['baseline','open-grammar','closed-grammar','open-free']+(['open-free-8192'] if extended else []):
            if variant=='baseline':
                record=baseline[item['caseId']];stats=record.get('usage',{});stopped=None
            else:
                directory=q.ROOT/'runtime-probes/sdk-mode'/item['caseId']/variant
                if not (directory/'result.json').exists():row['variants'][variant]={'status':'pending'};continue
                result=q.r.read(directory/'result.json')
                if not (directory/'response.json').exists():row['variants'][variant]={'status':result['status']};continue
                response=q.r.read(directory/'response.json');stats=response['stats'];stopped=stats['stopReason']
                # Do not rescue missing/capped answers or strip invented output text.
                text=response.get('nonReasoningContent') or (response['content'] if not variant.startswith('open-free') else '')
                try:output=json.loads(text);valid=q.valid_judgment(output)
                except (ValueError,TypeError):output=None;valid=False
                record={'trial':1,'status':'completed' if valid and stopped in ['eosFound','stopStringFound'] else 'failed','output':output,'seconds':result['seconds']}
            score=q.score_record(item,record)
            row['variants'][variant]={'status':record['status'],'factual':score['factualOutcome'],'strict':score['settlementOutcome'],
                'groundedFactualPass':score['groundedFactualPass'],'strictPass':score['strictPass'],'falsePositive':score['falsePositive'],
                'stopReason':stopped,'seconds':record.get('seconds'),'stats':stats}
        rows.append(row)
    return {'at':q.r.now(),'rows':rows,'qualification':'Six baseline-selected diagnostic cases, not independent accuracy data. Runtime endpoint/seed interfaces differ from the baseline. SDK variants preserve full rendered bytes except the declared terminal prefix and grammar switch. Failed/capped output is unscorable, never rescued or treated as abstention.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--extended',action='store_true');args=parser.parse_args()
    result=summarize(args.extended)
    print(json.dumps(result),flush=True)
