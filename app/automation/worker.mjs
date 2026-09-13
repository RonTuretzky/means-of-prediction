import { encodeFunctionData, zeroAddress } from 'viem';
import { parseEml, buildEmailProof } from '../src/lib/prover.ts';
import { bodyRegex } from '../src/lib/body.ts';
import { bodyPages } from '../src/lib/body-transport.ts';
import { factoryAbi,marketAbi,bodyStoreAbi,registryAbi,verifierAbi,marketAddress } from './abi.mjs';
import { digest,json } from './store.mjs';
import { fail,safeCode } from './errors.mjs';
export class SettlementWorker {
 constructor({store,client,relay,mailbox,config}){Object.assign(this,{store,client,relay,mailbox,config});}
 read(address,abi,functionName,args=[],blockNumber){return this.client.readContract({address,abi,functionName,args,...(blockNumber!==undefined?{blockNumber}:{})});}
 async index(){
  if(await this.client.getChainId()!==this.config.chainId)fail('wrong_chain');
  const d=this.config.deployment;
  if((await this.read(d.factory,factoryAbi,'verifier')).toLowerCase()!==d.verifier.toLowerCase()||await this.read(d.verifier,verifierAbi,'bodyParsingVersion')!==1n)fail('deployment_mismatch');
  const tip=await this.client.getBlockNumber(),height=tip-BigInt(this.config.confirmations),block=await this.client.getBlock({blockNumber:height});
  const last=this.store.getMeta('chain-checkpoint');
  if(last){const canonical=await this.client.getBlock({blockNumber:BigInt(last.number)});if(canonical.hash!==last.hash){this.store.run('DELETE FROM markets');this.store.setMeta('market-cursor',0);}}
  const count=Number(await this.read(d.factory,factoryAbi,'marketCount',[],height));
  if(count>this.config.maxMarkets)fail('market_capacity_reached');
  let cursor=this.store.getMeta('market-cursor')||0;
  if(cursor>count){this.store.run('DELETE FROM markets');cursor=0;}
  for(;cursor<Math.min(count,(this.store.getMeta('market-cursor')||0)+50);cursor++){
   const {market}=await this.read(d.factory,factoryAbi,'getMarket',[BigInt(cursor)],height);
   if(market.toLowerCase()!==marketAddress(d.factory,cursor).toLowerCase())fail('factory_address_derivation_mismatch');
   const fields=['question','contentRegex','contentField','criteria','windowStart','deadline','getSources'];
   const values=await Promise.all(fields.map(f=>this.read(market,marketAbi,f,[],height)));
   const m=Object.fromEntries(fields.map((f,i)=>[f==='getSources'?'sources':f,values[i]]));
   this.store.run('INSERT INTO markets VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET address=excluded.address,config=excluded.config',cursor,market.toLowerCase(),json(m));
  }
  this.store.setMeta('market-cursor',cursor);this.store.setMeta('chain-checkpoint',{number:Number(height),hash:block.hash});
  this.store.setMeta('index-caught-up',cursor===count);this.store.health('chain',true);return cursor===count;
 }
 async settle(){
  // Dry-run must not sign or rebroadcast an action left by an earlier live run.
  if(this.config.enabled&&!await this.relay.reconcile())return;
  const d=this.config.deployment;let considered=0;
  for(const row of this.store.all('SELECT * FROM markets ORDER BY id')){
   const m=JSON.parse(row.config);
   if(await this.read(row.address,marketAbi,'resolution')!==0)continue;
   for(const [sourceIndex,source] of m.sources.entries()){
    if(!this.config.allowedDkimDomains.includes(source.dkimDomain)||await this.read(row.address,marketAbi,'sourceMatched',[BigInt(sourceIndex)]))continue;
    for(const email of this.store.all('SELECT id FROM messages WHERE domain=? AND issued_at>=? AND issued_at<=? ORDER BY issued_at DESC',source.dkimDomain,Number(m.windowStart),Number(m.deadline))){
     const saved=this.store.message(email.id),parsed=parseEml(Buffer.from(saved.raw,'base64').toString('latin1'));
     let proof;
     try{
      if(source.fromRegex&&!bodyRegex(source.fromRegex).test(parsed.fromAddress))continue;
      // Onchain checkProof is authoritative; this is only a cheap, bounded prefilter.
      const pattern=source.contentRegex||m.contentRegex;
      if(!m.criteria){const re=bodyRegex(pattern),hit=m.contentField===0?re.test(parsed.boundSubject):m.contentField===1?re.test(parsed.bodyExcerpt):re.test(parsed.boundSubject)||re.test(parsed.bodyExcerpt);if(!hit)continue;}
      proof=buildEmailProof(parsed,saved.publicKeyHash,{contentField:m.contentField,pattern});
     }catch{continue;}
     const jobId=digest(json({chain:this.config.chainId,factory:d.factory,market:row.address,sourceIndex,email:email.id,rules:row.config}));
     this.store.job(jobId,{market:row.address,source:sourceIndex,emailId:email.id});
     try{
      if(!await this.read(d.dkimRegistry,registryAbi,'isDKIMPublicKeyHashValid',[parsed.domain,saved.publicKeyHash])){this.store.jobState(jobId,'attention','dkim_key_not_registered');continue;}
      // Disclosure scope was enforced at authenticated intake before any receipt-bearing RPC.
      const [ok]=await this.read(row.address,marketAbi,'checkProof',[BigInt(sourceIndex),proof]);
      if(!ok){this.store.jobState(jobId,'waiting','proof_not_accepted');continue;}
      if(!this.config.enabled){this.store.jobState(jobId,'ready','submission_disabled');continue;}
      const direct=encodeFunctionData({abi:marketAbi,functionName:'submitProof',args:[BigInt(sourceIndex),proof]});
      let request={to:row.address,data:direct,marketId:row.id};
      if((direct.length-2)/2+200>128*1024){
       if(!d.emailBodyStore)fail('pagination_unavailable');
       const pointers=[];
       for(const page of bodyPages(proof.canonicalBody)){
        const hash=(await import('viem')).keccak256(page);
        let pointer=await this.read(d.emailBodyStore,bodyStoreAbi,'chunkForHash',[hash]);
        if(pointer===zeroAddress){
         const done=await this.relay.perform('page:'+hash,jobId,{to:d.emailBodyStore,data:encodeFunctionData({abi:bodyStoreAbi,functionName:'storeChunk',args:[page]})});
         if(!done){this.store.jobState(jobId,'uploading');return;}
         pointer=await this.read(d.emailBodyStore,bodyStoreAbi,'chunkForHash',[hash]);
        }
        if(pointer===zeroAddress)fail('page_not_available');pointers.push(pointer);
       }
       request={to:d.emailBodyStore,marketId:row.id,data:encodeFunctionData({abi:bodyStoreAbi,functionName:'submitWithChunks',args:[row.address,BigInt(sourceIndex),{...proof,canonicalBody:'0x'},pointers]})};
      }
      const done=await this.relay.perform('proof:'+jobId,jobId,request);
      this.store.jobState(jobId,done?'confirmed':'submitting');if(!done)return;
     }catch(e){this.store.jobState(jobId,'attention',safeCode(e));this.store.health('relay',false,safeCode(e));return;}
     if(++considered>=25)return;
     if(await this.read(row.address,marketAbi,'sourceMatched',[BigInt(sourceIndex)]))break;
    }
   }
  }
 }
 async tick(){
  try{
   if(this.relay.signer.health){const h=await this.relay.signer.health();if(h.address.toLowerCase()!==this.config.relayAddress.toLowerCase()||h.chainId!==this.config.chainId)fail('signer_identity_mismatch');}
   this.store.health('signer',true);
   const balance=await this.client.getBalance({address:this.config.relayAddress});this.store.setMeta('relay-balance',String(balance));
   this.store.health('relay',balance>=BigInt(this.config.minBalance||'100000000000000'),'relay_needs_gas');
   if(balance>=BigInt(this.config.minBalance||'100000000000000'))this.store.health('relay',true);
   const indexed=await this.index();let intake={caughtUp:this.store.getMeta('mailbox-caught-up')===true};
   const lastMail=this.store.getMeta('mailbox-poll-at')||0;
   if(this.mailbox&&(!intake.caughtUp||Date.now()-lastMail>=this.config.pollMs)){intake=await this.mailbox.poll();this.store.setMeta('mailbox-poll-at',Date.now());}
   if(!this.mailbox)intake={caughtUp:true};if(indexed)await this.settle();this.store.health('worker',true);return intake;}
  catch(e){this.store.health('worker',false,safeCode(e));return {caughtUp:false,error:safeCode(e)};}
 }
}
