#!/usr/bin/env node
// Fresh body-verifier deployment + real-chain lifecycle. Public mode only uses a
// labelled dev fixture under body-fixture.invalid. Private NYT mail is local-only.
import {readFileSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {homedir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {resolveTxt} from 'node:dns/promises';
import {createHash} from 'node:crypto';
import {createPublicClient,createWalletClient,http,zeroAddress,keccak256,maxUint256,parseEventLogs,encodeFunctionData} from 'viem';
import {privateKeyToAccount} from 'viem/accounts';
import {parseEml,buildEmailProof} from '../src/lib/prover.ts';
import {signEml,devPublicKey,dnsKeyToHex} from './dkim.mjs';
process.umask(0o077);
const fatal = error => { console.error(JSON.stringify({error:error.shortMessage || String(error.message).split("\n")[0],details:error.details?.startsWith('invalid value: string')?'Invalid serialized RPC value (payload suppressed)':error.details?.slice(0,300)})); process.exit(1); };
process.on('uncaughtException',fatal); process.on('unhandledRejection',fatal);
const root=join(dirname(fileURLToPath(import.meta.url)),'../..');
const args=process.argv.slice(2), opt=(name,fallback)=>args.includes('--'+name)?args[args.indexOf('--'+name)+1]:fallback;
const publicMode=args.includes('--sepolia');
const rpc=opt('rpc',publicMode?'https://ethereum-sepolia-rpc.publicnode.com':'http://127.0.0.1:8559');
const pub=createPublicClient({transport:http(rpc,{timeout:60000}),pollingInterval:publicMode?2000:50});
const chainId=await pub.getChainId();
if(chainId!==(publicMode?11155111:31337))throw new Error('Wrong chain for selected mode');
if(publicMode&&args.includes('--real-email'))throw new Error('Private email tests must stay on local Anvil');
let secret;
if(publicMode){const cfg=JSON.parse(readFileSync(join(homedir(),'.mop-deployer.json'),'utf8'));secret=(Array.isArray(cfg)?cfg[0]:cfg).private_key;}
else secret='0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80';
const account=privateKeyToAccount(secret);secret=undefined;
const wallet=createWalletClient({account,transport:http(rpc,{timeout:60000})});
const dir=join(homedir(),'.local/share/means-of-prediction/body-e2e');mkdirSync(dir,{recursive:true,mode:0o700});
const output=opt('output',join(dir,publicMode?'sepolia.json':'local.json'));
const report=existsSync(output)?JSON.parse(readFileSync(output,'utf8')):{chainId,startedAt:new Date().toISOString(),deployer:account.address,contracts:{},transactions:[],checks:{},cases:[]};
if(report.chainId!==chainId)throw new Error('Report belongs to another chain');
const save=()=>writeFileSync(output,JSON.stringify(report,null,2),{mode:0o600});
const artifact=name=>JSON.parse(readFileSync(join(root,'contracts/out',name+'.sol',name+'.json'),'utf8'));
const abi=name=>artifact(name).abi;
async function receipt(hash,label){
 const r=await pub.waitForTransactionReceipt({hash,timeout:180000});
 if(r.status!=='success')throw new Error(label+' reverted');
 report.transactions.push({label,hash,block:Number(r.blockNumber),gasUsed:String(r.gasUsed)});save();
 console.log(label+': '+hash+' ('+r.gasUsed+' gas)');return r;
}
async function deploy(name,key,constructorArgs=[]){
 const a=artifact(name);
 if(report.contracts[key]){
  if(!await pub.getCode({address:report.contracts[key]}))throw new Error('Saved deployment has no code: '+key);
  return report.contracts[key];
 }
 let bytecode=a.bytecode.object;
 for(const libs of Object.values(a.bytecode.linkReferences || {})) for(const [lib,positions] of Object.entries(libs)) {
   const address=await deploy(lib,lib[0].toLowerCase()+lib.slice(1));
   for(const {start,length} of positions) bytecode=bytecode.slice(0,2+start*2)+address.slice(2).padStart(length*2,'0')+bytecode.slice(2+(start+length)*2);
 }
 const gas=await pub.estimateGas({account:account.address,gas:16000000n,data:(await import('viem')).encodeDeployData({abi:a.abi,bytecode,args:constructorArgs})});
 if(gas>15000000n)throw new Error('Deployment exceeds transaction budget: '+name);
 const r=await receipt(await wallet.deployContract({chain:null,abi:a.abi,bytecode,args:constructorArgs,gas:gas*110n/100n}), 'deploy '+name);
 report.contracts[key]=r.contractAddress;save();return r.contractAddress;
}
async function read(address,name,fn,values=[]){return pub.readContract({address,abi:abi(name),functionName:fn,args:values});}
async function send(address,name,fn,values=[],label=fn){
 const req={account:account.address,gas:16000000n,address,abi:abi(name),functionName:fn,args:values};
 await pub.simulateContract(req);
 const gas=await pub.estimateContractGas(req);
 if(gas>16000000n)throw new Error(label+' exceeds 16M gas budget: '+gas);
 return receipt(await wallet.writeContract({...req,account,chain:null,gas:gas*105n/100n>16700000n?16700000n:gas*105n/100n}),label);
}
const ct=await deploy('ConditionalTokens','conditionalTokens');
const usdc=await deploy('TestUSDC','usdc');
const registry=await deploy('DKIMRegistry','dkimRegistry');
const verifier=await deploy('DKIMVerifier','verifier',[registry]);
const impl=await deploy('HeadlineMarket','marketImplementation');
const pool=await deploy('FPMM','fpmmImplementation');
const factory=await deploy('MarketFactory','factory',[ct,verifier,impl,pool,zeroAddress,10000000000000000n,account.address]);
const bodyStore=await deploy('EmailBodyStore','emailBodyStore');
const multicall=publicMode?'0xcA11bde05977b3631167028862bE2a173976CA11':await deploy('Multicall3','multicall3');
report.contracts.multicall3=multicall;
if(await read(verifier,'DKIMVerifier','bodyParsingVersion')!==1n)throw new Error('Unexpected body profile');
report.checks.bodyParsingVersion=1;
// Read back deployment wiring and size limits; no guessed or dry-run addresses.
for(const [fn,want] of [['verifier',verifier],['conditionalTokens',ct],['marketImplementation',impl],['fpmmImplementation',pool]]){
 if((await read(factory,'MarketFactory',fn)).toLowerCase()!==want.toLowerCase())throw new Error('Wrong factory '+fn);
}
for(const [key,address] of Object.entries(report.contracts)){
 const code=await pub.getCode({address});if(!code||code==='0x')throw new Error('No code for '+key);
 if((code.length-2)/2>24576)throw new Error('Oversized deployed contract');
}
const contractNames={conditionalTokens:'ConditionalTokens',usdc:'TestUSDC',dkimRegistry:'DKIMRegistry',verifier:'DKIMVerifier',marketImplementation:'HeadlineMarket',fpmmImplementation:'FPMM',factory:'MarketFactory',regexLib:'RegexLib',multicall3:'Multicall3',emailBodyStore:'EmailBodyStore'};
for(const [key,name] of Object.entries(contractNames)){
 if(publicMode && key==='multicall3') continue;
 const a=artifact(name);let expected=a.deployedBytecode.object.toLowerCase();let actual=(await pub.getCode({address:report.contracts[key]})).toLowerCase();
 const mask=(value,start,length)=>value.slice(0,2+start*2)+'0'.repeat(length*2)+value.slice(2+(start+length)*2);
 for(const refs of Object.values(a.deployedBytecode.immutableReferences || {}))for(const ref of refs){expected=mask(expected,ref.start,ref.length);actual=mask(actual,ref.start,ref.length);}
 for(const libs of Object.values(a.deployedBytecode.linkReferences || {}))for(const [lib,refs] of Object.entries(libs))for(const ref of refs){
  const addr=report.contracts[lib[0].toLowerCase()+lib.slice(1)].slice(2).toLowerCase();
  expected=expected.slice(0,2+ref.start*2)+addr+expected.slice(2+(ref.start+ref.length)*2);
 }
 if(expected!==actual)throw new Error('Deployed runtime differs from compiled artifact: '+name);
}
report.checks.compiledRuntimeMatches=true;
report.checks.deploymentWiring=true;save();
async function register(domain,selector,key){
 const hash=keccak256(key.modulus);
 if(!await read(registry,'DKIMRegistry','isDKIMPublicKeyHashValid',[domain,hash]))await send(registry,'DKIMRegistry','registerKey',[domain,selector,key.exponent,key.modulus],'register '+domain+' '+selector);
 return hash;
}
async function exercise({label,raw,key,pattern,question,paginated=false}){
 if(report.cases.some(c=>c.label===label&&c.complete))return;
 const parsed=parseEml(raw),keyHash=await register(parsed.domain,parsed.selector,key);
 const proof=buildEmailProof(parsed,keyHash,{contentField:1,pattern});
 const calldataBytes=(encodeFunctionData({abi:abi('HeadlineMarket'),functionName:'submitProof',args:[0n,proof]}).length-2)/2;
 const fitsCommonTxpoolLimit=calldataBytes+200<=128*1024;
 paginated=paginated||!fitsCommonTxpoolLimit;
 if(!await read(verifier,'DKIMVerifier','verify',[proof]))throw new Error(label+': verifier rejected real proof');
 const badExcerpt={...proof,bodyExcerpt:proof.bodyExcerpt+' forged'};
 const badBody={...proof,canonicalBody:proof.canonicalBody+'00'};
 const invalidExcerpt=!await read(verifier,'DKIMVerifier','verify',[badExcerpt]);
 const invalidBody=!await read(verifier,'DKIMVerifier','verify',[badBody]);
 if(!invalidExcerpt||!invalidBody)throw new Error('Tampering was accepted');
 let c=report.cases.find(c=>c.label===label);
 if(!c){c={label,emailSha256:createHash('sha256').update(raw,'latin1').digest('hex'),question,pattern,bodyBytes:parsed.canonicalBody.length,windowBytes:Number(proof.bodyLength)};report.cases.push(c);save();}
 if(!c.market){
  await send(usdc,'TestUSDC','mint',[account.address,10000_000000n],label+' test collateral');
  await send(usdc,'TestUSDC','approve',[factory,maxUint256],label+' approve funding');
  const now=(await pub.getBlock()).timestamp;
  const params={question,description:'E2E '+label+'. Resolves YES when the authenticated decoded body SOURCE contains /'+pattern+'/. '+
    'HTML markup is retained; this is a substring rule, not the original Polymarket oracle rule. Full body bh= is verified; no DKIM l= signatures. '+
    'Signed Date must fall within the explicit bounds below. NO after deadline plus 24 hours if no proof was accepted.',
    contentRegex:pattern,criteria:'',contentField:1,sources:[{name:label,dkimDomain:parsed.domain,fromRegex:'^'+parsed.fromAddress.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$',contentRegex:''}],threshold:1,
    windowStart:BigInt(parsed.timestamp)-3600n,deadline:BigInt(parsed.timestamp)+3600n>now?BigInt(parsed.timestamp)+3600n:now+86400n,
    resolutionBuffer:86400n,collateralToken:usdc,fee:20000000000000000n,initialLiquidity:1000_000000n,distributionHint:[]};
  // Historical NYT tests intentionally use a retrospective explicit-evidence rule.
  params.description+=' Accepted signed-date bounds: '+params.windowStart+' to '+params.deadline+' Unix seconds.';
  const rc=await send(factory,'MarketFactory','createMarket',[params],label+' create market');
  const ev=parseEventLogs({abi:abi('MarketFactory'),logs:rc.logs,eventName:'MarketCreated'})[0];
  Object.assign(c,{market:ev.args.market,fpmm:ev.args.fpmm,marketId:String(ev.args.marketId),creationTx:rc.transactionHash,rules:params.description});save();
 }
 let pointers=[];
 if(paginated){
  for(let offset=2;offset<proof.canonicalBody.length;offset+=48000){
   const chunk='0x'+proof.canonicalBody.slice(offset,offset+48000), hash=keccak256(chunk);
   let pointer=await read(bodyStore,'EmailBodyStore','chunkForHash',[hash]);
   if(pointer===zeroAddress){
    await send(bodyStore,'EmailBodyStore','storeChunk',[chunk],label+' upload page '+(pointers.length+1));
    pointer=await read(bodyStore,'EmailBodyStore','chunkForHash',[hash]);
   }
   if(pointer===zeroAddress)throw new Error('Chunk not stored');
   pointers.push(pointer);
  }
  const compact={...proof,canonicalBody:'0x'};
  if(await read(c.market,'HeadlineMarket','resolution')===0){
   const [ok,why]=await read(bodyStore,'EmailBodyStore','checkWithChunks',[c.market,0n,compact,pointers]);
   if(!ok)throw new Error('Paginated preflight failed: '+why);
   if(pointers.length>1){
    const [reordered]=await read(bodyStore,'EmailBodyStore','checkWithChunks',[c.market,0n,compact,[...pointers].reverse()]);
    if(reordered)throw new Error('Reordered pages accepted');
   }
  }
  const encoded=encodeFunctionData({abi:abi('EmailBodyStore'),functionName:'submitWithChunks',args:[c.market,0n,compact,pointers]});
  c.finalCalldataBytes=(encoded.length-2)/2;
  if(c.finalCalldataBytes+200>128*1024)throw new Error('Final chunk submission too large');
  Object.assign(c,{transport:'paginated',pageCount:pointers.length,pointers,uploadGas:String(report.transactions.filter(t=>t.label.startsWith(label+' upload page')).reduce((n,t)=>n+BigInt(t.gasUsed),0n))});save();
 }
 if(await read(c.market,'HeadlineMarket','resolution')===0){
  const [subjectOk]=await read(c.market,'HeadlineMarket','checkProof',[0n,buildEmailProof(parsed,keyHash)]);
  const [valid,reason]=await read(c.market,'HeadlineMarket','checkProof',[0n,proof]);
  if(subjectOk||!valid)throw new Error('Body-only acceptance failed: '+reason);
  if(!c.purchaseTx){
   await send(usdc,'TestUSDC','approve',[c.fpmm,maxUint256],label+' approve trade');
   const r=await send(c.fpmm,'FPMM','buy',[100_000000n,0n,0n],label+' buy YES');c.purchaseTx=r.transactionHash;save();
  }
  if(await read(c.fpmm,'FPMM','protocolFeesAccrued')!==1_000000n)throw new Error('Platform fee incorrect');
  const r=paginated
   ?await send(bodyStore,'EmailBodyStore','submitWithChunks',[c.market,0n,{...proof,canonicalBody:'0x'},pointers],label+' body settlement')
   :await send(c.market,'HeadlineMarket','submitProof',[0n,proof],label+' body settlement');
  c.settlementTx=r.transactionHash;c.settlementGas=String(r.gasUsed);save();
 }
 const condition=await read(c.market,'HeadlineMarket','conditionId');
 if(await read(c.market,'HeadlineMarket','resolution')!==1||await read(ct,'ConditionalTokens','payoutNumerators',[condition,0n])!==1n)throw new Error('Incorrect payout');
 if(!c.redemptionTx){
  const before=await read(usdc,'TestUSDC','balanceOf',[account.address]);
  const r=await send(ct,'ConditionalTokens','redeemPositions',[usdc,condition,[1n,2n]],label+' redeem winner');
  const after=await read(usdc,'TestUSDC','balanceOf',[account.address]);if(after<=before)throw new Error('Winner was not paid');
  c.redemptionTx=r.transactionHash;c.redeemedMicrounits=String(after-before);save();
 }
 if(!c.feeWithdrawalTx){const r=await send(c.fpmm,'FPMM','withdrawProtocolFees',[],label+' collect platform fee');c.feeWithdrawalTx=r.transactionHash;save();}
 const [replay]=await read(c.market,'HeadlineMarket','checkProof',[0n,proof]);
 if(replay)throw new Error('Replay accepted');
 if(paginated)c.totalBodySubmissionGas=String(BigInt(c.uploadGas)+BigInt(c.settlementGas));
 Object.assign(c,{windowBytes:Number(proof.bodyLength),calldataBytes,fitsCommonTxpoolLimit,complete:true,checks:{invalidExcerpt,invalidBody,subjectAloneRejected:true,bodyAccepted:true,yesPayout:true,winnerRedeemed:true,platformFeeCollected:true,replayRejected:true}});save();
 console.log(label+': lifecycle passed');
}
if(publicMode){
 for(const [domain,selector] of [['nytimes.com','scph20250409'],['e.newyorktimes.com','nyt-20250429'],['service.newyorktimes.com','nyt-20250429'],['e.nytimes.com','scph0126']]){
  const records=(await resolveTxt(selector+'._domainkey.'+domain)).map(x=>x.join(''));
  const txt=records.find(x=>/(?:^|;)\s*p=/.test(x));
  if(!txt)throw new Error('No DKIM key in DNS for '+domain);
  const key=dnsKeyToHex(/(?:^|;)\s*p=([^;]*)/.exec(txt)[1].trim());
  await register(domain,selector,key);
 }
 report.checks.observedNytDnsKeysRegistered=4;save();
}
const fixtureFile=join(dir,'public-body-fixture.eml');
if(!existsSync(fixtureFile))writeFileSync(fixtureFile,signEml('From: Body parser fixture <fixture@body-fixture.invalid>\r\nSubject: Synthetic daily newsletter\r\nDate: '+new Date().toUTCString()+'\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n<p>This is a test fixture, not newspaper reporting.</p><p>Foulkes won the Demo=\r\ncratic primary.</p>\r\n',{domain:'body-fixture.invalid',headers:['from','subject','date','content-type','content-transfer-encoding']}),'latin1');
await exercise({label:'Public signed fixture (not NYT)',raw:readFileSync(fixtureFile,'latin1'),key:devPublicKey(),pattern:'Foulkes won the Democratic primary',question:'E2E fixture: does the authenticated body report Foulkes winning the primary?'});
if(args.includes('--large-fixture')){
 const file=join(dir,'public-large-body-fixture.eml');
 if(!existsSync(file)){
  const padding=Array.from({length:2200},(_,i)=>'<p>Public synthetic padding '+i.toString().padStart(4,'0')+' '+createHash('sha256').update('body-fixture-'+i).digest('hex').slice(0,28)+'</p>').join('\r\n');
  const raw='From: Body parser fixture <fixture@body-fixture.invalid>\r\nSubject: Synthetic paginated newsletter\r\nDate: '+new Date().toUTCString()+'\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n'+padding+'\r\n<p>Demo result: Blue won.</p>\r\n';
  writeFileSync(file,signEml(raw,{domain:'body-fixture.invalid',headers:['from','subject','date','content-type','content-transfer-encoding']}),'latin1');
 }
 await exercise({label:'Public large paginated fixture (not NYT)',raw:readFileSync(file,'latin1'),key:devPublicKey(),pattern:'Demo result: Blue won[.]',question:'Synthetic pagination test: does the authenticated body say Blue won?',paginated:true});
}
if(args.includes('--real-email')){
 const raw=readFileSync(opt('real-email'),'latin1'),p=parseEml(raw);
 const dns=(await resolveTxt(p.selector+'._domainkey.'+p.domain)).map(x=>x.join('')).find(x=>/(?:^|;)\s*p=/.test(x));
 const key=dnsKeyToHex(/(?:^|;)\s*p=([^;]*)/.exec(dns)[1].trim());
 await exercise({label:opt('case-label','Private real NYT email — exact election headline'),raw,key,pattern:opt('pattern','Helena Foulkes Defeats Rhode Island Gov[.] Dan McKee in Democratic Primary'),question:'Private E2E: does this authenticated NYT body contain the stated evidence?',paginated:args.includes('--paginate')});
}
report.complete=true;report.completedAt=new Date().toISOString();save();
if(publicMode){
 const target=join(root,'contracts/deployments/sepolia.json');
 if(existsSync(target)&&!existsSync(join(dir,'prior-sepolia.json')))writeFileSync(join(dir,'prior-sepolia.json'),readFileSync(target));
 const manifest={chainId,bodyParsingVersion:1,...report.contracts,llmJudge:null,protocolFee:'10000000000000000',feeRecipient:account.address,deployBlock:report.transactions[0].block,deployedAt:report.completedAt,e2eReport:'docs/BODY-PARSING.md'};
 writeFileSync(target,JSON.stringify(manifest,null,2)+'\n');console.log('Verified Sepolia deployment metadata updated.');
}
console.log('Evidence report: '+output);
