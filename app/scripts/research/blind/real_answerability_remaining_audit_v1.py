"""Raw gate for the separate101-pair extension; never reads model predictions."""
import argparse
import collections
import json
import math
import os
from pathlib import Path

import real_answerability_remaining_v1 as a


def ensure_dead(pid):
    if type(pid) is not int or pid<=1:raise ValueError('Invalid owner PID')
    try:os.kill(pid,0)
    except ProcessLookupError:return
    raise RuntimeError('Annotation runner remains alive')


def known(values):
    xs=[x for x in values if type(x) in [int,float] and math.isfinite(x) and x>=0]
    return {'knownTotal':sum(xs),'missingOrInvalid':len(values)-len(xs),'isLowerBound':len(xs)!=len(values)}


def reconcile(entry):
    root=a.ROOT;directory=root/'responses'/entry['name']
    job=a.q.r.read(root/'jobs'/(entry['name']+'.json'))
    files={str(p.relative_to(root)):a.q.r.digest(p) for p in directory.rglob('*') if p.is_file()}
    if not directory.exists():
        return {'name':entry['name'],'status':'unattempted','rawVerified':False,'fileHashes':{},'requestCount':0,
                'inputTokens':None,'outputTokens':None,'seconds':None,'usage':None}
    marker=a.q.r.read(directory/'attempt-started.json')
    if marker['jobSha256']!=entry['jobSha256']:
        raise RuntimeError('Attempt input marker differs')
    request_path=directory/'model-request.json'
    if (directory/'job.json').exists() and a.q.r.read(directory/'job.json')!=job:
        raise RuntimeError('Actual job differs')
    if request_path.exists() and a.q.r.read(request_path)!=a.build_request(job):
        raise RuntimeError('Actual model request differs from blind job')
    transport_path=directory/'transport-result.json'
    if not transport_path.exists():transport_path=directory/'transport-checkpoint.json'
    transport=a.q.r.read(transport_path) if transport_path.exists() else {}
    requests=transport.get('requests',[])
    if len(requests)>1 or any(not request_path.exists() or r.get('requestSha256')!=a.q.r.digest(request_path) for r in requests):
        raise RuntimeError('Extra request or incorrect wire hash')
    events=transport.get('events',[])
    responses=[e['response'] for e in events if isinstance(e.get('response'),dict)]
    if len(responses)>1 or any(r.get('model') not in [None,'gpt-6-astra'] for r in responses):
        raise RuntimeError('Response model or terminal-event count differs')
    usage=next((r['usage'] for r in responses if r.get('usage') is not None),None)
    saved_path=directory/'review.private.json'
    saved=a.q.r.read(saved_path) if saved_path.exists() else None
    if saved is not None and (saved.get('name'),saved.get('caseId'),saved.get('pass'))!=(entry['name'],entry['caseId'],entry['pass']):
        raise RuntimeError('Annotation identity differs')
    status=saved['status'] if saved else 'uncertain'
    common={'name':entry['name'],'status':status,'rawVerified':False,'fileHashes':files,'requestCount':len(requests),
        'inputTokens':(usage or {}).get('input_tokens'),'outputTokens':(usage or {}).get('output_tokens'),
        'usage':usage,'seconds':transport.get('seconds')}
    if status not in ['completed','invalid_annotation']:
        if status not in ['failed','uncertain']:raise RuntimeError('Unknown annotation disposition')
        common['qualification']='All available failed/unknown artifacts retained; cannot supply an accepted annotation. Missing usage/duration is unknown.'
        return common
    actual,effective=a.q.verify_teacher(directory)
    if actual!=job or effective['selectedAttempt']!=0 or len(effective['attempts'])!=1:
        raise RuntimeError('Original input/one-attempt teacher lineage differs')
    if len(requests)!=1 or requests[0]['status']!=200 or len(events)!=1 or events[0]['type']!='response.completed':
        raise RuntimeError('Expected unique successful raw request/event')
    response=events[0]['response']
    if response.get('model')!='gpt-6-astra' or response.get('status')!='completed':
        raise RuntimeError('Expected completed pinned model response')
    items=response.get('output') or transport.get('outputItems',[])
    text=''.join(c.get('text','') for i in items if i.get('type')=='message' for c in i.get('content',[]) if c.get('type')=='output_text')
    if not text:raise RuntimeError('Missing service-bound output text')
    raw=json.loads(text)
    if raw!=effective['output'] or raw!=saved['output']:
        raise RuntimeError('Annotation differs from raw response')
    errors=a.original.validate_output(raw,job)
    if errors!=saved['validationErrors'] or status!=('invalid_annotation' if errors else 'completed'):
        raise RuntimeError('Validation differs')
    common.update(rawVerified=True,validationErrors=errors)
    return common


def paired_gate(rows,entries):
    names=[x['name'] for x in rows];expected=[x['name'] for x in entries]
    if len(names)!=202 or len(set(names))!=202 or set(names)!=set(expected):
        raise RuntimeError('All202 unique planned dispositions required')
    by_name={x['name']:x for x in rows};case_ids={x['caseId'] for x in entries}
    if len(case_ids)!=101:raise RuntimeError('Exact101 paired identities required')
    return {cid:all(by_name[p+'/'+cid]['status']=='completed' and by_name[p+'/'+cid]['rawVerified'] for p in a.original.PASSES) for cid in sorted(case_ids)}


def audit(partial=False):
    plan=a.verify_plan();finished=a.ROOT/'run-finished.json'
    if not partial:
        if not finished.exists():raise RuntimeError('Full accounting requires finished runner')
        ensure_dead(a.q.r.read(a.ROOT/'run-started.json')['pid'])
    expected={e['name'] for e in plan['entries']}
    actual={str(p.parent.relative_to(a.ROOT/'responses')) for p in (a.ROOT/'responses').rglob('attempt-started.json')}
    if not actual<=expected:raise RuntimeError('Unexpected attempted pair/pass')
    # Stray files without our exclusive marker cannot disappear from accounting.
    for p in (a.ROOT/'responses').rglob('*'):
        if p.is_file():
            relative=p.relative_to(a.ROOT/'responses')
            if len(relative.parts)<3 or '/'.join(relative.parts[:2]) not in actual:
                raise RuntimeError('Unowned response artifact')
    rows=[reconcile(e) for e in plan['entries']];eligible=paired_gate(rows,plan['entries'])
    attempted=[r for r in rows if r['status']!='unattempted']
    report={'at':a.q.r.now(),'planSha256':a.q.r.digest(a.ROOT/'plan.private.json'),
        'auditorSha256':a.q.r.digest(Path(__file__)),'partial':partial or not finished.exists(),
        'planned':202,'accountedFor':len(rows),'attemptedRows':len(attempted),'rawVerified':sum(r['rawVerified'] for r in rows),
        'statuses':dict(collections.Counter(r['status'] for r in rows)),
        'inputTokens':known([r['inputTokens'] for r in attempted]),'outputTokens':known([r['outputTokens'] for r in attempted]),
        'requestSeconds':known([r['seconds'] for r in attempted]),'rows':rows,
        'pairsEligibleForAdjudication':eligible,'eligiblePairCount':sum(eligible.values()),
        'adjudicatedLabels':False,'modelComparisonsRead':False,
        'qualification':'Exact planned coverage and raw integrity, not correctness gold. Only pairs with two raw-verified completed annotations may receive an adjudicated label; all others remain unresolved. Root semantic adjudication and a new label seal are still required.'}
    if partial:a.q.r.save(a.ROOT/'raw-audit-progress.private.json',report)
    else:a.once(a.ROOT/'raw-audit.private.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['rows','pairsEligibleForAdjudication']},indent=2))
    return report


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true')
    audit(parser.parse_args().partial)
