"""Post-hoc paired review; consumes only independently raw-audited development outputs."""
import collections, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'source-check-v1'
PANEL=Path('/Users/wk/.local/share/means-of-prediction/slides/real-answerability-v1-20260913')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
report=read(ROOT/'audited-results.private.json');ind=read(HERE/'audit.private.json')
assert ind['rootAuditSha256']==sha(ROOT/'audited-results.private.json')
plan=read(ROOT/'plan-amended-v2.private.json');labels=read(PANEL/'adjudicated-labels.private.json')
entries={e['name']:e for e in plan['entries']};rows={v:{} for v in ['baseline','source_check']}
for row in report['rows']:
 v,cid=row['name'].split('/');rows[v][cid]=row
notes={
'10499a069c314a0d46cea3776b76c893018102bd0a9c3aa6391aa81ceb24ceb0':'Withdraws an Oklahoma margin claim and names missing official counts/source. This is consistent with the sealed insufficiency label; the output also lists candidate-positive requirements while assessing the overall pair, so it is not a reliable minimal logical explanation.',
'170b4f54f29662688fe4154d61b06d6f4d3095a7061b6b92f4a48a76ed4c6ef8':'Withdraws another Oklahoma margin claim, now explicitly citing official winner/count source and finality. These two Oklahoma observations share one fact; they are not independent evidence of general improvement.',
'cd6d4cc4a53fc223d64793d9bd29d4c744212a427c268f6c087292d187dd2efa':'Withdraws South Carolina margin claim; specifically lists final official vote count and official/consensus source route. Does not establish that the source-check appendix alone caused the change.',
'e81855326b7adf180170179ea7293286f14cc2128bd69064db05ead442c64b27':'Withdraws Massachusetts margin claim and cites official totals/finality. Factual CONFLICT remains despite a one-sided report, so correct abstention is not evidence of correct factual interpretation.',
'f8a1a19d9d2ef30e5ab8160d2e9964832e09d76863ef83c9ff193fb3bd24c828':'Withdraws SHEIN IPO claim. Final consensus source requirement is absent from the email, supporting abstention; however the explanation demands an official announcement even though the generated rule permits credible news for completion, and its consensus explanation is directed at No. Correct strict abstention does not validate the explanation.',
'22c54719ec158fb7ec2aecdfc1eaba61035eb50ce470137ae9d765a290133f77':'Withdraws Zverev advancement claim while again invoking September 27 confirmation and tournament-noncancellation as current prerequisites. Baseline generated rule already hardens the original future fallback. The original source route remains absent, but this is not clean evidence that Qwen learned the correct branch interpretation.',
'00fae3b9fd552cd9ce78d8a3bcec7107598e2c22cf80a89dc52a304cac13d15b':'New unsupported Shelton advancement A claim, with empty missingConditions, despite generated official/consensus source requirement. Baseline had abstained. The same generated rule also hardens future confirmation, but the independent source gap does not depend on that disputed hardening.',
'bb9add839d7d78618e16ae781412a87f4d3aeb01b156b6efcbc73f5cd8c6e695':'Withdraws Navarro tournament-win B. Correct source abstention, but explanation also requires a declared champion even though generated B explicitly permits early elimination/impossibility. The withdrawal cannot be characterized as wholly correct rule reasoning.',
'8f723b9944c9625c7813873e86874f069bb37d0a65f71235fdfe71eefab66809':'New Andreeva tournament-win B from a brief match report that does not identify this US Open. Output acknowledges missing official result and match identity while granting B; strict source/identity adherence remains inconsistent. A final or decisive round is not required for early elimination, so part of its explanation is itself too strong.',
'62720784a21c46e45bbe9fb36e872a6ffa7076e580d6f3c02e51d55b3f32eaaa':'Withdraws Alcaraz quarterfinal A with correct factual A; explanation again relies on future confirmation/nocancellation requirements inherited from the hardened baseline rule. The original source gap remains, but do not treat the future fallback as the original present prerequisite.',
'3263e2a66b51391af351934ae56268051ca649ba373c750633bc118e5ae68a21':'New Over-4.5-sets A from a report explicitly saying Zverev won in straight sets. Both factual A and strict A invert the generated threshold in this mens Grand Slam match. Source route is also unestablished and missingConditions is empty. This is not merely conservative source disagreement.'}
summary={};detail={}
for policy in ['strict','quoted']:
 counts=collections.Counter();categories={};changes=[]
 for l in labels:
  cid=l['caseId'];b=rows['baseline'][cid];c=rows['source_check'][cid]
  if l['settlementOutcome']!='INSUFFICIENT' or b['status']!='completed' or c['status']!='completed':continue
  def decision(x):return 'NEITHER' if policy=='quoted' and x['decision'] in ['A','B'] and not x['exactQuote'] else x['decision']
  bd,cd=decision(b),decision(c);bc,cc=bd in ['A','B','CONFLICT'],cd in ['A','B','CONFLICT']
  key=f'{int(bc)}->{int(cc)}';counts[key]+=1;category='+'.join(sorted(l['blockingConditions']));categories.setdefault(category,collections.Counter())[key]+=1
  if bc!=cc:
   changes.append({'caseId':cid,'marketId':entries['baseline/'+cid]['marketId'],'baselineDecision':bd,'sourceCheckDecision':cd,'category':category,'rawDecisionsUnchanged':b['decision']==c['decision']})
   if cid not in detail:
    detail[cid]={'label':l,'requests':{},'outputs':{},'fileHashes':{}}
    for v in rows:
     name=v+'/'+cid;p=ROOT/'responses'/name
     detail[cid]['requests'][v]=read(p/'request.json')
     detail[cid]['outputs'][v]=read(p/'result.json')['output']
     detail[cid]['fileHashes'][v]={x.name:sha(x) for x in p.iterdir() if x.is_file()}
 summary[policy]={'commonCompletedInsufficient':sum(counts.values()),'claimTransitions':dict(counts),'byFrozenBlockingConditions':{k:dict(v) for k,v in categories.items()},'changes':changes}
assert set(notes)=={x['caseId'] for x in summary['strict']['changes']}
for cid,note in notes.items():detail[cid]['manualReview']=note
out={'protocol':'Post-hoc diagnostic over frozen exposed-development cases. Source-category grouping uses the original adjudication blockers; it is not an independent new label audit. All score decisions reconstruct the independently raw-audited output. No prompt changes, inference, selection or promotion.',
'sourceHashes':{'plan':sha(ROOT/'plan-amended-v2.private.json'),'rootAudit':sha(ROOT/'audited-results.private.json'),'independentAudit':sha(HERE/'audit.private.json'),'labels':sha(PANEL/'adjudicated-labels.private.json'),'script':sha(Path(__file__))},
'paired':summary,'baselineReplayAgainstOldDevelopment':ind['baselineReplayAgainstOldDevelopment'],
'interpretation':['Raw strict claims drop 41 to 36: 8 withdrawals, 3 new unsupported claims, 33 persist, 9 remain abstentions. The 53 rows share events and emails; they are not independent draws.',
'Quoted claims drop 32 to 26: 8 withdrawals and 2 additions. Two withdrawals are only quote-format losses with unchanged raw claims (Alcaraz link-marker whitespace and UMass removed link marker); both additions repair quotes for unchanged unsupported raw claims. Quote filtering is not source entailment.',
'Of 13 official-count+source rows, claims fall 8 to 4. Of 39 source-only rows, claims fall 32 to 31. The one commonly available fixture-time row retains its raw claim. Three new raw claims are all source-only.',
'Both variants retain the single answerable Tupac pair. This tiny positive denominator cannot establish general recall or justify promotion.',
'Baseline replay changes strict decision in 5/55, factual decision in 7/55, full JSON in 27/55. Concurrent alternating dispatch is not serial crossover or a deterministic-runtime guarantee.',
'Several nominally correct abstentions cite invented or hardened prerequisites. The next benchmark must distinguish correct abstention from correct explanation and evaluate ordinary/fallback source branches separately.'],
'cases':detail}
p=HERE/'paired-diagnostic.private.json'
with p.open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'sha256':sha(p),'strict':summary['strict']['claimTransitions'],'quoted':summary['quoted']['claimTransitions'],'reviewedStrictChanges':len(notes),'archivedCaseContexts':len(detail)},indent=2))
