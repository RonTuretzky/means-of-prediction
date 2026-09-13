"""Seal complementary real-email labels, then compare untouched baselines.

Stored separately from the frozen blind-run source directory. No inference.
The first60 labels are preserved verbatim; incomplete new reviews stay unresolved.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blind'))
import real_answerability_remaining_v1 as a

ROOT=a.ROOT
OLD=a.PRIOR


def audit_gate(report, plan):
    expected={e['name'] for e in plan['entries']}
    rows=report['rows'];names=[r['name'] for r in rows]
    if report['partial'] or report['accountedFor']!=202 or len(names)!=202 or set(names)!=expected:
        raise RuntimeError('Full unique202-row raw audit required')
    if report['planSha256']!=a.q.r.digest(ROOT/'plan.private.json') or report['auditorSha256']!=plan['pins'][str(a.HERE/'real_answerability_remaining_audit_v1.py')]:
        raise RuntimeError('Raw audit lineage differs')
    for row in rows:
        for name,sha in row['fileHashes'].items():
            path=ROOT/name
            if not path.resolve().is_relative_to(ROOT.resolve()) or a.q.r.digest(path)!=sha:
                raise RuntimeError('Audited raw file changed')
    indexed={r['name']:r for r in rows}
    eligible={s['caseId']:all(indexed[p+'/'+s['caseId']]['status']=='completed' and indexed[p+'/'+s['caseId']]['rawVerified'] for p in a.original.PASSES) for s in plan['selected']}
    if report['pairsEligibleForAdjudication']!=eligible or report['eligiblePairCount']!=sum(eligible.values()):
        raise RuntimeError('Audited pair eligibility differs')
    return eligible


def validate_labels(labels, selected, eligible, job_reader):
    ids={s['caseId'] for s in selected}
    if len(labels)!=101 or len(ids)!=101 or {r['caseId'] for r in labels}!=ids:
        raise ValueError('All101 new pairs require one explicit disposition')
    for row in labels:
        cid=row['caseId']
        if row['settlementOutcome'] not in a.prior_scoring.ALLOWED or row['reviewStatus'] not in ['adjudicated','unresolved']:
            raise ValueError('Invalid label status')
        if row.get('humanValidated') is not False or not row.get('reviewer') or not row.get('reason'):
            raise ValueError('Explicit model-review provenance required')
        if not eligible[cid] and (row['reviewStatus']!='unresolved' or row['settlementOutcome']!='AMBIGUOUS' or row.get('unresolvedKind')!='annotation_incomplete'):
            raise ValueError('Incomplete dual review must remain annotation-incomplete')
        if row['reviewStatus']=='unresolved' and row['settlementOutcome'] in ['A','B','NONBINARY']:
            raise ValueError('Unresolved pair cannot become answerable')
        if row['reviewStatus']=='adjudicated' and row.get('reviewedPasses')!=['a','b']:
            raise ValueError('Both isolated reviews must be adjudicated')
        job,sha=job_reader(cid)
        if row['jobSha256']!=sha:
            raise ValueError('Adjudication input differs')
        quotes=row['supportingQuotes'];body=job['input']['completeEmail']['completeSemanticText']
        if not isinstance(quotes,list) or any(not isinstance(q,str) or not q or q not in body for q in quotes):
            raise ValueError('Non-exact adjudication quote')
        if row['settlementOutcome'] in ['A','B','NONBINARY'] and not quotes:
            raise ValueError('Answerable label needs a supporting quote')


def job_reader(cid):
    path=ROOT/'jobs/a'/(cid+'.json')
    return a.q.r.read(path),a.q.r.digest(path)


def dependencies():
    paths=[Path(__file__),Path(__file__).with_name('test_combined_v1.py'),ROOT/'plan.private.json',
        ROOT/'raw-audit.private.json',ROOT/'adjudicated-labels.private.json',OLD/'adjudicated-labels.private.json',OLD/'adjudicated-labels-seal.json']
    return {str(p):a.q.r.digest(p) for p in paths}


def checked_labels():
    plan=a.verify_plan()
    eligible=audit_gate(a.q.r.read(ROOT/'raw-audit.private.json'),plan)
    labels=a.q.r.read(ROOT/'adjudicated-labels.private.json')
    validate_labels(labels,plan['selected'],eligible,job_reader)
    prior=a.q.r.read(OLD/'adjudicated-labels.private.json')
    selected=a.q.r.read(OLD/'plan.private.json')['selected']+plan['selected']
    combined=prior+labels
    if len(combined)!=161 or len({r['caseId'] for r in combined})!=161 or {r['caseId'] for r in combined}!={s['caseId'] for s in selected}:
        raise RuntimeError('Combined cohort not exact161 disjoint union')
    return combined,selected


def seal():
    labels,selected=checked_labels()
    a.check_hashes(a.prior_scoring.METHOD_HASHES)
    a.once(ROOT/'combined-label-seal.private.json',{'at':a.q.r.now(),'dependencies':dependencies(),
        'baselineHashes':a.prior_scoring.METHOD_HASHES,'priorLabelsPreservedVerbatim':True,
        'combinedLabelsSha256':a.q.r.hash_value(labels),'pairs':161,
        'qualification':'Correlated exposed development labels, model-adjudicated only. Original60 unchanged; incomplete annotation pairs unresolved. This seal precedes the scorer loading baseline predictions.'})
    print(json.dumps({'labelSealSha256':a.q.r.digest(ROOT/'combined-label-seal.private.json'),'pairs':161}))


def decisions(labels, selected, qrows, rrows):
    qids=[r['caseId'] for r in qrows];rmids=[r['marketId'] for r in rrows]
    if len(qids)!=len(set(qids)) or len(rmids)!=len(set(rmids)):
        raise ValueError('Duplicate baseline records')
    qi={r['caseId']:r for r in qrows};ri={r['marketId']:r for r in rrows}
    if set(qi)!={r['caseId'] for r in labels} or set(ri)!={r['marketId'] for r in selected}:
        raise ValueError('Baseline cohort differs from combined labels')
    regex={s['caseId']:a.prior_scoring.regex_decision(ri[s['marketId']]) for s in selected}
    strict={cid:row['settlementOutcome'] for cid,row in qi.items()}
    quoted={cid:side if qi[cid]['exactQuote'] or side not in ['A','B'] else 'NEITHER' for cid,side in strict.items()}
    return {'regexCandidateSide':regex,'qwenStrictSide':strict,'qwenStrictSideWithExactQuote':quoted}


def score():
    seal=a.q.r.read(ROOT/'combined-label-seal.private.json')
    if dependencies()!=seal['dependencies'] or seal['baselineHashes']!=a.prior_scoring.METHOD_HASHES:
        raise RuntimeError('Post-seal dependency differs')
    labels,selected=checked_labels()
    if a.q.r.hash_value(labels)!=seal['combinedLabelsSha256']:
        raise RuntimeError('Combined labels changed')
    a.check_hashes(seal['baselineHashes'])
    qr=[r for r in a.q.r.read(a.prior_scoring.QWEN) if r['kind']=='factual']
    rr=[r for r in a.q.r.read(a.prior_scoring.REGEX) if r.get('factualScore') is not None]
    outputs=decisions(labels,selected,qr,rr)
    by_id={s['caseId']:s for s in selected}
    answerable=[r['caseId'] for r in labels if r['reviewStatus']=='adjudicated' and r['settlementOutcome'] in ['A','B']]
    result={'at':a.q.r.now(),'labelSealSha256':a.q.r.digest(ROOT/'combined-label-seal.private.json'),
        'pairs':161,'answerableEmails':len({by_id[c]['emailId'] for c in answerable}),
        'answerableFamilies':len({by_id[c]['family'] for c in answerable}),
        'labelDispositions':dict(collections.Counter(r['reviewStatus']+':'+r['settlementOutcome'] for r in labels)),
        'unresolvedKinds':dict(collections.Counter(r.get('unresolvedKind','rule_or_evidence_ambiguity') for r in labels if r['reviewStatus']=='unresolved')),
        'methods':{name:a.prior_scoring.measure(labels,value) for name,value in outputs.items()},
        'qualification':'Full existing natural-pair inventory, not all Polymarket markets or independent human gold. Original source/metadata scope. Regex candidate detector is not a complete source/time verifier. No contract execution or projected deployment accuracy.'}
    a.once(ROOT/'combined-baseline-comparison.private.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    import os
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['seal','score'])
    args=parser.parse_args();globals()[args.command]()
