"""Read-only replay of a fixed rejection rule. No model requests or score mutation."""
import collections, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
STUDY=HERE.parent/'astra-qwen-nyt-round1-20260912'
SOURCE=STUDY/'source-check-v1'
PANEL=HERE.parent/'real-answerability-v1-20260913'
BLIND=Path('/Users/wk/conductor/workspaces/research/porto-novo/app/scripts/research/blind')
sys.path.insert(0,str(BLIND))
import qwen_round1 as q
import qwen_final_audit as audit
POLICIES=['raw','exact_quote','exact_quote_empty_missing']
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def once(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def decisions(status,output,body):
 if status!='completed':return {p:'UNSCORABLE' for p in POLICIES}
 if not q.valid_judgment(output):raise ValueError('Completed invalid output')
 d=q.settlement(output);exact=bool(output['evidenceQuote']) and output['evidenceQuote'] in body
 # Conflicting raw outputs remain conflict diagnostics, never accepted directions.
 return {'raw':d,'exact_quote':d if d not in ['A','B'] or exact else 'NEITHER',
  'exact_quote_empty_missing':d if d not in ['A','B'] or (exact and output['missingConditions']==[]) else 'NEITHER'}
def metrics(rows,policy):
 positive=[r for r in rows if r['expected'] in ['A','B']]
 negative=[r for r in rows if r['expected']=='INSUFFICIENT']
 completed=lambda r:r['decisions'][policy]!='UNSCORABLE'
 return {'total':len(rows),'completed':sum(map(completed,rows)),
  'failures':sum(not completed(r) for r in rows),'positiveTotal':len(positive),
  'positiveCompleted':sum(map(completed,positive)),
  'correctPositive':sum(r['decisions'][policy]==r['expected'] for r in positive),
  'wrongSidePositive':sum(r['decisions'][policy] in ['A','B'] and r['decisions'][policy]!=r['expected'] for r in positive),
  'positiveAbstentions':sum(r['decisions'][policy]=='NEITHER' for r in positive),
  'positiveConflicts':sum(r['decisions'][policy]=='CONFLICT' for r in positive),
  'negativeTotal':len(negative),'negativeCompleted':sum(map(completed,negative)),
  'negativeDirectionalClaims':sum(r['decisions'][policy] in ['A','B'] for r in negative),
  'negativeConflicts':sum(r['decisions'][policy]=='CONFLICT' for r in negative),
  'negativeDirectionalOrConflictingClaims':sum(r['decisions'][policy] in ['A','B','CONFLICT'] for r in negative),
  'negativeRejections':sum(r['decisions'][policy]=='NEITHER' for r in negative),
  'unresolved':sum(r['expected']=='AMBIGUOUS' for r in rows),
  'nonbinary':sum(r['expected']=='NONBINARY' for r in rows)}
def main():
 protocol=read(HERE/'protocol.json')
 for p,h in protocol['inputAndSourceHashes'].items():assert sha(Path(p))==h,p
 raw_audit=audit.verify_phase('baseline','development')
 records=q.load('methods/baseline/development-judgments.private.json');items={x['caseId']:x for x in q.load(q.ITEMS)}
 selected=[x for x in records if x['kind']=='control'];assert len(selected)==1520 and len({x['caseId'] for x in selected})==1520
 controls=[]
 for row in selected:
  item=items[row['caseId']];output=row.get('output')
  controls.append({'caseId':row['caseId'],'marketId':row['marketId'],'status':row['status'],
   'expected':item['expected'] if item['expected'] in ['A','B'] else 'INSUFFICIENT',
   'decisions':decisions(row['status'],output,q.evidence_text(item['email'])),
   'missingConditions':output['missingConditions'] if row['status']=='completed' else None,
   'metadata':item['metadata']})
 assert sum(x['expected'] in ['A','B'] for x in controls)==608
 source_report=read(SOURCE/'audited-results.private.json');ind=read(STUDY/'source-check-independent-review-v1/audit.private.json')
 assert ind['rootAuditSha256']==sha(SOURCE/'audited-results.private.json')
 for name,h in source_report['artifactHashes'].items():assert sha(SOURCE/name)==h
 plan=read(SOURCE/'plan-amended-v2.private.json');entries={e['name']:e for e in plan['entries']}
 labels={l['caseId']:l for l in read(PANEL/'adjudicated-labels.private.json')};real={v:[] for v in ['baseline','source_check']}
 for row in source_report['rows']:
  name=row['name'];v,cid=name.split('/');entry=entries[name];l=labels[cid]
  assert entry['caseId']==cid
  if row['status']=='completed':
   for p,h in row['fileHashes'].items():assert sha(SOURCE/p)==h
   result=read(SOURCE/'responses'/name/'result.json');output=result['output']
   request=read(SOURCE/'responses'/name/'request.json');assert request==entry['request']
   body=json.loads(request['messages'][1]['content'])['email']['completeSemanticText']
  else:output=None;body='';assert entry['request'] is None and row['status']=='rule_unavailable'
  real[v].append({'caseId':cid,'marketId':entry['marketId'],'status':row['status'],
   'expected':l['settlementOutcome'] if l['reviewStatus']=='adjudicated' else 'AMBIGUOUS',
   'decisions':decisions(row['status'],output,body),
   'missingConditions':output['missingConditions'] if output else None,'blockingConditions':l['blockingConditions']})
 assert all(len(rs)==60 and len({x['caseId'] for x in rs})==60 for rs in real.values())
 def summarize(rs):
  return {p:metrics(rs,p) for p in POLICIES}
 out={'at':datetime.now(timezone.utc).isoformat(),'protocolSha256':sha(HERE/'protocol.json'),
  'baselineRawAudit':raw_audit,'natural':{v:summarize(rs) for v,rs in real.items()},
  'syntheticBaseline':summarize(controls),'naturalRows':real,'controlRows':controls,
  'interpretation':protocol['qualifications']}
 once(HERE/'result.private.json',out)
 print(json.dumps({k:v for k,v in out.items() if k not in ['naturalRows','controlRows','baselineRawAudit']},indent=2))
if __name__=='__main__':main()
