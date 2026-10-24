#!/usr/bin/env node
// Local synthetic historical replay. No credentials, signing, or external RPC.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeFunctionData, encodeAbiParameters, parseAbiParameters, sha256 } from '../../node_modules/viem/_esm/index.js';
import { LocalRPC, loadFrozenPacket, sendRecordedTx, captureState, saveNew, artifact, json, sha, CONSUMER, SETUP, FINAL_TIMESTAMP } from './peace_anvil_baseline.mjs';

const BASE = '/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021';
const assert = (x, m) => { if (!x) throw new Error(m); };
const eq = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
const read = p => JSON.parse(fs.readFileSync(p, 'utf8'));
const args = process.argv.slice(2);
const value = name => { const i = args.indexOf(name); assert(i >= 0 && args[i + 1], `Missing ${name}`); return args[i + 1]; };
const fixturePath = path.resolve(value('--fixture'));
assert(fixturePath.startsWith(`${BASE}/gaskiller-relay-local/`), 'Use actual new local actor fixture only');
const fixture = read(fixturePath);
const handoff = read(`${BASE}/packet-setup-handoff.private.json`);
const baseline = read(`${BASE}/baseline-handoff.private.json`);
const packet = loadFrozenPacket();
const relay = artifact('PeaceFinalizeGasKillerRelay');
const rpc = new LocalRPC('http://127.0.0.1:19545');
const relayAddress = handoff.addresses.relay;
const receipt = fixture.receipts?.[0] ?? fixture.receipt;
const cert = fixture.certificates?.[0] ?? fixture.certificate;
assert(receipt && cert, 'One actual typed receipt and certificate required');
assert(!fixture.receipts || fixture.receipts.length === 1, 'Exactly one receipt');
assert(!fixture.certificates || fixture.certificates.length === 1, 'Exactly one certificate');
assert(receipt.version === 1 && BigInt(receipt.chainId) === 31337n, 'Receipt version/chain');
assert(eq(receipt.relay, relayAddress) && eq(receipt.consumer, CONSUMER), 'Receipt targets');
for (const k of ['contextDomain', 'codeContextHash', 'preStateHash']) assert(eq(receipt[k], handoff.context[k]), `Receipt ${k}`);
assert(eq(receipt.packetHash, packet.packetHash) && BigInt(receipt.nonce) === 0n, 'Receipt packet/nonce');
assert(BigInt(receipt.anchorBlockNumber) === BigInt(handoff.anchor.number) && eq(receipt.anchorBlockHash, handoff.anchor.hash), 'Signed anchor');
assert(BigInt(receipt.executionTimestamp) === BigInt(handoff.anchor.timestamp), 'Actual simulation timestamp must equal anchor');
assert(BigInt(receipt.notAfter) === BigInt(handoff.context.notAfter), 'Frozen expiry');
assert(BigInt(cert.transitionIndex) === 0n && Number(cert.refBlock) === 129 && cert.nonSigners.length === 0, 'Actual certificate shape');
assert(eq(cert.targetFunction, handoff.context.callbackSelector), 'Certified typed callback selector');
const localDigest = sha256(encodeAbiParameters(parseAbiParameters('uint256,address,bytes4,bytes'), [0n, relayAddress, cert.targetFunction, cert.payload]));
assert(eq(localDigest, cert.digest), 'Certificate digest encoding');

const current = await rpc.call('eth_getBlockByNumber', ['latest', false]);
const info = await rpc.call('anvil_nodeInfo');
assert(info.forkConfig?.forkUrl == null && info.hardFork === 'Cancun' && Number(info.environment.chainId) === 31337, 'Synthetic local root only');
assert(eq(current.hash, handoff.anchor.hash), 'Common anchor changed');
assert(eq(await rpc.read(relayAddress, relay.abi, 'receiptPayload', [receipt]), cert.payload), 'Actual payload must be exact typed self-CALL');
assert(eq(await rpc.read(relayAddress, relay.abi, 'receiptDigest', [0n, receipt]), cert.digest), 'Actual onchain digest');
assert(eq(await rpc.read(relayAddress, relay.abi, 'stateCommitment'), receipt.preStateHash), 'Current exact prestate');
assert(json(await captureState(rpc, packet, handoff.addresses.gate)) === json(handoff.originalState), 'Original state differs');
assert(BigInt(await rpc.call('eth_getTransactionCount', [SETUP, 'latest'])) === BigInt(handoff.nextSetupNonce), 'Sender nonce differs');
saveNew(BASE, 'matched-comparison-plan.private.json', {
  recordedBeforeExecution: new Date().toISOString(), runnerSHA256: sha(fs.readFileSync(fileURLToPath(import.meta.url))),
  fixturePath, fixtureSHA256: sha(fs.readFileSync(fixturePath)), handoffSHA256: sha(fs.readFileSync(`${BASE}/packet-setup-handoff.private.json`)),
  commonAnchor: handoff.anchor.hash, block: 130, timestamp: FINAL_TIMESTAMP, sender: SETUP,
  senderNonce: handoff.nextSetupNonce, historicalSynthetic: true, receipt, certificateDigest: cert.digest,
  accounting: 'Whole transaction receipts; common setup and cache publication separate. Certified prestate reads affect EVM warmth, so route delta is not pure signature cost.',
});

const certArgs = [cert.digest, Number(cert.refBlock), cert.payload, BigInt(cert.transitionIndex), cert.targetFunction, BigInt(cert.s), cert.Raddr, cert.nonSigners];
const routes = [
  ['uncached-direct', CONSUMER, packet.finalizeCalldata],
  ['cached-direct', relayAddress, encodeFunctionData({ abi: relay.abi, functionName: 'directExecute' })],
  ['gaskiller-certified', relayAddress, encodeFunctionData({ abi: relay.abi, functionName: 'verifyAndUpdate', args: certArgs })],
];
const results = [];
let snapshot = await rpc.call('evm_snapshot');
for (let i = 0; i < routes.length; i++) {
  const [name, to, data] = routes[i];
  const preBlock = await rpc.call('eth_getBlockByNumber', ['latest', false]);
  assert(eq(preBlock.hash, handoff.anchor.hash), `${name}: different starting head`);
  assert(json(await captureState(rpc, packet, handoff.addresses.gate)) === json(handoff.originalState), `${name}: different target prestate`);
  assert(eq(await rpc.read(relayAddress, relay.abi, 'stateCommitment'), receipt.preStateHash), `${name}: different relay prestate`);
  assert(BigInt(await rpc.call('eth_getTransactionCount', [SETUP, 'latest'])) === BigInt(handoff.nextSetupNonce), `${name}: different sender nonce`);
  const tx = await sendRecordedTx(rpc, BASE, `matched-${name}`, { from: SETUP, to, data }, FINAL_TIMESTAMP);
  const state = await captureState(rpc, packet, handoff.addresses.gate);
  const outcome = await rpc.read(relayAddress, relay.abi, 'outcomeCommitment');
  const relayNonce = await rpc.read(relayAddress, relay.abi, 'nonce');
  const relayTransitionCount = await rpc.read(relayAddress, relay.abi, 'stateTransitionCount');
  assert(Number(state.decision) === 1 && state.consumedSourceMask === 15, `${name}: not Yes/all sources`);
  assert([...state.consumedRequests, ...state.consumedEmails].every(Boolean), `${name}: missing nullifier`);
  assert(eq(outcome, receipt.outcomeHash), `${name}: outcome differs from independently certified result`);
  assert(BigInt(relayNonce) === (i === 0 ? 0n : 1n), `${name}: relay nonce`);
  assert(BigInt(relayTransitionCount) === (i === 2 ? 1n : 0n), `${name}: SDK transition count`);
  if (i > 0) assert(json(state) === json(results[0].state), `${name}: target/gate final state differs`);
  const row = { name, preBlockHash: preBlock.hash, transaction: tx, calldataBytes: (data.length - 2) / 2, state, outcome, relayNonce, relayTransitionCount };
  saveNew(BASE, `matched-${name}-outcome.private.json`, row);
  results.push(row);
  if (i < routes.length - 1) {
    assert(await rpc.call('evm_revert', [snapshot]), `${name}: revert failed`);
    snapshot = await rpc.call('evm_snapshot');
  }
}
saveNew(BASE, 'matched-final-state-dump.private.json', { state: await rpc.call('anvil_dumpState') });
const costs = read(`${BASE}/cost-components.private.json`);
const direct = results[0].transaction.gasUsed, cached = results[1].transaction.gasUsed, certified = results[2].transaction.gasUsed;
const report = {
  status: 'all-three-actual-transactions-succeeded', results, sameTargetAndGateState: true,
  sameOutcomeCommitment: receipt.outcomeHash, costs,
  deltas: { cachedMinusUncached: cached - direct, certifiedMinusCached: certified - cached, certifiedMinusUncached: certified - direct },
  totalsIncludingCommonSetup: Object.fromEntries(results.map((r, i) => [r.name, r.transaction.gasUsed + BigInt(costs.commonPrerequisiteTotalGas) + (i === 0 ? 0n : BigInt(costs.cacheAndRelaySetupGas))])),
  priorCallerDeltaGas: 123466543, initialProvisionalReceiptGas: baseline.initialDirect.gasUsed,
  limits: ['Experimental raised local block and code/initcode limits; no production deployability claim.',
    'All three paths reuse genuine certified model decisions; no EVM model inference comparison.',
    'Cache saves transport only; certified callback reexecutes complete original authentication.',
    'Whole-route gas deltas include different pre-read warmness and wrapper work, not isolated signature gas.',
    'Local public test committee, synthetic funds, retrospective fixture clock. No Polymarket or public-chain transaction.',
    'Inherited SDK quorum trust and original source/key/chronology limitations remain.'],
};
saveNew(BASE, 'matched-comparison-results.private.json', report);
console.log(json({ status: report.status, gasUsed: Object.fromEntries(results.map(x => [x.name, x.transaction.gasUsed])), deltas: report.deltas, totals: report.totalsIncludingCommonSetup }));
