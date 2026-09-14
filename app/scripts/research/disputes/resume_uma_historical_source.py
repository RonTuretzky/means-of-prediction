#!/usr/bin/env python3
"""Resume an interrupted bounded historical source without refetching raw pages."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from collections import Counter
import collect_uma_historical_source as c

def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in c.SOURCES: raise SystemExit('usage: resume_uma_historical_source.py SOURCE')
    name=sys.argv[1]; source=c.SOURCES[name]; out=source['output']
    if (out/'manifest.json').exists() or (out/'normalized-dispute-events.json').exists(): raise SystemExit('capture is already final')
    plan=json.loads((out/'collection-plan.json').read_bytes()); probe=json.loads((out/'probe.json').read_bytes()); block=probe.get('indexedBlock')
    if not isinstance(block,dict) or not isinstance(block.get('number'),int): raise SystemExit('missing frozen indexed block')
    os.umask(0o077); c.write(out/'resume_uma_historical_source.py',Path(__file__).read_bytes())
    pages=[]; events=[]; after=''
    for n,path in enumerate(sorted((out/'raw').glob('[0-9][0-9][0-9]-requests.json')),1):
        raw=path.read_bytes(); data,err=c.parse(raw); batch=data.get('optimisticPriceRequests') if data else None
        if err or not isinstance(batch,list) or not batch or batch!=sorted(batch,key=lambda x:x.get('id','')):raise SystemExit(f'invalid archived page {path}: {err}')
        events.extend(c.norm(x,source,block) for x in batch); after=batch[-1]['id']; pages.append({'page':n,'after':'archived' if n>1 else '','httpStatus':200,'rawFile':'raw/'+path.name,'rawSha256':c.sha(raw),'rawBytes':len(raw),'returned':len(batch),'resumeSource':'archived response'})
        if len(batch)<c.PAGE: break
    complete=True
    if pages[-1]['returned']==c.PAGE:
      for n in range(len(pages)+1,c.MAX+1):
        status,raw,error=c.post(source['endpoint'],{'query':c.QUERY,'variables':{'first':c.PAGE,'after':after,'block':block['number']}}); e={'page':n,'after':after,'startedAt':c.now(),'httpStatus':status,'error':error}
        if raw is not None:
            filename=f'{n:03d}-requests.json';c.write(out/'raw'/filename,raw);e.update({'rawFile':'raw/'+filename,'rawSha256':c.sha(raw),'rawBytes':len(raw)})
        data,err=c.parse(raw) if raw is not None else (None,error);batch=data.get('optimisticPriceRequests') if data else None
        if status!=200 or err or not isinstance(batch,list) or batch!=sorted(batch,key=lambda x:x.get('id','')):e['parseError']=err or 'missing/unordered optimisticPriceRequests';pages.append(e);complete=False;break
        events.extend(c.norm(x,source,block) for x in batch);e['returned']=len(batch);pages.append(e)
        if len(batch)<c.PAGE:break
        nxt=batch[-1].get('id') if batch else None
        if not isinstance(nxt,str) or nxt<=after:e['parseError']='non-advancing cursor';complete=False;break
        after=nxt
      else:complete=False;pages.append({'stopReason':'maximum page cap reached'})
    payload={'schema_version':'uma-polygon-historical-dispute-collection-v1','sourceName':name,'indexedBlock':block,'events':events}; raw=c.dump(payload);c.write(out/'normalized-dispute-events.json',raw)
    mapped=sum(x['questionId'] is not None for x in events)
    manifest={'complete':complete,'completedAt':c.now(),'sourceName':name,'indexedBlock':block,'probe':probe,'pages':pages,'counts':{'disputeRequests':len(events),'allowlistedQuestionKeyRequests':mapped,'unmappedRequester':len(events)-mapped},'output':{'path':'normalized-dispute-events.json','sha256':c.sha(raw),'bytes':len(raw)},'resume':{'sourcePlanSha256':c.sha((out/'collection-plan.json').read_bytes()),'archivedPagesReused':len([x for x in pages if x.get('resumeSource')])},'limitations':['questionId is a resolution-subgraph key only; marketId and conditionId are null.','No hosted Polymarket resolution-subgraph entity join was made.','This source is not a claim of all Polymarket markets.']};c.write(out/'manifest.json',c.dump(manifest));print(json.dumps({'source':name,'complete':complete,**manifest['counts']},sort_keys=True));return 0 if complete else 1
if __name__=='__main__':raise SystemExit(main())
