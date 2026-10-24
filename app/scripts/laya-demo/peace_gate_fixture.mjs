// Original BBC mail and frozen model-input binding, not a settlement certificate.
import fs from 'node:fs';
import { encodeAbiParameters, parseAbiParameters, keccak256, stringToHex } from '../../node_modules/viem/_esm/index.js';
import { proofType, modelType, requestType, sha, canonical } from './chemistry_gate_fixture.mjs';

const [base, runtimePath, exportPath, out] = process.argv.slice(2);
if (!out) throw Error('Usage: node peace_gate_fixture.mjs PRIVATE_BASE RUNTIME_SOURCE EXPORT_MANIFEST OUTPUT');
const read = p => fs.readFileSync(p);
const frozenBytes = read(`${base}/frozen.private.json`);
if (sha(frozenBytes) !== '0xb546ccf88a8d95b6f6a2183f249d60c0b7d764bd109235babae42cc19cf745d6') throw Error('Peace freeze drift');
const frozen = JSON.parse(frozenBytes);
const rsaBytes = read(`${base}/rsa-fixtures.private.json`);
if (sha(rsaBytes) !== '0x5078c0d4ce818a126435020e9615937a57eded7fa232a2fe547f8f609f307cc9') throw Error('Original RSA fixture drift');
const rsa = JSON.parse(rsaBytes);
const modelManifestBytes = read(frozen.modelManifestPath);
if (sha(modelManifestBytes) !== '0x'+frozen.modelManifestSHA256) throw Error('Model manifest drift');
const manifest = JSON.parse(modelManifestBytes);
const runtimeSource = read(runtimePath), exportBytes = read(exportPath);
if (sha(runtimeSource) !== '0xb06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766') throw Error('Runtime changed');
if (sha(exportBytes) !== '0xb863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d') throw Error('Arithmetic changed');
if (frozen.items.length !== 1 || frozen.items[0].sourceKey !== 'bbc' || rsa.rows.length !== 1) throw Error('BBC-only fixture');
const item = frozen.items[0], proof = rsa.rows[0].proof;
const ruleBundle = {
  version:'peace-bbc-exact-rule-and-factual-predicates-v1', marketId:'5371292',
  question:frozen.question, factualA:frozen.factualA, factualB:frozen.factualB,
  fullRules:frozen.market.fullRules, originalFullRulesSHA256:frozen.market.fullRulesSHA256,
  savedMetadata:frozen.market.savedMetadata, endDateIsNotActualClosure:true,
};
const sourcePolicy = {
  version:'peace-bbc-single-origin-observation-v1', marketId:'5371292',
  selectedOrigin:'bbc.com', primaryRequiredSource:'nobelprize.org',
  selectedRoute:'Potential contributor to credible-reporting consensus; one BBC observation alone is insufficient.',
  frozenSourcePolicy:frozen.sourcePolicy, originalMarketSourceAdmissionEstablished:false,
  googleDKIMDoesNotAuthenticatePublisherTruth:true,
  currentSignatureRequired:true, retrospectiveTimingAndHistoricalDNSOwnershipUnresolved:true,
  modelSupport:'Independent A/B flags; model support is not source admission or executed settlement.',
};
const parserPolicy = {
  version:'peace-bbc-frozen-article-prefix-v1', fullBodyVersion:2, fullBodyCap:196608, windowCap:4096,
  inputBindingSHA256:frozen.sourcePins[Object.keys(frozen.sourcePins).find(x=>x.endsWith('/peace_input_binding.py'))],
  preForwardFreezeSHA256:sha(frozenBytes), originalHeaderAndFullBodyRequired:true,
  scope:'Only the exact frozen BBC input admitted; no generic onchain article parser or tokenizer claim.',
};
const h = v => keccak256(stringToHex(canonical(v)));
const rulesHash=h(ruleBundle), sourcePolicyHash=h(sourcePolicy), parserPolicyHash=h(parserPolicy);
const model = {
  weights:'0x'+frozen.profile.weightsSHA256,
  tokenizer:h(manifest.runtimeSmallFilesSha256),
  schema:h({questionOrder:['q','A','B'],stateOrder:['subject','body'],frozen:sha(frozenBytes)}),
  arithmetic:sha(exportBytes), preprocessing:parserPolicyHash,
  calibration:'0x'+frozen.profile.configSHA256, runtime:sha(runtimeSource), maxTokens:960,
};
const inputBytes=read(item.inputPath), input='0x'+inputBytes.toString('hex'), ids=item.flatTokenIds;
if (sha(inputBytes)!=='0x'+item.inputSHA256 || keccak256(inputBytes)!==item.gateHashes.inputHash) throw Error('Input drift');
const request = {
  version:1, chainId:31337, market:'0x000000000000000000000000000000000000c0Fe',
  rulesHash,sourcePolicyHash,sourceIndex:0,
  emailHash:keccak256(encodeAbiParameters(parseAbiParameters(proofType),[proof])),
  emailNullifier:proof.emailNullifier,canonicalBodySha256:'0x'+rsa.rows[0].canonicalBodySHA256,
  parserVersion:2,parserPolicyHash,bodyOffset:proof.bodyOffset,bodyLength:proof.bodyLength,
  decodedBytesHash:keccak256(stringToHex(proof.bodyExcerpt)),inputBytesHash:keccak256(input),
  tokenIdsHash:keccak256(encodeAbiParameters(parseAbiParameters('uint32[]'),[ids])),tokenCount:ids.length,
  model,thresholdPpm:550000,decisionPolicy:3,
  // Keep request expiry separately testable. This does not extend the DKIM x= gate.
  expiresAt:rsa.rows[0].expiresAtUnix+86400*365,nonce:1,
};
if(request.tokenIdsHash!==item.gateHashes.tokenIdsHash)throw Error('Token drift');
const requestKey=keccak256(encodeAbiParameters(parseAbiParameters(`bytes32,${requestType}`),[keccak256(stringToHex('LAYA_REQUEST_SCAFFOLD_V1')),request]));
const abiHex=encodeAbiParameters(parseAbiParameters(`${proofType},bytes,bytes,bytes,uint32[],${requestType}`),[proof,rsa.exponent,rsa.modulus,input,ids,request]);
const output={
  schema:'peace-bbc-evidence-gate-fixture-v1',status:'Genuine full-email and exact-input observation fixture; no model certificate or original-market settlement claim.',
  abiHex,request,requestKey,rulesHash,sourcePolicyHash,parserPolicyHash,
  ruleBundle,sourcePolicy,parserPolicy,model,modelPinsHash:keccak256(encodeAbiParameters(parseAbiParameters(modelType),[model])),
  frozenInputSHA256:sha(frozenBytes),rsaFixtureSHA256:sha(rsaBytes),
  arithmeticVersion:JSON.parse(exportBytes).version,runtimeSourceSHA256:sha(runtimeSource),integerExportManifestSHA256:sha(exportBytes),
  signedAtUnix:rsa.signedAtUnix[0],expiresAtUnix:rsa.expiresAtUnix[0],
  validationTimeUnix:rsa.validationTimeUnix,currentTimeUnix:rsa.currentTimeUnix,profileSHA256:rsa.profileSHA256,
  currentDKIMValidAgainstSavedKey:rsa.rows[0].currentDKIMValid,
  context:'Local chain31337 with placeholder consumer; rebind only consumer before gate construction/signing. No live deployment.',
};
const text=JSON.stringify(output,null,2)+'\n';
fs.writeFileSync(out,text,{flag:'wx',mode:0o600});
console.log(JSON.stringify({out,sha256:sha(text),rulesHash,sourcePolicyHash,parserPolicyHash,modelPinsHash:output.modelPinsHash,requestKey}));
