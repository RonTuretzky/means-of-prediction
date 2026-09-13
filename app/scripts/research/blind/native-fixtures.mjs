// Native positive/negative fixture evaluation. Local eth_call only; no sends.
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import {createPublicClient,http} from 'viem';

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
export function summarize(rows){
  const positives=rows.filter(r=>r.expected!=='neither'),negatives=rows.filter(r=>r.expected==='neither');
  return {fixtures:rows.length,positivePasses:positives.filter(r=>r.passed).length,positiveTotal:positives.length,
    negativeFalsePositives:negatives.filter(r=>r.falsePositive).length,negativeTotal:negatives.length,
    unscorablePositives:positives.filter(r=>!r.scorable).length,unscorableNegatives:negatives.filter(r=>!r.scorable).length};
}
export function classify(expected,calls){
  const scorable=calls.every(c=>typeof c.matched==='boolean');
  const target=expected==='A'?[true,false]:expected==='B'?[false,true]:[false,false];
  return {scorable,passed:scorable&&calls.every((c,i)=>c.matched===target[i]),
    falsePositive:expected==='neither'&&calls.some(c=>c.matched===true)};
}
async function main(){
  const [inputPath,outputPath,artifactPath]=process.argv.slice(2);
  if(!inputPath||!outputPath||!artifactPath)throw Error('Expected input, output, sealed artifact paths');
  const input=JSON.parse(readFileSync(inputPath)),selectionBytes=readFileSync(input.selectionPath);
  if(sha(selectionBytes)!==input.selectionSha256)throw Error('Selection changed');
  const selection=JSON.parse(selectionBytes),artifactBytes=readFileSync(artifactPath);
  if(selection.sourceHashes[artifactPath]!==sha(artifactBytes))throw Error('Unsealed native artifact');
  const freezeBytes=readFileSync(input.freezePath);
  if(sha(freezeBytes)!==input.freezeSha256)throw Error('Model freeze changed');
  if(sha(readFileSync(input.fixturesPath))!==input.fixturesSha256)throw Error('Fixtures changed');
  const root=dirname(input.freezePath),freeze=JSON.parse(freezeBytes),fixtures=JSON.parse(readFileSync(input.fixturesPath)),records=new Map();
  const sealBytes=readFileSync(resolve(root,'evaluation-fixture-seal.json'));
  if(sha(sealBytes)!==selection.artifactHashes['evaluation-fixture-seal.json']||JSON.parse(sealBytes).sha256!==input.fixturesSha256)throw Error('Fixtures differ from pretraining seal');
  if(!selection.challengeMethods.includes(input.method))throw Error('Unselected method');
  const expectedKeys=new Set(Object.entries(fixtures).flatMap(([mid,fs])=>[1,2].flatMap(trial=>fs.map((_,i)=>`${mid}:${trial}:${i}`))));
  const seenKeys=new Set();
  for(const row of input.rows){
    const key=`${row.marketId}:${row.trial}:${row.fixtureIndex}`;
    if(!expectedKeys.has(key)||seenKeys.has(key))throw Error('Unexpected or duplicate native fixture');
    seenKeys.add(key);
    const path=row.candidateRelativePath;
    if(!path.startsWith('methods/'+input.method+'/holdout/')||!freeze.files[path])throw Error('Unfrozen candidate');
    if(!records.has(path)){
      const bytes=readFileSync(resolve(root,path));if(sha(bytes)!==freeze.files[path])throw Error('Frozen candidate changed');
      records.set(path,JSON.parse(bytes));
    }
    const rec=records.get(path),out=rec.status==='completed'?rec.output:null;
    const patterns=['outcomeARegex','outcomeBRegex'].map(k=>out?.[k]??null);
    if(rec.marketId!==row.marketId||rec.trial!==row.trial||JSON.stringify(patterns)!==JSON.stringify(row.patterns))throw Error('Native input differs from frozen candidate');
    const f=fixtures[row.marketId]?.[row.fixtureIndex];
    if(!f||f.name!==row.name||f.html!==row.html||f.expected!==row.expected)throw Error('Native fixture differs from sealed gold');
  }
  if(seenKeys.size!==expectedKeys.size)throw Error('Incomplete native fixture coverage');
  const artifact=JSON.parse(artifactBytes),address='0x0000000000000000000000000000000000001000';
  const client=createPublicClient({transport:http('http://127.0.0.1:18559',{timeout:30000,retryCount:0})});
  if(await client.getChainId()!==31337)throw Error('Only local simulation allowed');
  const stateOverride=[{address,code:artifact.deployedBytecode.object}],gas=16000000n;
  for(const [source,expected] of [['Team won',true],['Team lost',false]]){
    if(await client.readContract({address,abi:artifact.abi,functionName:'matches',args:['won',source],gas,stateOverride})!==expected)throw Error('Native sentinel failed');
  }
  const rows=[];
  for(const r of input.rows){
    const calls=await Promise.all(r.patterns.map(async pattern=>{
      if(typeof pattern!=='string'||!pattern)return {error:'Missing pattern'};
      try{return {matched:await client.readContract({address,abi:artifact.abi,functionName:'matches',args:[pattern,r.html],gas,stateOverride})};}
      catch(e){return {error:(e.cause?.reason||e.shortMessage||'Native call failed').slice(0,250)};}
    }));
    rows.push({marketId:r.marketId,trial:r.trial,name:r.name,expected:r.expected,calls,...classify(r.expected,calls)});
  }
  const result={method:input.method,readOnly:true,chainId:31337,gasPerPatternCall:String(gas),artifactPath,artifactSha256:sha(artifactBytes),
    inputSha256:sha(readFileSync(inputPath)),summary:summarize(rows),rows,
    limitation:'Each A/B call has its own16M budget. This is not a combined transaction budget or DKIM/body-storage/settlement end-to-end test.'};
  writeFileSync(outputPath,JSON.stringify(result,null,2),{mode:0o600});console.log(JSON.stringify(result.summary));
}
if(process.argv[1]===fileURLToPath(import.meta.url))await main();
