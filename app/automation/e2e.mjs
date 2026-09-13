// Local: real contracts + raw signed email intake + IPC signer + durable worker.
// Sepolia: prepare/observe a labelled public fixture for the deployed worker.
import { readFileSync,writeFileSync,mkdirSync,existsSync } from 'node:fs';
import { join } from 'node:path';import { homedir } from 'node:os';import { randomBytes,createPublicKey } from 'node:crypto';
import { createPublicClient,createWalletClient,http,parseEventLogs,maxUint256,parseEther,zeroAddress } from 'viem';
import { privateKeyToAccount,generatePrivateKey } from 'viem/accounts';
import { Store } from './store.mjs';import { Collector } from './collector.mjs';import { MailboxWorker } from './imap.mjs';
import { RestrictedSigner } from './signer.mjs';import { SignerClient,serveSigner } from './signer-ipc.mjs';import { Relay } from './relay.mjs';import { SettlementWorker } from './worker.mjs';
import { signEml } from '../scripts/dkim.mjs';
process.umask(0o077);
const fatal=e=>{console.error(JSON.stringify({event:'e2e_failed',error:e.shortMessage||String(e.message).split('\n')[0]}));process.exit(1);};
process.on('uncaughtException',fatal);process.on('unhandledRejection',fatal);
const publicMode=process.argv.includes('--sepolia'),finish=process.argv.includes('--finish'),chainId=publicMode?11155111:31337;
const root=new URL('../../',import.meta.url).pathname,dir=join(homedir(),'.local/share/means-of-prediction/worker-e2e',publicMode?'sepolia':'local');mkdirSync(dir,{recursive:true,mode:0o700});
const reportFile=join(dir,'report.json');const report=existsSync(reportFile)?JSON.parse(readFileSync(reportFile)):{chainId,tag:randomBytes(3).toString('hex'),cases:[],transactions:[]};
const save=()=>writeFileSync(reportFile,JSON.stringify(report,null,2),{mode:0o600});
const dep=publicMode?JSON.parse(readFileSync(root+'contracts/deployments/sepolia.json')):{...JSON.parse(readFileSync(join(homedir(),'.local/share/means-of-prediction/body-e2e/local.json'))).contracts,chainId,bodyParsingVersion:1};
const rpc=publicMode?'https://ethereum-sepolia-rpc.publicnode.com':'http://127.0.0.1:8559';
const client=createPublicClient({cacheTime:0,transport:http(rpc,{timeout:60000})});if(await client.getChainId()!==chainId)throw Error('Wrong E2E chain');
let deployer;if(publicMode){const d=JSON.parse(readFileSync(join(homedir(),'.mop-deployer.json')));deployer=privateKeyToAccount((Array.isArray(d)?d[0]:d).private_key);}else deployer=privateKeyToAccount('0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80');
const wallet=createWalletClient({account:deployer,transport:http(rpc)});
const abi=name=>JSON.parse(readFileSync(root+'contracts/out/'+name+'.sol/'+name+'.json')).abi;
async function read(address,name,functionName,args=[]){return client.readContract({address,abi:abi(name),functionName,args});}
async function send(address,name,functionName,args,label){const req={account:deployer,address,abi:abi(name),functionName,args,gas:16000000n};await client.simulateContract(req);const estimate=await client.estimateContractGas(req);const gas=estimate*110n/100n;if(gas>16777216n)throw Error('E2E gas cap');const hash=await wallet.writeContract({...req,gas,chain:null});const r=await client.waitForTransactionReceipt({hash,timeout:180000});if(r.status!=='success')throw Error('E2E reverted');report.transactions.push({label,hash,gasUsed:String(r.gasUsed)});save();console.log(label+' '+hash);return r;}
let localAccount;if(!publicMode){const f=join(dir,'relay.key');if(!existsSync(f))writeFileSync(f,generatePrivateKey(),{mode:0o600});localAccount=privateKeyToAccount(readFileSync(f,'utf8').trim());}
report.relayAddress=publicMode?JSON.parse(readFileSync(join(homedir(),'.config/means-of-prediction/worker/service/collector/config.json'))).relayAddress:localAccount.address;
const fixtureFile=join(dir,'fixture.eml');
if(!existsSync(fixtureFile)){
 const timestamp=Number((await client.getBlock()).timestamp),padding=Array.from({length:2250},(_,i)=>'<p>Synthetic worker padding '+i.toString().padStart(4,'0')+' abcdefghijklmnopqrstuvwxyz0123456789</p>').join('\r\n');
 const raw='From: Automatic test <fixture@body-fixture.invalid>\r\nSubject: Automation '+report.tag+': Blue wins\r\nDate: '+new Date(timestamp*1000).toUTCString()+'\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n'+padding+'\r\n<p>Automatic '+report.tag+': Blue won.</p>\r\n';
 writeFileSync(fixtureFile,signEml(raw,{domain:'body-fixture.invalid',headers:['from','subject','date','content-type','content-transfer-encoding']}),'latin1');report.timestamp=timestamp;save();
}
if(!finish){
 if(!publicMode&&await client.getBalance({address:localAccount.address})<parseEther('0.1'))await client.waitForTransactionReceipt({hash:await wallet.sendTransaction({chain:null,to:localAccount.address,value:parseEther('1')})});
 for(const [kind,contentField,pattern]of[['subject',0,'Automation '+report.tag+': Blue wins'],['body',1,'Automatic '+report.tag+': Blue won[.]']]){
  if(report.cases.some(c=>c.kind===kind))continue;
  await send(dep.usdc,'TestUSDC','mint',[deployer.address,10000_000000n],'mint test collateral');
  await send(dep.usdc,'TestUSDC','approve',[dep.factory,maxUint256],'approve test funding');
  const p={question:'Synthetic auto-email '+kind+' test '+report.tag,description:'Synthetic fixture under body-fixture.invalid. YES when the authenticated '+kind+' contains the exact declared substring. This is not newspaper reporting.',contentRegex:pattern,criteria:'',contentField,sources:[{name:'Synthetic fixture',dkimDomain:'body-fixture.invalid',fromRegex:'^fixture@body-fixture[.]invalid$',contentRegex:''}],threshold:1,windowStart:BigInt(report.timestamp-60),deadline:BigInt(report.timestamp+86400),resolutionBuffer:86400n,collateralToken:dep.usdc,fee:20000000000000000n,initialLiquidity:1000_000000n,distributionHint:[]};
  const receipt=await send(dep.factory,'MarketFactory','createMarket',[p],'create automatic '+kind+' market');const ev=parseEventLogs({abi:abi('MarketFactory'),eventName:'MarketCreated',logs:receipt.logs})[0];
  const c={kind,market:ev.args.market,id:Number(ev.args.marketId),fpmm:ev.args.fpmm};report.cases.push(c);save();
  await send(dep.usdc,'TestUSDC','approve',[c.fpmm,maxUint256],'approve automatic test buy');
  await send(c.fpmm,'FPMM','buy',[100_000000n,0n,0n],'buy automatic test YES');
 }
 if(publicMode){console.log(JSON.stringify({prepared:true,fixtureFile,reportFile,relayAddress:report.relayAddress}));process.exit(0);}
}
let server,store,signerStore;
if(publicMode&&finish&&process.argv.includes('--wait')){
 const deadline=Date.now()+15*60*1000;
 while(!(await Promise.all(report.cases.map(c=>read(c.market,'HeadlineMarket','resolution')))).every(x=>x===1)){
  if(Date.now()>deadline)throw Error('Timed out waiting for automatic settlement');
  await new Promise(resolve=>setTimeout(resolve,10000));
 }
}
if(!publicMode){
 const keyFile=join(dir,'storage.key');if(!existsSync(keyFile))writeFileSync(keyFile,randomBytes(32).toString('hex'),{mode:0o600});const key=Buffer.from(readFileSync(keyFile,'utf8'),'hex');
 store=new Store(join(dir,'worker.sqlite'),key);signerStore=new Store(join(dir,'signer.sqlite'),key);
 const config={chainId,deployment:dep,factory:dep.factory,emailBodyStore:dep.emailBodyStore,relayAddress:localAccount.address,maxGas:'16000000',maxGasPrice:'2000000000',dailyBudget:'1000000000000000000',maxMarkets:10000,confirmations:0,enabled:true,pollMs:1000,maxMessageBytes:524288,uidBatch:100,messagesPerPoll:25,allowedDkimDomains:['body-fixture.invalid'],allowedFromDomains:['body-fixture.invalid'],discoveryFrom:['body-fixture.invalid'],mailbox:{host:'imap.test',user:'synthetic@test.invalid'}};
 const socket=join(dir,'signer.sock');server=await serveSigner(socket,new RestrictedSigner({account:localAccount,store:signerStore,config}));
 const dns=createPublicKey(readFileSync(root+'keys/dev-dkim.pub')).export({format:'der',type:'spki'}).toString('base64');
 const collector=new Collector({store,config,resolver:async()=>[['v=DKIM1; p='+dns]]});
 const raw=readFileSync(fixtureFile),imap={mailbox:{uidValidity:'1',uidNext:2},list:async()=>[{path:'INBOX',flags:new Set()}],getMailboxLock:async()=>({release(){}}),search:async()=>[1],fetchOne:async(_uid,fields)=>fields.source?{source:raw,internalDate:new Date()}:{size:raw.length,flags:new Set(),labels:new Set()},logout:async()=>{},close(){}};
 const mailbox=new MailboxWorker({store,collector,config,connect:async()=>imap});
 let relay=new Relay({store,client,config,signer:new SignerClient(socket)}),worker=new SettlementWorker({store,client,relay,mailbox,config});
 for(let i=0;i<80;i++){
  await worker.tick();await client.request({method:'evm_mine',params:[]});
  // Reconstruct the coordinator midway, preserving its encrypted journal and signer.
  if(i===2){relay=new Relay({store,client,config,signer:new SignerClient(socket)});worker=new SettlementWorker({store,client,relay,mailbox,config});report.coordinatorRestarted=true;}
  if((await Promise.all(report.cases.map(c=>read(c.market,'HeadlineMarket','resolution')))).every(x=>x===1))break;
  const bad=store.all('SELECT name,code FROM health WHERE ok=0');if(bad.length)console.log(JSON.stringify({iteration:i,health:bad}));
 }
 await worker.tick();report.journal=store.counts();save();
}
try{
 for(const c of report.cases){
  if(await read(c.market,'HeadlineMarket','resolution')!==1)throw Error('Automatic settlement not complete');
  const evidence=await read(c.market,'HeadlineMarket','getEvidence');
  // Paginated calls forward via the body store; direct calls record the relay.
  const expected=c.kind==='body'?dep.emailBodyStore:report.relayAddress;
  if(evidence[0].submitter.toLowerCase()!==expected.toLowerCase())throw Error('Wrong evidence submitter');
  const transferAmount=receipt=>parseEventLogs({abi:abi('TestUSDC'),eventName:'Transfer',logs:receipt.logs}).filter(l=>l.address.toLowerCase()===dep.usdc.toLowerCase()&&l.args.to.toLowerCase()===deployer.address.toLowerCase()).reduce((n,l)=>n+l.args.value,0n);
  if(!c.redeemed){
   const label='redeem automatic '+c.kind+' winner',previous=report.transactions.find(t=>t.label===label);
   const condition=await read(c.market,'HeadlineMarket','conditionId');
   const receipt=previous?await client.getTransactionReceipt({hash:previous.hash}):await send(dep.conditionalTokens,'ConditionalTokens','redeemPositions',[dep.usdc,condition,[1n,2n]],label);
   // Receipt events are transaction-specific; a load-balanced RPC may briefly
   // return an older state for a separate latest-balance query.
   if(receipt.status!=='success'||transferAmount(receipt)<=0n)throw Error('No redemption');
   c.redeemed=true;c.redemptionAmount=String(transferAmount(receipt));save();
  }
  if(!c.feeCollected){
   const label='collect automatic '+c.kind+' fee',previous=report.transactions.find(t=>t.label===label);
   if(!previous&&await read(c.fpmm,'FPMM','protocolFeesAccrued')!==1_000000n)throw Error('Fee mismatch');
   const receipt=previous?await client.getTransactionReceipt({hash:previous.hash}):await send(c.fpmm,'FPMM','withdrawProtocolFees',[],label);
   if(receipt.status!=='success'||transferAmount(receipt)!==1_000000n)throw Error('Fee transfer mismatch');
   c.feeCollected=true;save();
  }
 }
 report.complete=true;report.completedAt=new Date().toISOString();save();console.log(JSON.stringify({complete:true,reportFile,relayAddress:report.relayAddress}));
}finally{if(server)await new Promise(resolve=>server.close(resolve));store?.close();signerStore?.close();}
