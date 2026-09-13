// Operator-only Sepolia integration test. Run e2e.mjs --sepolia first.
// This injects a synthetic signed fixture; it does not send email or expose a
// public intake endpoint. Restore the newspaper-only scope after verification.
import { readFileSync,writeFileSync,mkdtempSync,rmSync } from 'node:fs';
import { tmpdir,homedir } from 'node:os';
import { join,resolve } from 'node:path';
import { createPublicKey,createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { createPublicClient,createWalletClient,http,parseEther } from '../../app/automation/node_modules/viem/_esm/index.js';
import { privateKeyToAccount } from '../../app/automation/node_modules/viem/_esm/accounts/index.js';
process.umask(0o077);
const root=resolve(new URL('../..',import.meta.url).pathname),dir=join(homedir(),'.config/means-of-prediction/worker');
const state=JSON.parse(readFileSync(join(dir,'digitalocean.json'))),testDir=join(homedir(),'.local/share/means-of-prediction/worker-e2e/sepolia');
const reportFile=join(testDir,'report.json'),report=JSON.parse(readFileSync(reportFile));
const ssh=['-i',join(dir,'digitalocean_ed25519'),'-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+join(dir,'known_hosts')];
const run=(program,args)=>execFileSync(program,args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:300000});
const remote=command=>run('ssh',[...ssh,'root@'+state.ip,command]);
const mode=process.argv[2];
try {
 if(!['--inject','--restore'].includes(mode)||report.chainId!==11155111||report.cases.length!==2)throw Error('Prepare the two Sepolia test markets first');
 const inject=mode==='--inject';
 const collectorFile=join(dir,'service/collector/config.json'),collector=JSON.parse(readFileSync(collectorFile));
 if(collector.chainId!==11155111||collector.relayAddress!==report.relayAddress)throw Error('Test deployment mismatch');
 if(inject){
  const client=createPublicClient({transport:http(collector.rpcUrl)});
  if(await client.getChainId()!==11155111)throw Error('Wrong chain');
  const target=parseEther('0.15'),balance=await client.getBalance({address:report.relayAddress});
  if(balance<target){
   const saved=JSON.parse(readFileSync(join(homedir(),'.mop-deployer.json'))),account=privateKeyToAccount((Array.isArray(saved)?saved[0]:saved).private_key);
   const wallet=createWalletClient({account,transport:http(collector.rpcUrl)});
   const hash=await wallet.sendTransaction({chain:null,to:report.relayAddress,value:target-balance});
   if((await client.waitForTransactionReceipt({hash})).status!=='success')throw Error('Funding failed');
   report.fundingTransactions=[...(report.fundingTransactions||[]),...(report.fundingTransaction?[report.fundingTransaction]:[]),hash];delete report.fundingTransaction;writeFileSync(reportFile,JSON.stringify(report,null,2));
  }
 }
 for(const role of ['collector','signer']){
  const path=join(dir,'service',role,'config.json'),c=JSON.parse(readFileSync(path));
  for(const key of ['allowedDkimDomains','allowedFromDomains']){c[key]=c[key].filter(d=>d!=='body-fixture.invalid');if(inject)c[key].push('body-fixture.invalid');}
  if(role==='collector')c.enabled=true;
  writeFileSync(path,JSON.stringify(c,null,2),{mode:0o600});
 }
 run(process.execPath,[join(root,'ops/settler/deploy.mjs'),'--configure']);
 if(inject){
  const stage=mkdtempSync(join(tmpdir(),'mop-fixture-'));
  try {
   const raw=readFileSync(join(testDir,'fixture.eml')),hash=createHash('sha256').update(raw).digest('hex');
   const pub=createPublicKey(readFileSync(join(root,'keys/dev-dkim.pub'))).export({format:'der',type:'spki'}).toString('base64');
   const script=`import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Store} from '/opt/mop/current/app/automation/store.mjs';
import {Collector} from '/opt/mop/current/app/automation/collector.mjs';
import {loadConfig,readPrivate} from '/opt/mop/current/app/automation/config.mjs';
const c=loadConfig();if(c.chainId!==11155111)throw Error('Test chain required');
const raw=readFileSync('/var/lib/mop-settler/test-fixture.eml');
if(createHash('sha256').update(raw).digest('hex')!==${JSON.stringify(hash)})throw Error('Fixture mismatch');
const store=new Store(c.database,Buffer.from(readPrivate(c.storageKeyFile),'hex'));
const intake=new Collector({store,config:c,resolver:async name=>{if(!name.endsWith('._domainkey.body-fixture.invalid'))throw Error('Fixture DNS scope');return [['v=DKIM1; p='+${JSON.stringify(pub)}]];}});
await intake.ingest(raw);store.close();console.log('Synthetic DKIM fixture authenticated and queued');`;
   writeFileSync(join(stage,'intake.mjs'),script);writeFileSync(join(stage,'fixture.eml'),raw);
   run('scp',[...ssh,join(stage,'intake.mjs'),'root@'+state.ip+':/var/lib/mop-settler/test-intake.mjs']);
   run('scp',[...ssh,join(stage,'fixture.eml'),'root@'+state.ip+':/var/lib/mop-settler/test-fixture.eml']);
   remote('systemctl stop mop-settler');
   try {
    remote('chown mop-settler:mop-settler /var/lib/mop-settler/test-intake.mjs /var/lib/mop-settler/test-fixture.eml && chmod 600 /var/lib/mop-settler/test-intake.mjs /var/lib/mop-settler/test-fixture.eml && runuser -u mop-settler -- env MOP_WORKER_CONFIG=/etc/mop/collector/config.json /usr/local/bin/node --experimental-strip-types /var/lib/mop-settler/test-intake.mjs');
   } finally {remote('rm -f /var/lib/mop-settler/test-intake.mjs /var/lib/mop-settler/test-fixture.eml; systemctl start mop-settler');}
   report.fixtureSha256=hash;report.injectedAt=new Date().toISOString();writeFileSync(reportFile,JSON.stringify(report,null,2));
  } finally {rmSync(stage,{recursive:true,force:true});}
 } else {
  report.newspaperOnlyRestoredAt=new Date().toISOString();writeFileSync(reportFile,JSON.stringify(report,null,2));
 }
 console.log(JSON.stringify({mode,chainId:11155111,relayAddress:report.relayAddress,ok:true}));
} catch {console.error('Deployed-worker test failed; sensitive provider output suppressed. Inspect protected service health and restore scope after diagnosis.');process.exitCode=1;}
