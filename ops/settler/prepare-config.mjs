import{readFileSync,writeFileSync,existsSync,mkdirSync}from'node:fs';
import{randomBytes}from'node:crypto';import{join}from'node:path';import{homedir}from'node:os';
import{generatePrivateKey,privateKeyToAccount}from'../../app/node_modules/viem/_esm/accounts/index.js';
process.umask(0o077);
const dir=join(homedir(),'.config/means-of-prediction/worker/service'),deployment=JSON.parse(readFileSync(new URL('../../contracts/deployments/sepolia.json',import.meta.url)));
for(const name of ['collector','signer'])mkdirSync(join(dir,name),{recursive:true,mode:0o700});
const keyPath=join(dir,'signer/private.key');if(!existsSync(keyPath))writeFileSync(keyPath,generatePrivateKey(),{mode:0o600});
const relayAddress=privateKeyToAccount(readFileSync(keyPath,'utf8').trim()).address;
for(const name of ['collector','signer']){const p=join(dir,name,'storage.key');if(!existsSync(p))writeFileSync(p,randomBytes(32).toString('hex'),{mode:0o600});}
const mailboxFile=join(dir,'collector/mailbox.json');if(!existsSync(mailboxFile))writeFileSync(mailboxFile,readFileSync(join(homedir(),'.config/means-of-prediction/mailbox.json')),{mode:0o600});
const scope={allowedDkimDomains:['nytimes.com','e.nytimes.com','e.newyorktimes.com','service.newyorktimes.com'],allowedFromDomains:['nytimes.com','newyorktimes.com'],discoveryFrom:['nytimes.com','newyorktimes.com']};
const base={chainId:11155111,factory:deployment.factory,emailBodyStore:deployment.emailBodyStore,relayAddress,maxGas:'16000000',maxGasPrice:'2000000000',dailyBudget:'100000000000000000',maxMarkets:10000,...scope};
const signer={...base,database:'/var/lib/mop-signer/signer.sqlite',privateKeyFile:'/etc/mop/signer/private.key',storageKeyFile:'/etc/mop/signer/storage.key',socketPath:'/run/mop-ipc/signer.sock'};
const collector={...base,deployment,rpcUrl:'https://ethereum-sepolia-rpc.publicnode.com',enabled:false,database:'/var/lib/mop-settler/worker.sqlite',storageKeyFile:'/etc/mop/collector/storage.key',mailboxFile:'/etc/mop/collector/mailbox.json',socketPath:'/run/mop-ipc/signer.sock',healthPort:4321,pollMs:60000,confirmations:2,maxMessageBytes:524288,uidBatch:5000,messagesPerPoll:25,minBalance:'100000000000000'};
for(const [name,c]of[['collector',collector],['signer',signer]]){const p=join(dir,name,'config.json');if(!existsSync(p))writeFileSync(p,JSON.stringify(c,null,2),{mode:0o600});}
console.log(JSON.stringify({configurationPresent:true,relayAddress,defaultMode:'dry-run; existing configurations preserved'}));
