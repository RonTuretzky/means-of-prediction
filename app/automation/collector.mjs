import { dkimVerify } from 'mailauth/lib/dkim/verify.js';
import { resolveTxt } from 'node:dns/promises';
import { createPublicKey } from 'node:crypto';
import { keccak256 } from 'viem';
import { parseEml } from '../src/lib/prover.ts';
import { fail } from './errors.mjs';
export class Collector {
 constructor({store,config,resolver=async name=>resolveTxt(name)}){Object.assign(this,{store,config,resolver});}
 async ingest(raw,receivedAt=Date.now()){
  if(raw.length>this.config.maxMessageBytes)fail('email_too_large',422);
  let p;try{p=parseEml(Buffer.from(raw).toString('latin1'));}catch{fail('email_unparseable',422);}
  const fromDomain=p.fromAddress.split('@').at(-1)?.toLowerCase();
  if(!this.config.allowedDkimDomains.includes(p.domain)||!this.config.allowedFromDomains.some(d=>fromDomain===d||fromDomain?.endsWith('.'+d)))fail('email_outside_scope',422);
  const cache=new Map();
  const resolver=async(name,type)=>{if(type!=='TXT')fail('dns_record_unsupported');if(!cache.has(name))cache.set(name,await this.resolver(name));return cache.get(name);};
  const checked=await dkimVerify(Buffer.from(raw),{resolver});
  const result=checked.results.find(r=>r.signingDomain===p.domain&&r.selector===p.selector&&r.algo==='rsa-sha256'&&r.status.result==='pass'&&!r.canonBodyLengthLimited);
  if(!result){if(checked.results.some(r=>r.status.result==='temperror'))fail('dkim_temporarily_unavailable');fail('email_dkim_invalid',422);}
  const records=(await resolver(p.selector+'._domainkey.'+p.domain,'TXT')).map(v=>Array.isArray(v)?v.join(''):v);
  const record=records.find(t=>/(?:^|;)\s*p=/.test(t)),keyText=record&&/(?:^|;)\s*p=([^;]*)/.exec(record)?.[1].trim();
  if(!keyText)fail('dkim_key_unavailable');
  let modulus;try{const key=createPublicKey({key:Buffer.from(keyText,'base64'),format:'der',type:'spki'}).export({format:'jwk'});modulus='0x'+Buffer.from(key.n,'base64url').toString('hex');}catch{fail('dkim_key_invalid',422);}
  return this.store.putMessage(raw,{domain:p.domain,selector:p.selector,timestamp:p.timestamp,receivedAt,publicKeyHash:keccak256(modulus)});
 }
}
