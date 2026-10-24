#!/usr/bin/env node
// Isolated historical Anvil profiling. Reuses genuine, previously recorded
// calldata; never signs a certificate, forks a network, or reads a private key.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { LocalRPC, loadFrozenPacket, sendRecordedTx, captureState, saveNew,
  sha, SETUP, FINAL_TIMESTAMP } from './peace_anvil_baseline.mjs';
import { SOURCE_GAS_TRACER } from './peace_source_gas_tracer.mjs';

const BASE='/Users/wk/.local/share/means-of-prediction';
const OLD=path.join(BASE,'peace-anvil-comparison-20261021');
const ROOT=path.join(BASE,'peace-gas-profile-20261021');
const OUT=path.join(ROOT,'profile-v2');
const GATE='0xA646Dc91Bff4e1f060100258071FF9b38fF74C94';
const ANCHOR='0xe02bc89880aa8b1ae6b1be33b4b34d3b63496d70078a58d7c6d38f1e637ebea4';
const ROUTES=[['uncached-direct',125369240],['cached-direct',123935796],['gaskiller-certified',124075906]];
const invariant=(v,m)=>{if(!v) throw new Error(m);};
class ProfileRPC extends LocalRPC {
  async trace(hash, tracer) {
    const body=JSON.stringify({jsonrpc:'2.0',id:++this.counter,method:'debug_traceTransaction',
      params:[hash,{tracer,timeout:'600s'}]});
    const data=await new Promise((resolve,reject)=>{
      const request=http.request(this.url,{method:'POST',headers:{'content-type':'application/json',
        'content-length':Buffer.byteLength(body)}},response=>{
        if(response.statusCode!==200){response.resume();reject(new Error('Trace HTTP failure'));return;}
        const chunks=[];let size=0;
        response.on('data',chunk=>{size+=chunk.length;if(size>64*1024*1024)request.destroy(new Error('Trace response bound'));else chunks.push(chunk);});
        response.on('error',reject);
        response.on('end',()=>{try{resolve(JSON.parse(Buffer.concat(chunks).toString()));}catch(e){reject(e);}});
      });
      const deadline=setTimeout(()=>request.destroy(new Error('Trace wall-clock deadline')),660000);
      request.on('close',()=>clearTimeout(deadline));request.on('error',reject);request.end(body);
    });
    if(data.error) throw new Error(JSON.stringify(data.error));
    return data.result;
  }
}
const rpc=new ProfileRPC('http://127.0.0.1:19545');
fs.mkdirSync(OUT,{mode:0o700});
const pins=JSON.parse(fs.readFileSync(path.join(ROOT,'protected-baseline-pins.private.json')));
for(const p of pins.protectedArtifacts) invariant(sha(fs.readFileSync(p.path))===p.sha256,`Protected artifact changed: ${p.path}`);
const anchor=await rpc.call('eth_getBlockByNumber',['latest',false]);
const info=await rpc.call('anvil_nodeInfo');
invariant(anchor.hash===ANCHOR && BigInt(anchor.number)===129n,'Expected unchanged historical anchor');
invariant(info.environment.chainId===31337 && info.hardFork==='Cancun' && info.forkConfig.forkUrl===null,'Expected isolated local Cancun');
invariant(BigInt(await rpc.call('eth_getTransactionCount',[SETUP,'latest']))===27n,'Unexpected setup nonce');
const packet=loadFrozenPacket();
const before=await captureState(rpc,packet,GATE);
invariant(before.decision===0 && before.consumedRequests.every(x=>!x) && before.consumedEmails.every(x=>!x),'Anchor already consumed');
saveNew(OUT,'profiling-plan.private.json',{schema:'peace-original-settlement-profiling-v1',anchor,info,before,
  runnerSHA256:sha(fs.readFileSync(fileURLToPath(import.meta.url))),
  tracerSHA256:sha(SOURCE_GAS_TRACER),routes:ROUTES,finalTimestamp:FINAL_TIMESTAMP,
  method:'Replay exact frozen calldata at the same historical anchor/time. Two independent traces per actual receipt. All source contracts and prior artifacts unchanged.'});
let snapshot=await rpc.call('evm_snapshot');
let previousState;
const results=[];
for(let i=0;i<ROUTES.length;i++){
  const [route,expectedGas]=ROUTES[i];
  const oldTx=JSON.parse(fs.readFileSync(path.join(OLD,`matched-${route}-transaction.private.json`)));
  const oldReceipt=JSON.parse(fs.readFileSync(path.join(OLD,`matched-${route}-receipt.private.json`))).receipt;
  invariant(oldTx.from.toLowerCase()===SETUP.toLowerCase() && oldTx.timestamp===FINAL_TIMESTAMP,'Frozen transaction context changed');
  console.log(JSON.stringify({route,phase:'replay'}));
  const receipt=await sendRecordedTx(rpc,OUT,`profile-${route}`,{from:oldTx.from,to:oldTx.to,data:oldTx.data},FINAL_TIMESTAMP);
  invariant(Number(receipt.gasUsed)===expectedGas,'Replayed gas differs from original');
  invariant(receipt.hash===oldReceipt.transactionHash,'Replayed transaction hash differs');
  const after=await captureState(rpc,packet,GATE);
  invariant(after.decision===1 && after.supportingSourceMask===15 && after.consumedSourceMask===15
    && after.consumedRequests.every(Boolean) && after.consumedEmails.every(Boolean),'Settlement invariants failed');
  if(previousState) invariant(JSON.stringify(after,(_,v)=>typeof v==='bigint'?v.toString():v)===previousState,'Original consumer/gate outcomes differ');
  previousState=JSON.stringify(after,(_,v)=>typeof v==='bigint'?v.toString():v);
  saveNew(OUT,`profile-${route}-state.private.json`,after);
  console.log(JSON.stringify({route,phase:'call-trace',gasUsed:Number(receipt.gasUsed)}));
  const callTrace=await rpc.trace(receipt.hash,'callTracer');
  invariant(Number(BigInt(callTrace.gasUsed))===expectedGas,'Call tracer receipt mismatch');
  saveNew(OUT,`profile-${route}-calls.private.json`,callTrace);
  console.log(JSON.stringify({route,phase:'compact-opcode-trace'}));
  const started=Date.now();
  const trace=await rpc.trace(receipt.hash,SOURCE_GAS_TRACER);
  invariant(trace.gasUsed===expectedGas && trace.errors.length===0,'Opcode tracer receipt mismatch or errors');
  saveNew(OUT,`profile-${route}-opcodes.private.json`,trace);
  const result={route,transactionHash:receipt.hash,gasUsed:expectedGas,opcodeGas:trace.opcodeGas,
    opaqueCallGas:trace.opaqueCallGas,intrinsicGas:trace.intrinsicGas,steps:trace.steps,frames:trace.frames.length,
    pcRows:trace.rows.length,traceMilliseconds:Date.now()-started};
  results.push(result);
  console.log(JSON.stringify({...result,phase:'complete'}));
  if(i<ROUTES.length-1){
    invariant(await rpc.call('evm_revert',[snapshot]),'Snapshot revert failed');
    invariant((await rpc.call('eth_getBlockByNumber',['latest',false])).hash===ANCHOR,'Anchor changed after revert');
    snapshot=await rpc.call('evm_snapshot');
  }
}
for(const p of pins.protectedArtifacts) invariant(sha(fs.readFileSync(p.path))===p.sha256,`Protected artifact changed: ${p.path}`);
saveNew(OUT,'profiling-results.private.json',{schema:'peace-original-settlement-profiling-results-v1',results,
  protectedArtifactsUnchanged:pins.protectedArtifacts.length,originalConsumerGateStateIdentical:true});
console.log(JSON.stringify({complete:true,output:OUT}));
