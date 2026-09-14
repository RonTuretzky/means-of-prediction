#!/usr/bin/env python3
"""Build a private, write-once union of completed UMA dispute exports."""
from __future__ import annotations
import hashlib,json,os
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen

BASE=Path.home()/'.local/share/means-of-prediction'
OUTPUT=BASE/'disputed-markets-20260914-union-v3'
SOURCES=[
 {'name':'polygon-oov2','events':BASE/'disputed-markets-20260914-polymarket-question-keys-v1'/'normalized-dispute-events.json','manifest':BASE/'disputed-markets-20260914-polymarket-question-keys-v1'/'manifest.json','raw':BASE/'disputed-markets-20260914'/'raw','coverageManifest':BASE/'disputed-markets-20260914'/'manifest.json'},
 {'name':'polygon-oov1','events':BASE/'disputed-markets-20260914-polygon-oov1-v2'/'normalized-dispute-events.json','manifest':BASE/'disputed-markets-20260914-polygon-oov1-v2'/'manifest.json','raw':BASE/'disputed-markets-20260914-polygon-oov1-v2'/'raw','coverageManifest':BASE/'disputed-markets-20260914-polygon-oov1-v2'/'manifest.json'},
 {'name':'polygon-managed-oov2','events':BASE/'disputed-markets-20260914-polygon-managed-oov2-v2'/'normalized-dispute-events.json','manifest':BASE/'disputed-markets-20260914-polygon-managed-oov2-v2'/'manifest.json','raw':BASE/'disputed-markets-20260914-polygon-managed-oov2-v2'/'raw','coverageManifest':BASE/'disputed-markets-20260914-polygon-managed-oov2-v2'/'manifest.json'}]
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def write(p,b):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def raw_lookup(path):
 result={}
 for page in sorted(path.glob('[0-9][0-9][0-9]-requests.json')):
  raw=page.read_bytes(); data=json.loads(raw); rows=data.get('data',{}).get('optimisticPriceRequests',[])
  for row in rows:
   if isinstance(row,dict) and isinstance(row.get('id'),str):result[row['id']]={'page':page.name,'sha256':sha(raw),'row':row}
 return result
def event_key(event):
 values=[event.get('chainId'),event.get('oracleAddress'),event.get('transactionHash'),event.get('logIndex')]
 if any(v is None for v in values):raise ValueError(f'missing event key part: {values}')
 return ':'.join(str(v).lower() for v in values)
def main():
 if OUTPUT.exists():raise SystemExit(f'refusing to overwrite: {OUTPUT}')
 os.umask(0o077);OUTPUT.mkdir(mode=0o700);os.chmod(OUTPUT,0o700);code=Path(__file__).read_bytes()
 source_hashes=[]
 for source in SOURCES:
  for label,path in [('events',source['events']),('manifest',source['manifest']),('coverageManifest',source['coverageManifest'])]:source_hashes.append({'source':source['name'],'kind':label,'path':str(path),'sha256':sha(path.read_bytes())})
 plan={'schemaVersion':'uma-dispute-union-v3','createdAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'code':{'path':str(Path(__file__)),'sha256':sha(code)},'inputs':source_hashes,'dedupeKey':'lowercase chainId:oracleAddress:transactionHash:logIndex','rawReferences':'Each union event points to its source capture raw page; raw data is retained only in the source private capture.'}
 write(OUTPUT/'union-plan.json',dump(plan));write(OUTPUT/'build_union_index.py',code)
 snapshot_urls={'subgraph.yaml':'https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/subgraph.yaml','constants.ts':'https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/src/utils/constants.ts','optimistic-oracle-v-2.ts':'https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/src/optimistic-oracle-v-2.ts','managed-oo-v2.ts':'https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/src/managed-oo-v2.ts','optimistic-oracle-old.ts':'https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/src/optimistic-oracle-old.ts'}
 snapshot_dir=OUTPUT/'source-snapshots';snapshot_dir.mkdir(mode=0o700);snapshots={}
 for name,url in snapshot_urls.items():
  raw=urlopen(url,timeout=30).read();write(snapshot_dir/name,raw);snapshots[name]={'url':url,'path':'source-snapshots/'+name,'sha256':sha(raw),'bytes':len(raw)}
 records={}; duplicate_keys=[]; coverage=[]; source_counts=Counter()
 for source in SOURCES:
  payload=json.loads(source['events'].read_bytes()); manifest=json.loads(source['coverageManifest'].read_bytes()); lookup=raw_lookup(source['raw']); events=payload.get('events')
  if not isinstance(events,list):raise SystemExit(f'{source["name"]} has no events list')
  missing_refs=0
  for original in events:
   event=dict(original); lifecycle=dict(event.get('lifecycle') or {}); request_id=lifecycle.get('requestId'); raw_ref=lookup.get(request_id)
   if raw_ref is None:missing_refs+=1; raise SystemExit(f'missing raw request reference: {source["name"]}:{request_id}')
   raw_row=raw_ref['row']
   for event_field,raw_field in [('transactionHash','disputeHash'),('logIndex','disputeLogIndex'),('ancillaryData','ancillaryData')]:
    if event.get(event_field)!=raw_row.get(raw_field):raise SystemExit(f'normalized/raw conflict: {source["name"]}:{request_id}:{event_field}')
   lifecycle['disputeTimestamp']=raw_row.get('disputeTimestamp')
   if source['name']=='polygon-oov2':valid={'0x6a9d222616c90fca5754cd1333cfd9b7fb6a4f74','0x157ce2d672854c848c9b79c49a8cc6cc89176a49','0x2f5e3684cb1f318ec51b00edba38d79ac2c0aa9d'};handler='optimistic-oracle-v-2.ts'
   elif source['name']=='polygon-managed-oov2':valid={'0x65070be91477460d8a7aeeb94ef92fe056c2f2a7','0x69c47de9d4d3dad79590d61b9e05918e03775f24'};handler='managed-oo-v2.ts'
   else:valid=set();handler='optimistic-oracle-old.ts'
   if (event.get('requester') or '').lower() not in valid:event['questionId']=None;lifecycle['mappingStatus']='pending_ancillary_hash_to_question_id_join' if source['name']=='polygon-oov1' else 'unmapped_requester'
   elif not isinstance(event.get('questionId'),str):raise SystemExit(f'missing question key: {source["name"]}:{request_id}')
   else:lifecycle['questionIdBasis']=f'keccak256 ancillaryData after source-specific requester check; pinned {handler} SHA-256 {snapshots[handler]["sha256"]}'
   event['sourceRefs']=list(event.get('sourceRefs') or [])+[{'kind':'archived_raw_request_page','capture':source['name'],'directory':str(source['raw'].parent),'path':'raw/'+raw_ref['page'],'rawSourceSha256':raw_ref['sha256'],'requestId':request_id},{'kind':'polymarket_resolution_subgraph_snapshot','snapshot':snapshots[handler]}]
   event['lifecycle']=lifecycle; key=event_key(event); event['eventKey']=key
   if key in records:
    if records[key]!=event:raise SystemExit(f'duplicate event-key conflict: {key}')
    duplicate_keys.append(key)
   else:records[key]=event
  source_counts[source['name']]=len(events)
  probe=manifest.get('probe',{})
  coverage.append({'source':source['name'],'inputEvents':len(events),'complete':manifest.get('complete'),'indexedBlock':manifest.get('indexedBlock') or payload.get('indexedBlock'),'deployment':probe.get('deployment','not_queried_at_frozen_capture'),'hasIndexingErrors':probe.get('hasIndexingErrors','not_queried_at_frozen_capture'),'rawReferenceMissing':missing_refs,'sourceManifestSha256':sha(source['coverageManifest'].read_bytes())})
 ordered=[records[k] for k in sorted(records)]
 mapped=[x for x in ordered if x.get('questionId') is not None]
 unmapped=[x for x in ordered if x.get('questionId') is None]
 jsonl=lambda items: b''.join((json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n').encode() for x in items)
 records_bytes=jsonl(ordered); mapped_bytes=jsonl(mapped); unmapped_bytes=jsonl(unmapped)
 write(OUTPUT/'normalized-dispute-events.jsonl',records_bytes);write(OUTPUT/'known-adapter-question-keys.jsonl',mapped_bytes);write(OUTPUT/'unmapped-requests.jsonl',unmapped_bytes)
 timestamps=[int(x['lifecycle']['disputeTimestamp']) for x in ordered if isinstance(x.get('lifecycle',{}).get('disputeTimestamp'),str) and x['lifecycle']['disputeTimestamp'].isdigit()]
 questions=Counter(x['questionId'] for x in mapped)
 manifest={'complete':all(x['complete'] is True for x in coverage),'coverage':coverage,'sourceSnapshots':snapshots,'counts':{'sourceInputEvents':dict(source_counts),'rawOccurrences':sum(source_counts.values()),'uniqueEvents':len(ordered),'duplicateEventKeysCollapsed':len(duplicate_keys),'knownAdapterQuestionKeyRequests':len(mapped),'uniqueKnownAdapterQuestionKeys':len(questions),'unmappedRequests':len(unmapped),'questionKeyMultiplicity':dict(sorted(Counter(questions.values()).items())),'earliestDisputeTimestamp':min(timestamps) if timestamps else None,'latestDisputeTimestamp':max(timestamps) if timestamps else None},'outputs':{'allEvents':{'path':'normalized-dispute-events.jsonl','sha256':sha(records_bytes),'bytes':len(records_bytes)},'knownAdapterQuestionKeys':{'path':'known-adapter-question-keys.jsonl','sha256':sha(mapped_bytes),'bytes':len(mapped_bytes)},'unmappedRequests':{'path':'unmapped-requests.jsonl','sha256':sha(unmapped_bytes),'bytes':len(unmapped_bytes)}},'limitations':['A known-adapter question key is not a Gamma market ID and is not proof of a platform-listed market.','No Gamma market or condition join was available; marketId and conditionId remain null.','Each source has its own pinned indexed block, listed in coverage; this is not a common-chain-block snapshot.','The OOv2 metadata audit was after the frozen capture, so its hasIndexingErrors result is a later endpoint-health observation, not proof about the frozen instant.']}
 write(OUTPUT/'manifest.json',dump(manifest));print(json.dumps({'complete':manifest['complete'],**manifest['counts']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
