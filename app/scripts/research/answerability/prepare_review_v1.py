"""Export complete review material only after the extension's full raw gate.

This creates private reading aids, never labels, judgments or baseline joins.
"""
import json
import os
from pathlib import Path

import combined_v1 as c


def main():
    plan=c.a.verify_plan()
    report=c.a.q.r.read(c.ROOT/'raw-audit.private.json')
    eligible=c.audit_gate(report,plan)
    target=c.ROOT/'review-material'
    if target.exists():
        raise RuntimeError('Review material already exists; do not overwrite')
    target.mkdir(mode=0o700)
    rows=[];emails={}
    for selected in plan['selected']:
        cid=selected['caseId'];job,job_sha=c.job_reader(cid)
        email=job['input']['completeEmail'];eid=selected['emailId']
        if eid in emails and emails[eid]!=email:
            raise RuntimeError('Shared email identifier has different complete content')
        if eid not in emails:
            emails[eid]=email;c.a.once(target/'emails'/(eid+'.json'),email)
        passes={}
        for which in c.a.original.PASSES:
            path=c.ROOT/'responses'/which/cid/'review.private.json'
            passes[which]=c.a.q.r.read(path) if path.exists() else {'status':'unattempted_or_uncertain','output':None}
        rows.append({'caseId':cid,'marketId':selected['marketId'],'emailId':eid,
            'jobSha256':job_sha,'eligibleForAdjudication':eligible[cid],
            'publicMarket':job['input']['publicMarket'],'emailFile':str(target/'emails'/(eid+'.json')),
            'passes':passes})
    c.a.once(target/'worksheet.private.json',rows)
    c.a.once(target/'manifest.private.json',{'at':c.a.q.r.now(),'pairs':len(rows),'completeEmails':len(emails),
        'sourceSha256':c.a.q.r.digest(Path(__file__)),'rawAuditSha256':c.a.q.r.digest(c.ROOT/'raw-audit.private.json'),
        'fileHashes':{str(p.relative_to(target)):c.a.q.r.digest(p) for p in target.rglob('*') if p.is_file()},
        'qualification':'Full semantic emails and complete original terms/dual reviews. No text clipping or link removal. Reading material only; not adjudication or new ground truth. Incomplete dual reviews must remain unresolved.'})
    print(json.dumps({'pairs':len(rows),'completeEmails':len(emails),'eligiblePairs':sum(eligible.values()),'worksheetSha256':c.a.q.r.digest(target/'worksheet.private.json')}))


if __name__=='__main__':
    os.umask(0o077);main()
