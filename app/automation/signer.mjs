import { decodeFunctionData, encodeFunctionData, keccak256 } from 'viem';
import { marketAbi, bodyStoreAbi, marketAddress } from './abi.mjs';
import { fail } from './errors.mjs';
import { digest, json } from './store.mjs';
export class RestrictedSigner {
 constructor({account,store,config,now=Date.now}){Object.assign(this,{account,store,config,now});}
 async sign(input){
  if(input.chainId!==this.config.chainId||input.value!=='0'||!Number.isSafeInteger(input.nonce)||input.nonce<0||!/^0x[0-9a-f]*$/i.test(input.data)||input.data.length%2!==0)fail('signer_policy_rejected',422);
  let gas,gasPrice;try{gas=BigInt(input.gas);gasPrice=BigInt(input.gasPrice);}catch{fail('signer_policy_rejected',422);}
  if(gas<21000n||gas>BigInt(this.config.maxGas)||gasPrice<=0n||gasPrice>BigInt(this.config.maxGasPrice)||(input.data.length-2)/2+200>128*1024)fail('signer_limits_rejected',422);
  const isStore=input.to?.toLowerCase()===this.config.emailBodyStore.toLowerCase();
  let decoded;try{decoded=decodeFunctionData({abi:isStore?bodyStoreAbi:marketAbi,data:input.data});}catch{fail('signer_function_rejected',422);}
  const canonical=encodeFunctionData({abi:isStore?bodyStoreAbi:marketAbi,functionName:decoded.functionName,args:decoded.args});
  if(canonical.toLowerCase()!==input.data.toLowerCase())fail('signer_calldata_noncanonical',422);
  if(isStore&&decoded.functionName==='storeChunk'){
   const size=(decoded.args[0].length-2)/2;if(size<1||size>24000)fail('signer_chunk_rejected',422);
  }else{
   if(!Number.isSafeInteger(input.marketId)||input.marketId<0||input.marketId>=this.config.maxMarkets)fail('signer_market_rejected',422);
   const expected=marketAddress(this.config.factory,input.marketId).toLowerCase();
   let proof,source;
   if(isStore&&decoded.functionName==='submitWithChunks'){
    const [market,index,p,pointers]=decoded.args;source=index;proof=p;
    if(market.toLowerCase()!==expected||p.canonicalBody!=='0x'||pointers.length<1||pointers.length>9)fail('signer_market_rejected',422);
   }else if(!isStore&&decoded.functionName==='submitProof'){
    if(input.to.toLowerCase()!==expected)fail('signer_market_rejected',422);
    [source,proof]=decoded.args;
   }else fail('signer_function_rejected',422);
   if(source>255n||!this.config.allowedDkimDomains.includes(proof.domainName))fail('signer_source_rejected',422);
  }
  const fingerprint=digest(json({to:input.to.toLowerCase(),data:input.data.toLowerCase(),chainId:input.chainId,nonce:input.nonce}));
  const key='nonce:'+input.nonce,day=new Date(this.now()).toISOString().slice(0,10),cost=gas*gasPrice;
  const prior=this.store.getMeta(key);
  if(prior&&prior.fingerprint!==fingerprint)fail('signer_nonce_conflict',409);
  if(prior&&gasPrice<BigInt(prior.gasPrice))fail('signer_replacement_underpriced',409);
  if(prior&&gasPrice===BigInt(prior.gasPrice)&&gas===BigInt(prior.gas)&&prior.signed)return this.store.open(Buffer.from(prior.signed,'base64'),'signed:'+input.nonce).signed;
  this.store.transaction(()=>{
   const old=this.store.getMeta(key),previous=old?.day===day?BigInt(old.cost):0n,additional=cost>previous?cost-previous:0n;
   const spent=BigInt(this.store.getMeta('budget:'+day)||'0');
   if(spent+additional>BigInt(this.config.dailyBudget))fail('signer_daily_budget_exhausted',429);
   this.store.setMeta('budget:'+day,String(spent+additional));
   this.store.setMeta(key,{fingerprint,cost:String(cost>previous?cost:previous),gasPrice:String(gasPrice),gas:String(gas),day});
  });
  const signed=await this.account.signTransaction({chainId:input.chainId,to:input.to,data:input.data,value:0n,nonce:input.nonce,gas,gasPrice,type:'legacy'});
  this.store.transaction(()=>{const state=this.store.getMeta(key);this.store.setMeta(key,{...state,hash:keccak256(signed),signed:this.store.seal({signed},'signed:'+input.nonce).toString('base64')});});
  return signed;
 }
}
