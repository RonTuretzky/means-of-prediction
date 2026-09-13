import { readFileSync,statSync } from 'node:fs';
import { fail } from './errors.mjs';
export function readPrivate(path){if(!path||statSync(path).mode&0o077)fail('configuration_permissions');return readFileSync(path,'utf8').trim();}
export function loadConfig(){
 const c=JSON.parse(readPrivate(process.env.MOP_WORKER_CONFIG));
 if(c.deployment?.chainId!==c.chainId||c.deployment?.bodyParsingVersion!==1||![11155111,31337].includes(c.chainId))fail('configuration_chain_rejected');
 if(!Array.isArray(c.allowedDkimDomains)||!c.allowedDkimDomains.length||!Array.isArray(c.allowedFromDomains)||!c.allowedFromDomains.length||!c.discoveryFrom?.length)fail('configuration_scope_missing');
 if(c.pollMs<1000||c.pollMs>3600000||c.messagesPerPoll<1||c.uidBatch<1||c.maxMessageBytes>1024*1024||c.confirmations<0||c.maxMarkets<1)fail('configuration_bounds');
 return c;
}
