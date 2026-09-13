"""Independent CPU-only label/disposition and aggregate reconciliation."""
import ast,collections,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=Path('/Users/wk/conductor/workspaces/research/porto-novo')
sys.path.insert(0,str(REPO/'app/scripts/research/answerability'))
import combined_v1 as c
import real_answerability_remaining_audit_v1 as raw_audit
ROOT=c.ROOT
SUPPORT=c.a.q.ROOT/'source-check-independent-review-v1/audit.py'
# Load only the two previously tested pure functions; importing its full module
# would add unrelated source-check modules to the frozen annotation import closure.
namespace={'collections':collections}
functions=[n for n in ast.parse(SUPPORT.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ['strict','measure']]
assert {n.name for n in functions}=={'strict','measure'}
exec(compile(ast.Module(body=functions,type_ignores=[]),str(SUPPORT),'exec'),namespace)
strict_fn,measure_fn=namespace['strict'],namespace['measure']
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
plan=c.a.verify_plan();report=read(ROOT/'raw-audit.private.json')
assert sha(ROOT/'adjudicated-labels.private.json')=='32bd48488b024bb0f81357f1d6efd0c724efd342ce33f1372715c4b1746ec876'
assert sha(ROOT/'combined-label-seal.private.json')=='f126a28f522f27249c63915ff45432a83ac4f64a4e22a82203a8f969f85b5362'
raw_audit.ensure_dead(read(ROOT/'run-started.json')['pid'])
assert report['rows']==[raw_audit.reconcile(e) for e in plan['entries']]
eligible=c.audit_gate(report,plan);assert sum(eligible.values())==99
labels,selected=c.checked_labels();old=read(c.OLD/'adjudicated-labels.private.json');new=read(ROOT/'adjudicated-labels.private.json')
assert labels[:60]==old and labels[60:]==new and len(labels)==161
assert sha(c.OLD/'adjudicated-labels.private.json')=='f5a89076ae95dc93c0adbac4e7b3725dd525abb8db38d4c8da87811c34c446fa'
seal=read(ROOT/'combined-label-seal.private.json');comparison=read(ROOT/'combined-baseline-comparison.private.json')
assert c.dependencies()==seal['dependencies'] and c.a.q.r.hash_value(labels)==seal['combinedLabelsSha256']
assert seal['baselineHashes']==c.a.prior_scoring.METHOD_HASHES
c.a.check_hashes(seal['baselineHashes'])
assert comparison['labelSealSha256']==sha(ROOT/'combined-label-seal.private.json')
assert datetime.fromisoformat(seal['at'])<datetime.fromisoformat(comparison['at'])
review=read(ROOT/'root-adjudication-record.private.json');groups=review['independentlyAuthoredReasonGroups'];indices=[i for xs in groups.values() for i in xs];invalid=review['unresolvedInvalidPairs']
assert len(indices)==99 and len(set(indices))==99 and set(indices).isdisjoint(invalid) and sorted(indices+invalid)==list(range(101))
for group,xs in groups.items():
 for i in xs:assert new[i]['caseId']==plan['selected'][i]['caseId'] and new[i]['reviewGroup']==group and new[i]['reviewStatus']=='adjudicated' and new[i]['settlementOutcome']=='INSUFFICIENT'
for i in invalid:assert not eligible[new[i]['caseId']] and new[i]['reviewStatus']=='unresolved' and new[i]['settlementOutcome']=='AMBIGUOUS' and new[i]['unresolvedKind']=='annotation_incomplete'
sem=read(ROOT/'independent-semantic-review.private.json');corrected={new[i]['caseId'] for i in review['futureFallbackCorrections']}
assert corrected=={x['caseId'] for x in sem['cases'] if x['futureConfirmationHardenedByBothPasses']}
for i in review['futureFallbackCorrections']:assert new[i]['blockingConditions']==['source'] and new[i]['annotationCorrection']
assert review['originalRulesReadingRecordSha256']==sha(ROOT/'root-original-rules-reading.private.json')
assert review['worksheetSha256']==sha(ROOT/'review-material/worksheet.private.json')
# Derive Qwen decisions from raw-verified original outputs, not cached score decisions.
qphase={'factualRows':161,'rawResponsesVerified':0,'unscorableRows':0}
qr=[r for r in c.a.q.load('methods/baseline/development-judgments.private.json') if r['kind']=='factual'];items={x['caseId']:x for x in c.a.q.load(c.a.q.ITEMS)}
assert len(qr)==161 and {r['caseId'] for r in qr}=={x['caseId'] for x in labels}
strict={};quoted={}
for r in qr:
 output=r.get('output');valid=r['status']=='completed' and c.a.q.valid_judgment(output)
 if valid:
  directory=Path(r['directory']);raw=json.loads((directory/'response.raw').read_bytes());request=read(directory/'request.json')
  assert sha(directory/'response.raw')==r['rawResponseSha256'] and sha(directory/'response.json')==r['responseSha256']
  assert raw==read(directory/'response.json') and raw['model']==request['model']==r['returnedModel']
  assert c.a.q.r.hash_value(request)==r['requestSha256'] and r['httpStatus']==200
  choice=raw['choices'][0];assert choice['finish_reason']=='stop' and json.loads(choice['message']['content'])==output and raw['usage']==r['usage']
  qphase['rawResponsesVerified']+=1
 else:qphase['unscorableRows']+=1
 x=strict_fn(output) if valid else 'UNSCORABLE'
 exact=bool(valid and output['evidenceQuote'] and output['evidenceQuote'] in c.a.q.evidence_text(items[r['caseId']]['email']))
 strict[r['caseId']]=x;quoted[r['caseId']]=x if x not in ['A','B'] or exact else 'NEITHER'
rr=[r for r in read(c.a.prior_scoring.REGEX) if r.get('factualScore') is not None]
assert len(rr)==161 and len({r['marketId'] for r in rr})==161
regex={}
for r in rr:
 f=r['factualScore']
 if r['status']!='completed' or not f.get('validPair') or f['status'] not in ['hit','miss','wrong-outcome','conflict']:x='UNSCORABLE'
 else:
  matches=f['matches'];assert len(matches)==2
  a,b=[m is not None for m in matches];x='CONFLICT' if a and b else 'A' if a else 'B' if b else 'NEITHER'
 regex[r['marketId']]=x
ds={'regexCandidateSide':{s['caseId']:regex[s['marketId']] for s in selected},'qwenStrictSide':strict,'qwenStrictSideWithExactQuote':quoted}
metrics={k:measure_fn(labels,x) for k,x in ds.items()};assert metrics==comparison['methods']
disp=dict(collections.Counter(l['reviewStatus']+':'+l['settlementOutcome'] for l in labels));assert disp==comparison['labelDispositions']
unresolved=dict(collections.Counter(l.get('unresolvedKind','rule_or_evidence_ambiguity') for l in labels if l['reviewStatus']=='unresolved'));assert unresolved==comparison['unresolvedKinds']
by_id={s['caseId']:s for s in selected};answerable=[l['caseId'] for l in labels if l['reviewStatus']=='adjudicated' and l['settlementOutcome'] in ['A','B']]
assert len({by_id[c]['emailId'] for c in answerable})==comparison['answerableEmails']==1
assert len({by_id[c]['family'] for c in answerable})==comparison['answerableFamilies']==1
paths=[ROOT/n for n in ['plan.private.json','raw-audit.private.json','adjudicated-labels.private.json','root-adjudication-record.private.json','combined-label-seal.private.json','combined-baseline-comparison.private.json','independent-semantic-review.private.json']]+[c.OLD/'adjudicated-labels.private.json',SUPPORT,REPO/'app/scripts/research/answerability/combined_v1.py',Path(__file__)]
out={'at':datetime.now(timezone.utc).isoformat(),'sourceHashes':{str(p):sha(p) for p in paths},'verified':{'rawResponsesReconciled':202,'eligibleNewPairs':99,'unresolvedNewPairs':2,'prior60PreservedVerbatim':True,'priorEntireTreePinsVerified':True,'combinedExact161Union':True,'reasonGroupIndicesCover99Exactly':True,'invalidIndicesCoverRemaining2':True,'futureFallbackCorrectionsMatchIndependentReview':9,'labelSealPredatesScore':True,'qwenRawAudit':qphase,'aggregateMatchesRoot':True},'labelDispositions':disp,'unresolvedKinds':unresolved,'methods':metrics,'qualification':'Read-only independent integrity, index/group and arithmetic reconciliation. Targeted10-case semantic review previously completed; no independent semantic adjudication of the other89 pairs is claimed. Model-adjudicated exposed development data, not human gold or live settlement evidence.'}
with (HERE/'audit.private.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({'sha256':sha(HERE/'audit.private.json'),'dispositions':disp,'methods':metrics},indent=2))
