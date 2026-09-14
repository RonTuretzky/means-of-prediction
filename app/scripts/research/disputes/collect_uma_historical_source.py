#!/usr/bin/env python3
"""Bounded write-once disputed-request collector for official UMA Polygon sources."""
from __future__ import annotations
import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from Crypto.Hash import keccak

BASE=Path.home()/'.local/share/means-of-prediction'
ADAPTERS={
 '0xcb1822859cef82cd2eb4e6276c7916e692995130':'UmaCtfAdapterOld','0x6a9d222616c90fca5754cd1333cfd9b7fb6a4f74':'UmaCtfAdapterV2','0x157ce2d672854c848c9b79c49a8cc6cc89176a49':'UmaCtfAdapterV3','0x65070be91477460d8a7aeeb94ef92fe056c2f2a7':'UmaCtfAdapterV4','0x2f5e3684cb1f318ec51b00edba38d79ac2c0aa9d':'NegRiskUmaCtfAdapter','0x69c47de9d4d3dad79590d61b9e05918e03775f24':'NegRiskUmaCtfAdapterV4'}
SOURCES={
 'polygon-oov1':{'output':BASE/'disputed-markets-20260914-polygon-oov1-v2','endpoint':'https://api.studio.thegraph.com/query/1057/polygon-optimistic-oracle/1.2.0','oracle':'0xbb1a8db2d4350976a11cdfa60a1d43f97710da49','manifest':'https://raw.githubusercontent.com/UMAprotocol/subgraphs/master/packages/optimistic-oracle/manifest/data/polygon.json','schema':'https://raw.githubusercontent.com/UMAprotocol/subgraphs/master/packages/optimistic-oracle/schema.graphql'},
 'polygon-managed-oov2':{'output':BASE/'disputed-markets-20260914-polygon-managed-oov2-v2','endpoint':'https://api.studio.thegraph.com/query/1057/polygon-managed-optimistic-oracle-v2/1.2.0','oracle':'0x2c0367a9db231ddeb d88a94b4f6461a6e47c58b1'.replace(' ',''),'manifest':'https://raw.githubusercontent.com/UMAprotocol/subgraphs/master/packages/managed-oracle-v2/manifest/data/polygon.json','schema':'https://raw.githubusercontent.com/UMAprotocol/subgraphs/master/packages/managed-oracle-v2/schema.graphql'}}
PAGE=1000; MAX=100
META='query { _meta { block { number hash } deployment hasIndexingErrors } }'
QUERY='''query($first:Int!,$after:String!,$block:Int!){ optimisticPriceRequests(first:$first,where:{id_gt:$after,disputeTimestamp_not:null},orderBy:id,orderDirection:asc,block:{number:$block}) { id requester identifier ancillaryData time state disputeTimestamp disputeBlockNumber disputeHash disputeLogIndex settlementTimestamp settlementBlockNumber settlementHash settlementPrice } }'''
def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def sha(b:bytes): return hashlib.sha256(b).hexdigest()
def dump(v:Any): return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def write(p:Path,b:bytes):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def post(endpoint:str,payload:dict):
 req=Request(endpoint,data=json.dumps(payload,separators=(',',':')).encode(),method='POST',headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'means-of-prediction-uma-history/1.0'})
 try:
  with build_opener().open(req,timeout=45) as r:return r.status,r.read(),None
 except HTTPError as e:return e.code,e.read(),f'HTTP {e.code}'
 except (URLError,TimeoutError,ValueError) as e:return None,None,str(e)
def parse(raw):
 try:v=json.loads(raw)
 except Exception as e:return None,f'invalid JSON: {e}'
 if not isinstance(v,dict) or v.get('errors'):return None,f"GraphQL errors: {v.get('errors')}"
 return v.get('data'),None
def key(data):
 if not isinstance(data,str):return None
 try:b=bytes.fromhex(data[2:] if data.startswith('0x') else data)
 except ValueError:return None
 k=keccak.new(digest_bits=256);k.update(b);return '0x'+k.hexdigest()
def norm(row, source, block):
 requester=row.get('requester'); name=ADAPTERS.get((requester or '').lower()); q=key(row.get('ancillaryData')) if name else None
 return {'chainId':137,'oracleAddress':source['oracle'],'transactionHash':row.get('disputeHash'),'logIndex':row.get('disputeLogIndex'),'requester':requester,'identifier':row.get('identifier'),'timestamp':row.get('time'),'ancillaryData':row.get('ancillaryData'),'questionId':q,'conditionId':None,'marketId':None,'sourceRefs':[{'kind':'uma_polygon_subgraph','endpoint':source['endpoint'],'requestId':row.get('id')},{'kind':'uma_deployment_manifest','url':source['manifest'],'oracleAddress':source['oracle']}], 'lifecycle':{'eventName':'DisputePrice','blockNumber':row.get('disputeBlockNumber'),'blockHash':None,'blockHashBasis':'source response did not select per-event block hash','indexedBlockHash':block.get('hash'),'indexedBlockNumber':block.get('number'),'removed':None,'finality':'subgraph indexed block snapshot','requestId':row.get('id'),'stateAtIndexedBlock':row.get('state'),'settlementTimestamp':row.get('settlementTimestamp'),'settlementBlockNumber':row.get('settlementBlockNumber'),'settlementHash':row.get('settlementHash'),'settlementPrice':row.get('settlementPrice'),'ancillaryDataKeccak256':key(row.get('ancillaryData')),'mappingStatus':'allowlisted_polymarket_resolution_question_key' if q else 'unmapped_requester_or_missing_ancillary_key','adapter':name}}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('source',choices=sorted(SOURCES));a=ap.parse_args();s=SOURCES[a.source];out=s['output']
 if out.exists():raise SystemExit(f'refusing to overwrite: {out}')
 os.umask(0o077);out.mkdir(mode=0o700);os.chmod(out,0o700);rawdir=out/'raw';rawdir.mkdir(mode=0o700)
 code=Path(__file__).read_bytes();source_record={key:(str(value) if isinstance(value,Path) else value) for key,value in s.items()};plan={'schemaVersion':'uma-polygon-historical-dispute-collection-v1','createdAt':now(),'sourceName':a.source,'source':source_record,'code':{'path':str(Path(__file__)),'sha256':sha(code)},'adapterAllowlist':ADAPTERS,'requestPolicy':{'attemptsPerCall':1,'retries':0,'pageSize':PAGE,'maximumPages':MAX,'pagination':'id_gt ascending at pinned indexed block','stopOnError':True},'queries':{'meta':META,'requests':QUERY},'coverage':'one official UMA subgraph source; all returned UMA disputes, not all Polymarket markets'};write(out/'collection-plan.json',dump(plan));write(out/'collect_uma_historical_source.py',code)
 status,raw,error=post(s['endpoint'],{'query':META});probe={'startedAt':now(),'httpStatus':status,'error':error,'endpoint':s['endpoint']}
 if raw is not None:write(rawdir/'000-meta.json',raw);probe.update({'rawFile':'raw/000-meta.json','rawSha256':sha(raw),'rawBytes':len(raw)})
 data,err=parse(raw) if raw is not None else (None,error);meta=data.get('_meta') if data else None
 if status!=200 or err or not isinstance(meta,dict) or not isinstance(meta.get('block',{}).get('number'),int):probe['result']='failed';write(out/'probe.json',dump(probe));write(out/'manifest.json',dump({'complete':False,'probe':probe,'reason':err or error or 'invalid meta'}));print(json.dumps({'complete':False,'source':a.source,'error':err or error},sort_keys=True));return 1
 block=meta['block'];probe.update({'result':'indexed_block_frozen','indexedBlock':block,'deployment':meta.get('deployment'),'hasIndexingErrors':meta.get('hasIndexingErrors')});write(out/'probe.json',dump(probe))
 events=[];pages=[];after='';complete=True
 for n in range(1,MAX+1):
  status,raw,error=post(s['endpoint'],{'query':QUERY,'variables':{'first':PAGE,'after':after,'block':block['number']}});entry={'page':n,'after':after,'startedAt':now(),'httpStatus':status,'error':error}
  if raw is not None:
   f=f'{n:03d}-requests.json';write(rawdir/f,raw);entry.update({'rawFile':'raw/'+f,'rawSha256':sha(raw),'rawBytes':len(raw)})
  data,err=parse(raw) if raw is not None else (None,error);batch=data.get('optimisticPriceRequests') if data else None
  if status!=200 or err or not isinstance(batch,list) or batch!=sorted(batch,key=lambda x:x.get('id','')):entry['parseError']=err or 'missing/unordered optimisticPriceRequests';pages.append(entry);complete=False;break
  events.extend(norm(x,s,block) for x in batch);entry['returned']=len(batch);pages.append(entry)
  if len(batch)<PAGE:break
  nxt=batch[-1].get('id') if batch else None
  if not isinstance(nxt,str) or nxt<=after:entry['parseError']='non-advancing cursor';complete=False;break
  after=nxt
 else:complete=False;pages.append({'stopReason':'maximum page cap reached'})
 output={'schema_version':'uma-polygon-historical-dispute-collection-v1','sourceName':a.source,'indexedBlock':block,'events':events};b=dump(output);write(out/'normalized-dispute-events.json',b)
 mapped=sum(x['questionId'] is not None for x in events);m={'complete':complete,'completedAt':now(),'sourceName':a.source,'indexedBlock':block,'probe':probe,'pages':pages,'counts':{'disputeRequests':len(events),'allowlistedQuestionKeyRequests':mapped,'unmappedRequester':len(events)-mapped},'output':{'path':'normalized-dispute-events.json','sha256':sha(b),'bytes':len(b)},'limitations':['questionId is a resolution-subgraph key only; marketId and conditionId are null.','No hosted Polymarket resolution-subgraph entity join was made.','This source is not a claim of all Polymarket markets.']};write(out/'manifest.json',dump(m));print(json.dumps({'source':a.source,'complete':complete,**m['counts']},sort_keys=True));return 0 if complete else 1
if __name__=='__main__':raise SystemExit(main())
