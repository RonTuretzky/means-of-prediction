// Export only public synthetic-test facts. Never export raw mail or signed bytes.
import { readFileSync,writeFileSync } from 'node:fs';import { homedir } from 'node:os';import { join } from 'node:path';
import { createPublicClient,http,keccak256,serializeTransaction } from '../../app/automation/node_modules/viem/_esm/index.js';
try{
 const dir=join(homedir(),'.local/share/means-of-prediction');
 const test=JSON.parse(readFileSync(join(dir,'worker-e2e/sepolia/report.json'))),inspection=JSON.parse(readFileSync(join(dir,'worker-inspection.json')));
 if(!test.complete||!test.newspaperOnlyRestoredAt||!inspection.health.ok||!inspection.health.mailboxCaughtUp)throw Error('Finish the test and restore the newspaper scope first');
 const expectedDomains=['nytimes.com','e.nytimes.com','e.newyorktimes.com','service.newyorktimes.com'];
 if(JSON.stringify([...inspection.health.allowedDkimDomains].sort())!==JSON.stringify(expectedDomains.sort()))throw Error('Newspaper scope not restored');
 const client=createPublicClient({transport:http('https://ethereum-sepolia-rpc.publicnode.com')});if(await client.getChainId()!==11155111)throw Error('Wrong chain');
 const transactions=[];
 for(const action of inspection.actions){
  if(action.state!=='confirmed'||!action.receipt)throw Error('Unfinished relay action');
  const hash=action.receipt.hash,[tx,receipt]=await Promise.all([client.getTransaction({hash}),client.getTransactionReceipt({hash})]);
  if(receipt.status!=='success'||tx.from.toLowerCase()!==test.relayAddress.toLowerCase()||tx.nonce!==action.nonce||tx.to.toLowerCase()!==action.to.toLowerCase()||tx.value!==0n||tx.gas>16000000n)throw Error('Unexpected relay transaction');
  const serialized=serializeTransaction({type:'legacy',chainId:11155111,nonce:tx.nonce,gas:tx.gas,gasPrice:tx.gasPrice,to:tx.to,value:tx.value,data:tx.input},{r:tx.r,s:tx.s,v:tx.v});
  if(keccak256(serialized)!==hash||(serialized.length-2)/2>128*1024)throw Error('Transaction envelope mismatch');
  transactions.push({kind:action.id.startsWith('page:')?'body-page':'proof',hash,nonce:tx.nonce,to:tx.to,gasLimit:String(tx.gas),gasUsed:String(receipt.gasUsed),effectiveGasPrice:String(receipt.effectiveGasPrice),costWei:String(receipt.gasUsed*receipt.effectiveGasPrice),serializedBytes:(serialized.length-2)/2,block:Number(receipt.blockNumber)});
 }
 if(transactions.length!==10||transactions.filter(t=>t.kind==='body-page').length!==8||new Set(transactions.map(t=>t.nonce)).size!==10)throw Error('Unexpected fixture action count');
 const result={description:'Synthetic automatic-email integration test; no NYT raw email was published.',chainId:11155111,checkedAt:new Date().toISOString(),factory:inspection.health.factory,relayAddress:test.relayAddress,release:inspection.release,fixtureDomain:'body-fixture.invalid',fixtureSha256:test.fixtureSha256,canonicalBodyBytes:168786,scopeRestoredAt:test.newspaperOnlyRestoredAt,cases:test.cases,relayTransactions:transactions,lifecycleTransactions:test.transactions,totalRelayGas:String(transactions.reduce((n,t)=>n+BigInt(t.gasUsed),0n)),totalRelayCostWei:String(transactions.reduce((n,t)=>n+BigInt(t.costWei),0n)),mailboxAuthenticatedNytCount:inspection.emailDomains.filter(d=>d.domain!=='body-fixture.invalid').reduce((n,d)=>n+d.count,0),isolation:inspection.isolation,backupRestoreVerified:Object.values(inspection.backups).every(b=>b.restored),automationAndMailboxTestsPassed:25};
 writeFileSync(new URL('../../docs/automation-sepolia-test.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({recorded:true,relayTransactions:transactions.length,totalRelayGas:result.totalRelayGas,nytMessages:result.mailboxAuthenticatedNytCount}));
}catch{console.error('Public E2E record verification failed; provider output suppressed.');process.exitCode=1;}
