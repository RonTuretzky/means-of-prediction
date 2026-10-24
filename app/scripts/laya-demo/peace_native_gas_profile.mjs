#!/usr/bin/env node
// Fast native call-frame measurements of all three exact frozen local routes.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { LocalRPC, loadFrozenPacket, sendRecordedTx, captureState, saveNew,
  sha, SETUP, FINAL_TIMESTAMP } from './peace_anvil_baseline.mjs';
const BASE='/Users/wk/.local/share/means-of-prediction';
const OLD=path.join(BASE,'peace-anvil-comparison-20261021');
const ROOT=path.join(BASE,'peace-gas-profile-20261021');
const OUT=path.join(ROOT,'profile-final');
const GATE='0xA646Dc91Bff4e1f060100258071FF9b38fF74C94';
const ANCHOR='0xe02bc89880aa8b1ae6b1be33b4b34d3b63496d70078a58d7c6d38f1e637ebea4';
const ROUTES=[['uncached-direct',125369240],['cached-direct',123935796],['gaskiller-certified',124075906]];
const invariant=(v,m)=>{if(!v)throw new Error(m);};
const rpc=new LocalRPC('http://127.0.0.1:19545');
fs.mkdirSync(OUT,{mode:0o700});
const pins=JSON.parse(fs.readFileSync(path.join(ROOT,'protected-baseline-pins.private.json')));
for(const p of pins.protectedArtifacts)invariant(sha(fs.readFileSync(p.path))===p.sha256,`Protected artifact changed: ${p.path}`);
const anchor=await rpc.call('eth_getBlockByNumber',['latest',false]);
const info=await rpc.call('anvil_nodeInfo');
invariant(anchor.hash===ANCHOR && BigInt(anchor.number)===129n,'Expected unchanged historical anchor');
invariant(info.environment.chainId===31337 && info.hardFork==='Cancun'
  && new URL(info.forkConfig.forkUrl).href==='http://127.0.0.1:19546/'
  && info.forkConfig.forkBlockNumber===129,'Expected isolated local archive fork at original129');
invariant(BigInt(await rpc.call('eth_getTransactionCount',[SETUP,'latest']))===27n,'Unexpected setup nonce');
const packet=loadFrozenPacket();
const before=await captureState(rpc,packet,GATE);
invariant(before.decision===0 && before.consumedRequests.every(x=>!x) && before.consumedEmails.every(x=>!x),'Anchor already consumed');
saveNew(OUT,'profiling-plan.private.json',{schema:'peace-native-settlement-profile-v1',anchor,info,before,
  runnerSHA256:sha(fs.readFileSync(fileURLToPath(import.meta.url))),routes:ROUTES,finalTimestamp:FINAL_TIMESTAMP,
  detailedDirectTrace:path.join(ROOT,'profile-v2/profile-uncached-direct-opcodes.private.json')});
let snapshot=await rpc.call('evm_snapshot');let expectedState;const results=[];
for(let i=0;i<ROUTES.length;i++){
  const [route,expectedGas]=ROUTES[i];
  const savedTx=path.join(OLD,`matched-${route}-transaction.private.json`);
  const oldTx=JSON.parse(fs.readFileSync(savedTx));
  const oldReceipt=JSON.parse(fs.readFileSync(path.join(OLD,`matched-${route}-receipt.private.json`))).receipt;
  invariant(oldTx.from.toLowerCase()===SETUP.toLowerCase() && oldTx.timestamp===FINAL_TIMESTAMP,'Frozen transaction context changed');
  const receipt=await sendRecordedTx(rpc,OUT,`profile-${route}`,{from:oldTx.from,to:oldTx.to,data:oldTx.data},FINAL_TIMESTAMP);
  invariant(Number(receipt.gasUsed)===expectedGas && receipt.hash===oldReceipt.transactionHash,'Replayed receipt mismatch');
  const after=await captureState(rpc,packet,GATE);
  invariant(after.decision===1 && after.supportingSourceMask===15 && after.consumedSourceMask===15
    && after.consumedRequests.every(Boolean) && after.consumedEmails.every(Boolean),'Settlement invariants failed');
  const encoded=JSON.stringify(after,(_,v)=>typeof v==='bigint'?v.toString():v);
  if(expectedState)invariant(encoded===expectedState,'Original consumer/gate outcomes differ');
  expectedState=encoded;
  saveNew(OUT,`profile-${route}-state.private.json`,after);
  const callTrace=await rpc.call('debug_traceTransaction',[receipt.hash,{tracer:'callTracer'}]);
  invariant(Number(BigInt(callTrace.gasUsed))===expectedGas,'Native trace receipt mismatch');
  saveNew(OUT,`profile-${route}-calls.private.json`,callTrace);
  const bytes=Buffer.from(oldTx.data.slice(2),'hex');
  const intrinsicGas=21000+bytes.reduce((s,c)=>s+(c===0?4:16),0);
  const result={route,transactionHash:receipt.hash,gasUsed:expectedGas,intrinsicGas,
    calldataBytes:bytes.length,sourceTransactionSHA256:sha(fs.readFileSync(savedTx))};
  results.push(result);console.log(JSON.stringify(result));
  if(i<ROUTES.length-1){
    invariant(await rpc.call('evm_revert',[snapshot]),'Snapshot revert failed');
    invariant((await rpc.call('eth_getBlockByNumber',['latest',false])).hash===ANCHOR,'Anchor changed after revert');
    snapshot=await rpc.call('evm_snapshot');
  }
}
for(const p of pins.protectedArtifacts)invariant(sha(fs.readFileSync(p.path))===p.sha256,`Protected artifact changed: ${p.path}`);
saveNew(OUT,'profiling-results.private.json',{schema:'peace-native-settlement-profile-results-v1',results,
  protectedArtifactsUnchanged:pins.protectedArtifacts.length,originalConsumerGateStateIdentical:true});
console.log(JSON.stringify({complete:true,output:OUT}));
