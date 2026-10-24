#!/usr/bin/env node
// Publishes exact calldata transport on the isolated local benchmark only.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeDeployData, encodeFunctionData, getContractAddress, keccak256 } from '../../node_modules/viem/_esm/index.js';
import { LocalRPC, artifact, loadFrozenPacket, sendRecordedTx, captureState, saveNew, json, sha,
  CONSUMER, SETUP, AVS, FINAL_TIMESTAMP } from './peace_anvil_baseline.mjs';

const OUT = '/Users/wk/.local/share/means-of-prediction/peace-anvil-comparison-20261021';
const assert = (x, why) => { if (!x) throw new Error(why); };
const eq = (a, b) => a.toLowerCase() === b.toLowerCase();
const strip = x => x.slice(2);
const hex = x => `0x${BigInt(x).toString(16)}`;

export async function runPacketSetup({ rpcUrl = 'http://127.0.0.1:19545', out = OUT, execute = false, gasPrice = 0n }) {
  assert(path.resolve(out) === OUT, 'Only the new private comparison directory permitted');
  const packet = loadFrozenPacket();
  const cacheArtifact = artifact('PeaceFinalizePacketCache');
  const relayArtifact = artifact('PeaceFinalizeGasKillerRelay');
  const expectedCache = getContractAddress({ from: SETUP, nonce: 15n });
  const expectedRelay = getContractAddress({ from: SETUP, nonce: 26n });
  const chunks = [];
  for (let byteOffset = 0; byteOffset < packet.packetLength; byteOffset += 24575) {
    chunks.push(`0x${strip(packet.finalizeCalldata).slice(byteOffset * 2, (byteOffset + 24575) * 2)}`);
  }
  assert(chunks.length === 9 && chunks.map(strip).join('') === strip(packet.finalizeCalldata), 'Exact shard split failed');
  const cacheData = encodeDeployData({ abi: cacheArtifact.abi, bytecode: cacheArtifact.bytecode.object,
    args: [packet.packetHash, BigInt(packet.packetLength), SETUP] });
  for (const chunk of chunks) encodeFunctionData({ abi: cacheArtifact.abi, functionName: 'appendChunk', args: [chunk] });
  const registry = getContractAddress({ from: SETUP, nonce: 2n });
  const relayData = encodeDeployData({ abi: relayArtifact.abi, bytecode: relayArtifact.bytecode.object,
    args: [CONSUMER, expectedCache, registry, AVS] });
  const plan = { schema: 'peace-local-anvil-packet-setup-v1', execute, rpcUrl,
    runnerSHA256: sha(fs.readFileSync(fileURLToPath(import.meta.url))),
    baselineRunnerSHA256: sha(fs.readFileSync(new URL('./peace_anvil_baseline.mjs', import.meta.url))),
    consumer: CONSUMER, registry, setup: SETUP, avs: AVS, expectedCache, expectedRelay,
    packetHash: packet.packetHash, packetLength: packet.packetLength,
    chunks: chunks.map((chunk, i) => ({ i, bytes: strip(chunk).length / 2, hash: keccak256(chunk) })),
    artifacts: { cache: { path: cacheArtifact.artifactPath, sha256: cacheArtifact.artifactSHA256 },
      relay: { path: relayArtifact.artifactPath, sha256: relayArtifact.artifactSHA256 } },
    timestamps: 'Each setup transaction at1792546000+nextBlockNumber. All three final matched branches at1792546544.',
    note: 'Staged immutable calldata transport; every relay path still executes unchanged full consumer.finalize. Publication gas is separate.' };
  fs.mkdirSync(out, { recursive: true, mode: 0o700 });
  saveNew(out, execute ? 'packet-setup-plan.private.json' : 'packet-setup-offline-plan.private.json', plan);
  if (!execute) return plan;
  const baselineRaw = fs.readFileSync(path.join(out, 'baseline-handoff.private.json'));
  const baseline = JSON.parse(baselineRaw);
  assert(eq(baseline.packetHash, packet.packetHash) && baseline.packetLength === packet.packetLength
    && eq(baseline.addresses.consumer, CONSUMER) && eq(baseline.addresses.registry, registry), 'Baseline handoff mismatch');
  const rpc = new LocalRPC(rpcUrl);
  assert(BigInt(await rpc.call('eth_chainId')) === 31337n && /anvil/i.test(await rpc.call('web3_clientVersion')), 'Local chain guard');
  const info = await rpc.call('anvil_nodeInfo');
  assert(info.forkConfig?.forkUrl === null && info.forkConfig?.forkBlockNumber === null && info.hardFork === 'Cancun', 'Only non-fork Cancun permitted');
  const blockBefore = await rpc.call('eth_getBlockByNumber', ['latest', false]);
  assert(BigInt(blockBefore.number) === 117n && BigInt(blockBefore.timestamp) === 1792546117n
    && blockBefore.hash === baseline.preBlock.hash, 'Expected restored original pre-finalization block117');
  assert(BigInt(await rpc.call('eth_getTransactionCount', [SETUP, 'latest'])) === 15n, 'Unexpected setup nonce');
  for (const entry of Object.values(baseline.code)) {
    assert(eq(keccak256(await rpc.call('eth_getCode', [entry.address, 'latest'])), entry.keccak256), 'Baseline dependency code changed');
  }
  const stateBefore = await captureState(rpc, packet, baseline.addresses.gate);
  assert(json(stateBefore) === json(baseline.preState), 'Baseline contract state changed');
  const receipts = [];
  const send = async (label, tx) => {
    const timestamp = 1792546000 + Number(BigInt(await rpc.call('eth_blockNumber'))) + 1;
    const receipt = await sendRecordedTx(rpc, out, label, tx, timestamp, gasPrice);
    receipts.push(receipt); return receipt;
  };
  const cache = (await send('packet-cache-deploy', { from: SETUP, data: cacheData })).contractAddress;
  assert(eq(cache, expectedCache), 'Cache CREATE mismatch');
  for (let i = 0; i < chunks.length; i++) {
    await send(`packet-cache-chunk-${i}`, { from: SETUP, to: cache,
      data: encodeFunctionData({ abi: cacheArtifact.abi, functionName: 'appendChunk', args: [chunks[i]] }) });
  }
  await send('packet-cache-seal', { from: SETUP, to: cache,
    data: encodeFunctionData({ abi: cacheArtifact.abi, functionName: 'seal', args: [] }) });
  assert(await rpc.read(cache, cacheArtifact.abi, 'isSealed'), 'Cache unsealed');
  assert((await rpc.read(cache, cacheArtifact.abi, 'read')) === packet.finalizeCalldata, 'Published packet differs');
  const relay = (await send('packet-relay-deploy', { from: SETUP, data: relayData })).contractAddress;
  assert(eq(relay, expectedRelay), 'Relay CREATE mismatch');
  const stateAfter = await captureState(rpc, packet, baseline.addresses.gate);
  assert(json(stateAfter) === json(stateBefore), 'Packet publication changed original consumer/gate state');
  const anchor = await rpc.call('eth_getBlockByNumber', ['latest', false]);
  assert(Number(BigInt(anchor.timestamp)) < FINAL_TIMESTAMP, 'No room for frozen finalization clock');
  const code = {};
  for (const [name, address] of [['cache', cache], ['relay', relay]]) {
    const runtime = await rpc.call('eth_getCode', [address, 'latest']);
    code[name] = { address, bytes: strip(runtime).length / 2, keccak256: keccak256(runtime) };
  }
  const shards = [];
  for (let i = 0; i < chunks.length; i++) {
    const address = await rpc.read(cache, cacheArtifact.abi, 'shards', [BigInt(i)]);
    const runtime = await rpc.call('eth_getCode', [address, 'latest']);
    assert(runtime === `0x00${strip(chunks[i])}`, 'Shard runtime content mismatch');
    shards.push({ i, address, keccak256: keccak256(runtime), bytes: strip(runtime).length / 2 });
  }
  const get = name => rpc.read(relay, relayArtifact.abi, name);
  const context = { contextDomain: await get('contextDomain'), codeContextHash: await get('codeContextHash'),
    preStateHash: await get('stateCommitment'), preOutcomeHash: await get('outcomeCommitment'),
    nonce: await get('nonce'), sdkTransitionCount: await get('stateTransitionCount'),
    notAfter: await get('lastValidTimestamp'), executionTimestamp: FINAL_TIMESTAMP,
    callbackSelector: '0x699880b0', directExecuteSelector: '0x731bca58', sdkSelector: '0x82b35a01' };
  const snapshot = await rpc.call('evm_snapshot');
  saveNew(out, 'comparison-anchor-block.private.json', anchor);
  saveNew(out, 'comparison-anchor-anvil-dump.private.json', { state: await rpc.call('anvil_dumpState') });
  const handoff = { ...plan, baselineHandoffSHA256: sha(baselineRaw), receipts,
    addresses: { ...baseline.addresses, cache, relay }, code, shards, context, anchor, snapshot,
    originalState: stateAfter, nextSetupNonce: BigInt(await rpc.call('eth_getTransactionCount', [SETUP, 'latest'])),
    sumPublicationGas: receipts.reduce((sum, r) => sum + r.gasUsed, 0n),
    matchedBranches: ['consumer.finalize(exact original calldata)', 'relay.directExecute()', 'relay.verifyAndUpdate(actual actor certificate)'],
    instructions: 'Use snapshot at this exact anchor; set next timestamp1792546544 for EACH branch and identical SETUP sender. Revert/recreate snapshot between branches. Capture target/gate states, all nullifiers, real receipts and gas. Original consumer direct branch leaves relaynonce0; relay branches increment relaynonce1, but target/gate terminal outcomes must match.' };
  saveNew(out, 'packet-setup-handoff.private.json', handoff);
  return handoff;
}
async function main() {
  const args = process.argv.slice(2), options = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--rpc') options.rpcUrl = args[++i];
    else if (args[i] === '--out') options.out = args[++i];
    else if (args[i] === '--execute') options.execute = true;
    else if (args[i] === '--gas-price-wei') options.gasPrice = BigInt(args[++i]);
    else throw new Error(`Unknown option ${args[i]}`);
  }
  const result = await runPacketSetup(options);
  console.log(json({ executed: Boolean(options.execute), expectedCache: result.expectedCache,
    expectedRelay: result.expectedRelay, snapshot: result.snapshot, context: result.context,
    sumPublicationGas: result.sumPublicationGas }));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.stack); process.exitCode = 1; });
}
