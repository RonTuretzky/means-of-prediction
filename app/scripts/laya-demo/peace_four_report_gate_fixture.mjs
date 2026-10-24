// Exact four-report source policy and genuine full-email fixtures, not a model certificate.
import fs from 'node:fs';
import { encodeAbiParameters, parseAbiParameters, keccak256, stringToHex } from '../../node_modules/viem/_esm/index.js';
import { proofType, modelType, requestType, sha, canonical } from './chemistry_gate_fixture.mjs';

const [base, runtimePath, exportPath, expectedFreezeSHA, expectedRSASHA, out] = process.argv.slice(2);
if (!out) throw Error('Usage: PRIVATE_BASE RUNTIME EXPORT FREEZE_SHA RSA_SHA OUTPUT');
const read = p => fs.readFileSync(p);
const frozenBytes = read(`${base}/frozen.private.json`), rsaBytes = read(`${base}/rsa-fixtures.private.json`);
if (sha(frozenBytes) !== '0x'+expectedFreezeSHA || sha(rsaBytes) !== '0x'+expectedRSASHA) throw Error('Frozen artifact drift');
const frozen = JSON.parse(frozenBytes), rsa = JSON.parse(rsaBytes);
const policyBytes = read('/Users/wk/.local/share/means-of-prediction/peace-source-admission-20261021/source-policy-frozen.private.json');
const expectedPolicy = '464871658b2543c7cfd2fac61ecaf84ec32e437a06265dd12e648ea2750ea3a2';
if (sha(policyBytes) !== '0x'+expectedPolicy || frozen.sourcePolicySHA256 !== expectedPolicy || rsa.sourcePolicySHA256 !== expectedPolicy) throw Error('Source policy drift');
const sourcePolicy = JSON.parse(policyBytes);
if (JSON.stringify(frozen.items.map(x=>x.sourceKey)) !== JSON.stringify(sourcePolicy.sourceOrder) || rsa.rows.length !== 4) throw Error('Exact named set required');
const modelManifestBytes = read(frozen.modelManifestPath);
if (sha(modelManifestBytes) !== '0x'+frozen.modelManifestSHA256) throw Error('Model manifest drift');
const manifest = JSON.parse(modelManifestBytes), runtime = read(runtimePath), exported = read(exportPath);
if (sha(runtime) !== '0xb06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766' || sha(exported) !== '0xb863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d') throw Error('Model arithmetic drift');
const h = v => keccak256(stringToHex(canonical(v)));
const ruleBundle = {version:'peace-four-report-exact-rules-and-predicates-v1',marketId:'5371292',question:frozen.question,
  factualA:frozen.factualA,factualB:frozen.factualB,fullRules:frozen.market.fullRules,
  originalFullRulesSHA256:frozen.market.fullRulesSHA256,savedMetadata:frozen.market.savedMetadata,
  endDateIsNotActualClosure:true};
if (ruleBundle.originalFullRulesSHA256 !== 'f1ba951f9767de4eae4f2562b22bc4ad43db741fe3d30cecc5112a93eafece6d') throw Error('Original rule drift');
const parserPolicy = {version:'peace-four-report-exact-original-prefix-v1',fullBodyVersion:2,fullBodyCap:196608,windowCap:4096,
  preprocessingSourcePins:frozen.sourcePins,preForwardFreezeSHA256:sha(frozenBytes),originalHeaderAndFullBodyRequired:true,
  scope:'Exact reviewed BBC/CNN/ABC/RFI original windows and frozen input/token commitments. Offline extraction/tokenization, not generic Solidity HTML parsing.'};
const rulesHash=h(ruleBundle),sourcePolicyHash=h(sourcePolicy),parserPolicyHash=h(parserPolicy);
const model={weights:'0x'+frozen.profile.weightsSHA256,tokenizer:h(manifest.runtimeSmallFilesSha256),
  schema:h({questionOrder:['q','A','B'],stateOrder:['subject','body'],frozen:sha(frozenBytes)}),arithmetic:sha(exported),
  preprocessing:parserPolicyHash,calibration:'0x'+frozen.profile.configSHA256,runtime:sha(runtime),maxTokens:960};
const proofs=[], inputs=[], ids=[], requests=[], requestKeys=[];
for (let i=0;i<4;i++) {
  const item=frozen.items[i], row=rsa.rows[i], report=sourcePolicy.reports[i];
  if (item.sourceKey!==row.sourceKey || item.sourceKey!==report.sourceKey || item.rawSHA256!==report.rawSHA256 || row.rawSHA256!==report.rawSHA256 || !row.currentDKIMValid) throw Error('Unreviewed or expired report');
  const proof=row.proof,inputBytes=read(item.inputPath),input='0x'+inputBytes.toString('hex'),tokens=item.flatTokenIds;
  if (sha(inputBytes)!=='0x'+item.inputSHA256 || keccak256(inputBytes)!==item.gateHashes.inputHash) throw Error('Input drift');
  const request={version:1,chainId:31337,market:'0x000000000000000000000000000000000000c0Fe',rulesHash,sourcePolicyHash,sourceIndex:i,
    emailHash:keccak256(encodeAbiParameters(parseAbiParameters(proofType),[proof])),emailNullifier:proof.emailNullifier,
    canonicalBodySha256:'0x'+row.canonicalBodySHA256,parserVersion:2,parserPolicyHash,bodyOffset:proof.bodyOffset,bodyLength:proof.bodyLength,
    decodedBytesHash:keccak256(stringToHex(proof.bodyExcerpt)),inputBytesHash:keccak256(input),
    tokenIdsHash:keccak256(encodeAbiParameters(parseAbiParameters('uint32[]'),[tokens])),tokenCount:tokens.length,
    model,thresholdPpm:550000,decisionPolicy:3,expiresAt:row.expiresAtUnix+86400*365,nonce:i+1};
  // This request expiry does not replace or extend original DKIM x= enforcement.
  if (request.tokenIdsHash!==item.gateHashes.tokenIdsHash) throw Error('Token drift');
  requestKeys.push(keccak256(encodeAbiParameters(parseAbiParameters(`bytes32,${requestType}`),[keccak256(stringToHex('LAYA_REQUEST_SCAFFOLD_V1')),request])));
  proofs.push(proof); inputs.push(input); ids.push(tokens); requests.push(request);
}
const abiHex=encodeAbiParameters(parseAbiParameters(`${proofType}[],bytes,bytes,bytes[],uint32[][],${requestType}[]`),[proofs,rsa.exponent,rsa.modulus,inputs,ids,requests]);
const output={schema:'peace-four-report-genuine-evidence-fixture-v1',abiHex,requests,requestKeys,sourceOrder:sourcePolicy.sourceOrder,
  rulesHash,sourcePolicyHash,parserPolicyHash,ruleBundle,sourcePolicy,sourcePolicyFileSHA256:sha(policyBytes),parserPolicy,model,
  modelPinsHash:keccak256(encodeAbiParameters(parseAbiParameters(modelType),[model])),frozenInputSHA256:sha(frozenBytes),rsaFixtureSHA256:sha(rsaBytes),
  runtimeSourceSHA256:sha(runtime),integerExportManifestSHA256:sha(exported),arithmeticVersion:JSON.parse(exported).version,
  signedAtUnix:rsa.signedAtUnix,expiresAtUnix:rsa.expiresAtUnix,validationTimeUnix:rsa.validationTimeUnix,currentTimeUnix:rsa.currentTimeUnix,
  profileSHA256:rsa.profileSHA256,fullBodies:rsa.rows.map(r=>({sourceKey:r.sourceKey,rawSHA256:r.rawSHA256,canonicalHeaderSHA256:r.canonicalHeaderSHA256,canonicalBodySHA256:r.canonicalBodySHA256,canonicalBodyBytes:r.canonicalBodyBytes})),
  scope:'Local exact reviewed qualitative consensus fixture, pending real operator certificates and consumer tests. Rebind consumer before signing; preserve original BBC receipt separately.'};
const text=JSON.stringify(output,null,2)+'\n';fs.writeFileSync(out,text,{flag:'wx',mode:0o600});
console.log(JSON.stringify({out,sha256:sha(text),rulesHash,sourcePolicyHash,parserPolicyHash,modelPinsHash:output.modelPinsHash,requestKeys}));
