// Read-only local-chain checks. This script never sends a transaction or email.
import {readFileSync,writeFileSync} from 'node:fs';
import {createPublicClient,http} from 'viem';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
const [inputPath,outputPath]=process.argv.slice(2);
if(!inputPath||!outputPath)throw Error('Usage: native-check.mjs <private-input.json> <private-output.json>');
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const input=JSON.parse(readFileSync(inputPath,'utf8'));
const override=process.env.MOP_NATIVE_STATE_OVERRIDE==='1';
const dep=override?{regexLib:'0x0000000000000000000000000000000000001000'}:
 JSON.parse(readFileSync(resolve(process.env.HOME,'.local/share/means-of-prediction/body-e2e/local.json'),'utf8')).contracts;
const artifactBytes=readFileSync(resolve(repo,'contracts/out/RegexLib.sol/RegexLib.json'));
const artifact=JSON.parse(artifactBytes.toString('utf8')),abi=artifact.abi;
const rpc=process.env.MOP_NATIVE_RPC||'http://127.0.0.1:8559';
if(new URL(rpc).hostname!=='127.0.0.1')throw Error('Only a loopback simulation RPC is allowed');
const client=createPublicClient({transport:http(rpc,{timeout:30000,retryCount:0})});
if(await client.getChainId()!==31337)throw Error('Only the local simulation chain is allowed');
const stateOverride=override?[{address:dep.regexLib,code:artifact.deployedBytecode.object}]:undefined;
if(!override&&!await client.getCode({address:dep.regexLib}))throw Error('RegexLib is not deployed locally');
const limit=16000000n,checks=[],witnesses=[];
// Positive and negative sentinels catch a missing/incorrect runtime before the
// experiment mistakes RPC or state-override failures for matcher limitations.
for(const [pattern,source,expected] of [['won','Team won',true],['won','Team lost',false]]){
 const actual=await client.readContract({address:dep.regexLib,abi,functionName:'matches',args:[pattern,source],gas:limit,stateOverride});
 if(actual!==expected)throw Error('Native matcher sentinel failed');
}
for(const pattern of [...new Set(input.patterns.filter(Boolean))]){
 const item={pattern,validateSucceeded:false};
 try {await client.readContract({address:dep.regexLib,abi,functionName:'validate',args:[pattern],gas:limit,stateOverride});item.validateSucceeded=true;}
 catch(e){item.error=(e.cause?.reason||e.shortMessage||'Native validation call failed').slice(0,250);}
 checks.push(item);
}
for(const {pattern,decodedSource} of input.witnesses){
 const item={pattern,decodedSource,matchesWithinGasLimit:false};
 try{
  item.matchesWithinGasLimit=await client.readContract({address:dep.regexLib,abi,functionName:'matches',args:[pattern,decodedSource],gas:limit,stateOverride});
  if(item.matchesWithinGasLimit)item.matcherGasEstimate=String(await client.estimateContractGas({address:dep.regexLib,abi,functionName:'matches',args:[pattern,decodedSource],gas:limit,stateOverride}));
 }catch(e){item.error=(e.cause?.reason||e.shortMessage||'Native matcher call failed').slice(0,250);}
 witnesses.push(item);
}
const result={chainId:31337,readOnly:true,library:dep.regexLib,gasLimit:String(limit),checks,witnesses,
 stateOverride:override,artifactSha256:createHash('sha256').update(artifactBytes).digest('hex'),
 sourceSha256:createHash('sha256').update(readFileSync(resolve(repo,'contracts/src/lib/RegexLib.sol'))).digest('hex'),
 note:'A failed validation call may indicate gas exhaustion rather than invalid syntax. Matcher-only gas excludes RSA, DKIM, body storage and settlement. No public-chain submission.'};
writeFileSync(outputPath,JSON.stringify(result,null,2),{mode:0o600});
console.log(JSON.stringify({patterns:checks.length,validationCallsPassed:checks.filter(x=>x.validateSucceeded).length,witnesses:witnesses.length,matcherCallsPassed:witnesses.filter(x=>x.matchesWithinGasLimit).length}));
