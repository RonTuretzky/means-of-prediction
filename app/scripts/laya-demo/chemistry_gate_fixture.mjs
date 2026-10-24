// Freeze original mail/request fixtures for evidence-gate tests. This does not
// certify inference, source truth or settlement. Paths are private CLI inputs.
import fs from 'node:fs';
import crypto from 'node:crypto';
import { encodeAbiParameters, parseAbiParameters, keccak256, stringToHex } from '../../node_modules/viem/_esm/index.js';

export const proofType = '(string domainName,bytes32 publicKeyHash,uint256 timestamp,string fromAddress,string subject,string bodyExcerpt,bytes32 emailNullifier,bytes header,bytes signature,bytes canonicalBody,uint256 bodyOffset,uint256 bodyLength)';
export const modelType = '(bytes32 weights,bytes32 tokenizer,bytes32 schema,bytes32 arithmetic,bytes32 preprocessing,bytes32 calibration,bytes32 runtime,uint32 maxTokens)';
export const requestType = `(uint32 version,uint256 chainId,address market,bytes32 rulesHash,bytes32 sourcePolicyHash,uint32 sourceIndex,bytes32 emailHash,bytes32 emailNullifier,bytes32 canonicalBodySha256,uint32 parserVersion,bytes32 parserPolicyHash,uint32 bodyOffset,uint32 bodyLength,bytes32 decodedBytesHash,bytes32 inputBytesHash,bytes32 tokenIdsHash,uint32 tokenCount,${modelType} model,uint32 thresholdPpm,uint8 decisionPolicy,uint64 expiresAt,uint256 nonce)`;
export const resultType = '(uint32 version,bytes32 requestKey,bytes32 executionRoot,uint32 aPpm,uint32 bPpm)';
export const sha = bytes => '0x' + crypto.createHash('sha256').update(bytes).digest('hex');
export const canonical = value => JSON.stringify(value, (_, v) => v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b))) : v);

if (process.argv[1]?.endsWith('/chemistry_gate_fixture.mjs')) {
  const [base, runtimePath, exportManifestPath, out] = process.argv.slice(2);
  if (!out) throw Error('Usage: node chemistry_gate_fixture.mjs PRIVATE_BASE RUNTIME_SOURCE EXPORT_MANIFEST OUTPUT');
  const frozenBytes = fs.readFileSync(`${base}/frozen.private.json`);
  if (sha(frozenBytes) !== '0x116a1e592fb349359a85c825c7c21b85fba8a23400d1963edc8fbb3a30ff000d') throw Error('freeze drift');
  const frozen = JSON.parse(frozenBytes);
  const rsaBytes = fs.readFileSync(`${base}/rsa-fixtures.private.json`);
  if (sha(rsaBytes) !== '0xb135f793cb9547d774114d308915d8cdd0c7b133c925667a69906ce060e434ab') throw Error('RSA fixture drift');
  const rsa = JSON.parse(rsaBytes);
  const manifest = JSON.parse(fs.readFileSync(frozen.modelManifestPath));
  const runtimeSource = fs.readFileSync(runtimePath);
  const exportBytes = fs.readFileSync(exportManifestPath);
  const arithmetic = JSON.parse(exportBytes);
  const ruleBundle = {
    version: 'chemistry-exact-rule-and-factual-predicates-v1', marketId: '5371179',
    question: frozen.question, factualA: frozen.factualA, factualB: frozen.factualB,
    fullRules: frozen.market.fullRules, originalFullRulesSHA256: frozen.market.fullRulesSha256,
    snapshotEndDate: frozen.market.endDate, endDateIsNotActualClosure: true,
  };
  const sourcePolicy = {
    version: 'chemistry-retrospective-complete-pair-two-origins-v1',
    marketId: '5371179', sourceGroups: ['reuters.com', 'apnews.com'], requiredOrigins: 2,
    primarySource: 'nobelprize.org', selectedRoute: 'credible-reporting consensus',
    pairReference: ['Henri Kagan', 'Kenso Soai'], person: 'Takuzo Aida', category: 'Chemistry', year: 2026,
    negativeAdmission: 'Affirmatively exhaustive admitted laureate set; absence from an incomplete snippet is insufficient.',
    sourceReasoning: frozen.expectationAndSourceLimit,
    twoReutersVersionsAreOneOrigin: true, googleDKIMDoesNotProvePublisherAuthorship: true,
    sourceAcceptance: 'Local research configuration only; original rules do not specify a numeric consensus threshold or Google-relay acceptance.',
    currentSignatureRequired: true, historicalReplayIsNotPresentAcceptance: true,
    independentHistoricalDNSOwnershipAndReceiptUnproven: true,
    modelSupport: 'Record both independent A/B flags. B-only from both origins required for local No settlement; abstention/conflict stays unresolved.',
  };
  const parserPolicy = {
    version: 'chemistry-frozen-article-prefix-v1', fullBodyVersion: 2, fullBodyCap: 196608, windowCap: 4096,
    inputBindingSHA256: frozen.sourcePins[Object.keys(frozen.sourcePins).find(x => x.endsWith('/chemistry_input_binding.py'))],
    preForwardFreezeSHA256: sha(frozenBytes), originalHeaderAndBodyRequired: true,
    scope: 'Only exact three frozen inputs admitted; no generic onchain article parser/tokenizer claim',
  };
  const h = value => keccak256(stringToHex(canonical(value)));
  const rulesHash = h(ruleBundle), sourcePolicyHash = h(sourcePolicy), parserPolicyHash = h(parserPolicy);
  const model = {
    weights: '0x' + frozen.profile.weightsSHA256,
    tokenizer: h(manifest.runtimeSmallFilesSha256), schema: h({questionOrder:['q','A','B'], stateOrder:['subject','body'], frozen: sha(frozenBytes)}),
    arithmetic: sha(exportBytes), preprocessing: h(parserPolicy), calibration: '0x' + frozen.profile.configSHA256,
    runtime: sha(runtimeSource), maxTokens: 960,
  };
  const proofs = rsa.rows.map(x => x.proof);
  const inputs = frozen.items.map(x => {
    const bytes = fs.readFileSync(x.inputPath);
    if (sha(bytes) !== '0x' + x.inputSHA256 || keccak256(bytes) !== x.gateHashes.inputHash) throw Error('exact input drift');
    return '0x' + bytes.toString('hex');
  });
  const ids = frozen.items.map(x => x.flatTokenIds);
  const requests = proofs.map((p, i) => ({
    version:1, chainId:31337, market:'0x000000000000000000000000000000000000c0Fe', rulesHash, sourcePolicyHash,
    sourceIndex:i === 1 ? 1 : 0, emailHash:keccak256(encodeAbiParameters(parseAbiParameters(proofType),[p])),
    emailNullifier:p.emailNullifier, canonicalBodySha256:'0x' + rsa.rows[i].canonicalBodySHA256,
    parserVersion:2, parserPolicyHash, bodyOffset:p.bodyOffset, bodyLength:p.bodyLength,
    decodedBytesHash:keccak256(stringToHex(p.bodyExcerpt)), inputBytesHash:keccak256(inputs[i]),
    tokenIdsHash:keccak256(encodeAbiParameters(parseAbiParameters('uint32[]'),[ids[i]])), tokenCount:ids[i].length,
    model, thresholdPpm:550000, decisionPolicy:3, expiresAt:Math.max(...rsa.expiresAtUnix)+86400*365, nonce:i+1,
  }));
  requests.forEach((r,i) => {if (r.tokenIdsHash!==frozen.items[i].gateHashes.tokenIdsHash) throw Error('token drift');});
  const requestKeys = requests.map(r => keccak256(encodeAbiParameters(parseAbiParameters(`bytes32,${requestType}`),[keccak256(stringToHex('LAYA_REQUEST_SCAFFOLD_V1')),r])));
  const abiHex = encodeAbiParameters(parseAbiParameters(`${proofType}[],bytes,bytes,bytes[],uint32[][],${requestType}[]`),[proofs,rsa.exponent,rsa.modulus,inputs,ids,requests]);
  const output = {
    schema:'chemistry-evidence-gate-fixture-v1', status:'Evidence authentication fixture only; this artifact does not itself certify model execution or settlement.',
    abiHex, requests, requestKeys, rulesHash, sourcePolicyHash, ruleBundle, sourcePolicy, parserPolicy,
    model, arithmeticVersion:arithmetic.version, runtimeSourceSHA256:sha(runtimeSource), integerExportManifestSHA256:sha(exportBytes),
    frozenInputSHA256:sha(frozenBytes), rsaFixtureSHA256:sha(rsaBytes),
    signedAtUnix:rsa.signedAtUnix, expiresAtUnix:rsa.expiresAtUnix,
    validationTimeUnix:rsa.validationTimeUnix, currentTimeUnix:rsa.currentTimeUnix, profileSHA256:rsa.profileSHA256,
    context:'31337 and placeholder consumer for local tests only; tests rebind only local consumer/chain context before gate construction.',
  };
  const text = JSON.stringify(output,null,2)+'\n';
  fs.writeFileSync(out,text,{flag:'wx',mode:0o600});
  fs.writeFileSync(out+'.runtime.py',runtimeSource,{flag:'wx',mode:0o600});
  fs.writeFileSync(out+'.export.json',exportBytes,{flag:'wx',mode:0o600});
  console.log(JSON.stringify({out,sha256:sha(text),rulesHash,sourcePolicyHash,requestKeys,profileSHA256:rsa.profileSHA256}));
}
