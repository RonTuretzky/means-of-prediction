import { keccak256, recoverTransactionAddress, parseTransaction } from 'viem';
import { fail, safeCode } from './errors.mjs';
// One pending nonce globally. Persist intent before signing, and signed bytes
// before broadcast. Every retry/replacement remains in that same nonce family.
export class Relay {
 constructor({store,client,signer,config,now=Date.now}){Object.assign(this,{store,client,signer,config,now});}
 pending(){const row=this.store.get("SELECT id FROM actions WHERE state NOT IN ('confirmed','reverted') ORDER BY nonce LIMIT 1");return row?this.store.action(row.id):null;}
 async perform(id,jobId,request){
  let action=this.store.action(id);
  if(action?.state==='confirmed')return true;
  if(action?.state==='reverted')fail('transaction_reverted',409);
  const other=this.pending();if(other&&other.id!==id){await this.advance(other);return false;}
  if(!action){
   const nonce=await this.client.getTransactionCount({address:this.config.relayAddress,blockTag:'pending'});
   if(this.store.get('SELECT id FROM actions WHERE nonce=?',nonce))fail('relay_nonce_conflict');
   const gasEstimate=await this.client.estimateGas({account:this.config.relayAddress,to:request.to,data:request.data,value:0n,gas:BigInt(this.config.maxGas)});
   const gas=gasEstimate*110n/100n,gasPrice=await this.client.getGasPrice();
   if(gas>BigInt(this.config.maxGas)||gasPrice>BigInt(this.config.maxGasPrice))fail('relay_gas_budget');
   if(await this.client.getBalance({address:this.config.relayAddress})<gas*gasPrice)fail('relay_needs_gas');
   const intent={...request,chainId:this.config.chainId,nonce,value:'0',gas:String(gas),gasPrice:String(gasPrice)};
   this.store.saveAction(id,jobId,'prepared',nonce,{request:intent,versions:[]});action=this.store.action(id);
  }
  return this.advance(action);
 }
 async advance(action){
  let p=action.payload;
  for(const version of p.versions){
   let receipt;try{receipt=await this.client.getTransactionReceipt({hash:version.hash});}catch(e){if(e.name!=='TransactionReceiptNotFoundError')throw e;}
   if(!receipt)continue;
   this.store.health('relay',true);
   const tip=await this.client.getBlockNumber();if(tip<receipt.blockNumber+BigInt(this.config.confirmations))return false;
   const canonical=await this.client.getBlock({blockNumber:receipt.blockNumber});if(canonical.hash!==receipt.blockHash)return false;
   const state=receipt.status==='success'?'confirmed':'reverted';
   p={...p,receipt:{hash:version.hash,block:Number(receipt.blockNumber),blockHash:receipt.blockHash,gasUsed:String(receipt.gasUsed)}};
   this.store.saveAction(action.id,action.job_id,state,action.nonce,p);
   if(state==='confirmed'&&action.id.startsWith('proof:'))this.store.jobState(action.job_id,'confirmed');
   this.store.health('relay',true);if(state==='reverted')fail('transaction_reverted',409);return true;
  }
  if(await this.client.getTransactionCount({address:this.config.relayAddress,blockTag:'latest'})>action.nonce)fail('relay_nonce_consumed_unknown',409);
  const last=p.versions.at(-1);
  // An accepted pending transaction is normal. Avoid repeated "already known"
  // responses on every five-second tick; rebroadcast if it remains absent.
  if(last&&action.state==='submitted'&&p.lastBroadcastAt!==undefined&&this.now()-p.lastBroadcastAt<30000){this.store.health('relay',true);return false;}
  if(!last||this.now()-last.signedAt>120000){
   if(last&&action.state!=='prepared'){const current=await this.client.getGasPrice(),bump=BigInt(p.request.gasPrice)*9n/8n+1n;const price=current>bump?current:bump;
    if(price>BigInt(this.config.maxGasPrice))fail('relay_replacement_budget');
    p={...p,request:{...p.request,gasPrice:String(price)}};
    // The replacement intent also survives an uncertain signer response.
    this.store.saveAction(action.id,action.job_id,'prepared',action.nonce,p);
   }
   const signed=await this.signer.sign(p.request),tx=parseTransaction(signed);
   if((await recoverTransactionAddress({serializedTransaction:signed})).toLowerCase()!==this.config.relayAddress.toLowerCase()||tx.to.toLowerCase()!==p.request.to.toLowerCase()||tx.data!==p.request.data||tx.nonce!==p.request.nonce||tx.chainId!==p.request.chainId||(tx.value??0n)!==0n||tx.gas!==BigInt(p.request.gas)||tx.gasPrice!==BigInt(p.request.gasPrice))fail('signer_response_mismatch');
   p={...p,versions:[...p.versions,{signed,hash:keccak256(signed),signedAt:this.now()}]};
   this.store.saveAction(action.id,action.job_id,'signed',action.nonce,p);
  }
  const version=p.versions.at(-1);
  try{await this.client.sendRawTransaction({serializedTransaction:version.signed});p={...p,lastBroadcastAt:this.now()};this.store.saveAction(action.id,action.job_id,'submitted',action.nonce,p);}
  catch{this.store.health('relay',false,'broadcast_uncertain');return false;}
  this.store.health('relay',true);return false;
 }
 async reconcile(){
  const head=await this.client.getBlockNumber();
  for(const row of this.store.all("SELECT id FROM actions WHERE state='confirmed' ORDER BY nonce DESC LIMIT 64")){
   const a=this.store.action(row.id);if(!a.payload.receipt||head>BigInt(a.payload.receipt.block)+128n)continue;
   const b=await this.client.getBlock({blockNumber:BigInt(a.payload.receipt.block)});
   if(b.hash!==a.payload.receipt.blockHash){this.store.saveAction(a.id,a.job_id,'signed',a.nonce,{...a.payload,receipt:null});this.store.jobState(a.job_id,'queued','chain_reorganization');}
  }
  const a=this.pending();if(a)try{await this.advance(a);}catch(e){this.store.health('relay',false,safeCode(e));throw e;}
  return !this.pending();
 }
}
