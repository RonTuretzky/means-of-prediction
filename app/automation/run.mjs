import httpServer from 'node:http';
import { setTimeout as delay } from 'node:timers/promises';
import { createPublicClient,http } from 'viem';
import { Store } from './store.mjs';
import { loadConfig,readPrivate } from './config.mjs';
import { SignerClient } from './signer-ipc.mjs';
import { Collector } from './collector.mjs';
import { MailboxWorker } from './imap.mjs';
import { Relay } from './relay.mjs';
import { SettlementWorker } from './worker.mjs';
import { safeCode } from './errors.mjs';
process.umask(0o077);
try{
 const c=loadConfig(),store=new Store(c.database,Buffer.from(readPrivate(c.storageKeyFile),'hex'));
 const saved=JSON.parse(readPrivate(c.mailboxFile));
 c.mailbox={host:saved.host||'imap.gmail.com',user:saved.user,pass:saved.appPassword,oauth:saved.oauth,accessToken:saved.accessToken,mailboxes:saved.mailboxes};
 const client=createPublicClient({transport:http(c.rpcUrl,{timeout:30000,retryCount:1})});
 const relay=new Relay({store,client,config:c,signer:new SignerClient(c.socketPath)});
 const collector=new Collector({store,config:c}),mailbox=new MailboxWorker({store,collector,config:c});
 const worker=new SettlementWorker({store,client,relay,mailbox,config:c});
 const server=httpServer.createServer((req,res)=>{
  if(req.method!=='GET'||req.url!=='/health'){res.writeHead(404).end();return;}
  const health=store.all('SELECT name,ok,code,checked_at FROM health'),fresh=health.length>=3&&health.every(h=>h.ok&&Date.now()-h.checked_at<Math.max(c.pollMs*3,180000));
  const status={ok:fresh,mode:c.enabled?'automatic':'dry-run',chainId:c.chainId,factory:c.deployment.factory,relayAddress:c.relayAddress,relayBalanceWei:store.getMeta('relay-balance'),allowedDkimDomains:c.allowedDkimDomains,mailboxCaughtUp:store.getMeta('mailbox-caught-up')===true,indexCaughtUp:store.getMeta('index-caught-up')===true,...store.counts(),health};
  res.writeHead(fresh?200:503,{'Content-Type':'application/json','Cache-Control':'no-store'}).end(JSON.stringify(status));
 });
 await new Promise(resolve=>server.listen(c.healthPort||4321,'127.0.0.1',resolve));
 const abort=new AbortController();let stopped=false;for(const signal of ['SIGTERM','SIGINT'])process.once(signal,()=>{stopped=true;abort.abort();server.close();});
 console.log(JSON.stringify({event:'worker_started',chainId:c.chainId,scope:c.allowedDkimDomains}));
 while(!stopped){const status=await worker.tick();
  if(process.argv.includes('--once'))break;
  try{await delay(status.caughtUp&&!relay.pending()?c.pollMs:Math.min(c.pollMs,5000),undefined,{signal:abort.signal});}catch(e){if(e.name!=='AbortError')throw e;}
 }
 server.close();store.close();
}catch(e){console.error(JSON.stringify({event:'worker_failed',code:safeCode(e)}));process.exitCode=1;}
