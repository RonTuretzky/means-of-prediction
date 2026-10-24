#!/usr/bin/env node
// Local historical replay only. No signing keys, fork RPC, or public-chain writes.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import {
  decodeAbiParameters, decodeFunctionResult, encodeAbiParameters,
  encodeDeployData, encodeFunctionData, getContractAddress, keccak256,
  parseAbiParameters, sha256, stringToHex,
} from '../../node_modules/viem/_esm/index.js';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const PRIVATE = '/Users/wk/.local/share/means-of-prediction';
const FIXTURE_BASE = `${PRIVATE}/peace-four-report-demo-20261021`;
export const CONSUMER = '0xBE48387535e1dE07361eF51B57aaa5758c445D79';
export const SETUP = '0x00000000000000000000000000000000000a11ce';
export const DEPLOYER = '0x0000000000000000000000000000000000c0ffee';
export const AVS = '0x0000000000000000000000000000000000000a55';
export const FINAL_TIMESTAMP = 1792546544;
const GENESIS_TIMESTAMP = 1792546000;
const GAS_LIMIT = 900000000n;
export const json = value => JSON.stringify(value, (_, x) => typeof x === 'bigint' ? x.toString() : x, 2) + '\n';
export const sha = raw => crypto.createHash('sha256').update(raw).digest('hex');
const invariant = (x, message) => { if (!x) throw new Error(message); };
const hex = n => `0x${BigInt(n).toString(16)}`;
const eqHex = (a, b) => a.toLowerCase() === b.toLowerCase();
export function saveNew(out, name, value) {
  invariant(!name.includes('/') && !name.includes('..'), 'Output basename required');
  const target = path.join(out, name);
  fs.writeFileSync(target, typeof value === 'string' ? value : json(value), { flag: 'wx', mode: 0o600 });
  return target;
}
export function artifact(name) {
  const target = path.join(REPO, 'contracts/out', `${name}.sol`, `${name}.json`);
  const raw = fs.readFileSync(target);
  return { ...JSON.parse(raw), artifactPath: target, artifactSHA256: sha(raw) };
}
const fn = (a, name) => a.abi.find(x => x.type === 'function' && x.name === name);
const tupleArray = p => ({ ...p, type: 'tuple[]' });
function pinnedJSON(target, expected) {
  const raw = fs.readFileSync(target);
  invariant(sha(raw) === expected, `Fixture SHA mismatch: ${target}`);
  return JSON.parse(raw);
}

export function loadFrozenPacket() {
  const gatePath = `${FIXTURE_BASE}/gate-fixture.private.json`;
  const actorPath = `${FIXTURE_BASE}/gaskiller-local/actor-fixture.private.json`;
  const gate = pinnedJSON(gatePath, '0c409ee7a6c16f4629f42101d0c9aa99135b7ce4ec7176e7d3a816ac28d33d7b');
  const actor = pinnedJSON(actorPath, '6fed0a096e6f04454d38e4fa7a29f3966e5969ca03eee192fe877b253a723a29');
  const consumer = artifact('PeaceFourReportSchnorrConsumer');
  const sourcePath = path.join(REPO, 'contracts/src/judge/PeaceFourReportSchnorrConsumer.sol');
  invariant(sha(fs.readFileSync(sourcePath)) === '44cb38c21268d5ccccc75e36c05a524bc9ad0e5abf28ac9495264e18473d42d8', 'Original consumer source changed');
  const observation = fn(consumer, 'recordAuthenticatedObservation');
  const requestType = observation.inputs[0];
  const proofType = observation.inputs[1];
  const gateTypes = [tupleArray(proofType), { type: 'bytes' }, { type: 'bytes' },
    { type: 'bytes[]' }, { type: 'uint32[][]' }, tupleArray(requestType)];
  const [proofs, exponent, modulus, inputs, ids, decodedRequests] = decodeAbiParameters(gateTypes, gate.abiHex);
  const receiptType = fn(consumer, 'acceptCertifiedReport').inputs[0];
  const operatorType = parseAbiParameters('(uint256 x,uint256 y,uint256 weight,uint256 popS,address popR)[]')[0];
  const certificateType = parseAbiParameters('(bytes32 digest,uint32 refBlock,bytes payload,uint256 transitionIndex,bytes4 targetFunction,uint256 s,address Raddr,address[] nonSigners)[]')[0];
  const [operators, receipts, certificates] = decodeAbiParameters([operatorType, tupleArray(receiptType), certificateType], actor.abiHex);
  invariant(Number(gate.currentTimeUnix) === FINAL_TIMESTAMP, 'Unexpected historical fixture clock');
  invariant(operators.length === 3 && receipts.length === 4 && proofs.length === 4 && certificates.length === 4, 'Frozen tuple lengths');
  const requests = decodedRequests.map(x => ({ ...x, market: CONSUMER }));
  const domain = keccak256(stringToHex('LAYA_REQUEST_SCAFFOLD_V1'));
  const requestKeys = requests.map(x => keccak256(encodeAbiParameters([{ type: 'bytes32' }, requestType], [domain, x])));
  for (let i = 0; i < 4; i++) {
    const r = receipts[i], c = certificates[i];
    invariant(eqHex(r.consumer, CONSUMER) && r.version === 3 && r.chainId === 31337n && r.marketId === 5371292n, 'Receipt context mismatch');
    invariant(eqHex(r.requestKey, requestKeys[i]), 'Frozen request key mismatch');
    invariant(eqHex(r.inputHash, keccak256(inputs[i])), 'Input bytes hash mismatch');
    invariant(eqHex(r.tokenIdsHash, keccak256(encodeAbiParameters([{ type: 'uint32[]' }], [ids[i]]))), 'Token ABI hash mismatch');
    invariant(c.refBlock === 109 && c.transitionIndex === BigInt(i) && c.targetFunction === '0xf811127c' && c.nonSigners.length === 0, 'Actual certificate shape mismatch');
    invariant(eqHex(c.digest, sha256(encodeAbiParameters(parseAbiParameters('uint256,address,bytes4,bytes'), [BigInt(i), CONSUMER, c.targetFunction, c.payload]))), 'Actual digest mismatch');
    invariant(r.aPpm >= 550000 && r.bPpm < 550000, 'Actual preselected model support changed');
  }
  const finalizeCalldata = encodeFunctionData({ abi: consumer.abi, functionName: 'finalize', args: [proofs, inputs, ids] });
  return { consumer, proofs, exponent, modulus, inputs, ids, requests, requestKeys, operators,
    receipts, certificates, finalizeCalldata, gatePath, actorPath,
    packetHash: keccak256(finalizeCalldata), packetLength: (finalizeCalldata.length - 2) / 2 };
}

export class LocalRPC {
  constructor(url) {
    const u = new URL(url);
    invariant(u.protocol === 'http:' && u.hostname === '127.0.0.1' && u.port === '19545'
      && u.pathname === '/' && !u.search && !u.hash && !u.username && !u.password, 'Only isolated http://127.0.0.1:19545 allowed');
    this.url = u.href; this.counter = 0;
  }
  async call(method, params = []) {
    const res = await fetch(this.url, { method: 'POST', redirect: 'error',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: ++this.counter, method, params }),
      signal: AbortSignal.timeout(180000) });
    invariant(res.ok, `${method}: HTTP ${res.status}`);
    const body = await res.json();
    if (body.error) throw new Error(`${method}: ${JSON.stringify(body.error)}`);
    return body.result;
  }
  async read(address, abi, functionName, args = []) {
    const result = await this.call('eth_call', [{ to: address, data: encodeFunctionData({ abi, functionName, args }) }, 'latest']);
    return decodeFunctionResult({ abi, functionName, data: result });
  }
}

export async function sendRecordedTx(rpc, out, label, tx, timestamp, gasPrice = 0n) {
  const blockBefore = await rpc.call('eth_getBlockByNumber', ['latest', false]);
  invariant(timestamp > Number(BigInt(blockBefore.timestamp)) && timestamp <= FINAL_TIMESTAMP, `${label}: timestamp must advance within frozen clock`);
  await rpc.call('evm_setNextBlockTimestamp', [timestamp]);
  const full = { ...tx, gas: hex(GAS_LIMIT), gasPrice: hex(gasPrice), value: '0x0' };
  const bytes = Buffer.from((tx.data ?? '0x').slice(2), 'hex');
  saveNew(out, `${label}-transaction.private.json`, { timestamp, ...full, calldataBytes: bytes.length,
    calldataSHA256: sha(bytes), calldataKeccak256: keccak256(tx.data ?? '0x'),
    calldataZeroBytes: bytes.filter(x => x === 0).length });
  const hash = await rpc.call('eth_sendTransaction', [full]);
  let receipt;
  while (!(receipt = await rpc.call('eth_getTransactionReceipt', [hash]))) await new Promise(resolve => setTimeout(resolve, 200));
  const block = await rpc.call('eth_getBlockByHash', [receipt.blockHash, false]);
  saveNew(out, `${label}-receipt.private.json`, { receipt, block });
  invariant(receipt.status === '0x1', `${label} reverted; receipt saved`);
  invariant(Number(BigInt(block.timestamp)) === timestamp, `${label}: wrong mined clock`);
  invariant(BigInt(receipt.effectiveGasPrice) === gasPrice, `${label}: effective gas price mismatch`);
  return { label, hash, gasUsed: BigInt(receipt.gasUsed), effectiveGasPrice: BigInt(receipt.effectiveGasPrice),
    blockNumber: BigInt(receipt.blockNumber), timestamp, contractAddress: receipt.contractAddress };
}

export async function captureState(rpc, packet, gateAddress) {
  const c = packet.consumer.abi, g = artifact('PeaceFourReportEvidenceGate').abi;
  const state = {
    decision: await rpc.read(CONSUMER, c, 'decision'),
    observationCount: await rpc.read(CONSUMER, c, 'observationCount'),
    supportingSourceMask: await rpc.read(CONSUMER, c, 'supportingSourceMask'),
    anyBSupport: await rpc.read(CONSUMER, c, 'anyBSupport'),
    stateTransitionCount: await rpc.read(CONSUMER, c, 'stateTransitionCount'),
    consumedSourceMask: await rpc.read(gateAddress, g, 'consumedSourceMask'),
    observations: [], consumedRequests: [], consumedEmails: [],
  };
  for (let i = 0; i < 4; i++) {
    state.observations.push(await rpc.read(CONSUMER, c, 'observations', [packet.requestKeys[i]]));
    state.consumedRequests.push(await rpc.read(gateAddress, g, 'consumedRequests', [packet.requestKeys[i]]));
    state.consumedEmails.push(await rpc.read(gateAddress, g, 'consumedEmails', [packet.proofs[i].emailNullifier]));
  }
  return state;
}
function assertState(state, terminal) {
  invariant(Number(state.decision) === (terminal ? 1 : 0) && Number(state.observationCount) === 4
    && Number(state.supportingSourceMask) === 15 && state.anyBSupport === false
    && Number(state.stateTransitionCount) === 4 && Number(state.consumedSourceMask) === (terminal ? 15 : 0), 'Unexpected consumer/gate state');
  invariant(state.observations.every(x => x[0] && x[1] && !x[2]), 'Expected all four genuine A-only observations');
  invariant([...state.consumedRequests, ...state.consumedEmails].every(x => x === terminal), 'Unexpected nullifier consumption');
}

export async function runBaseline({ rpcUrl, out, execute = false, gasPrice = 0n, resumeAfterRegistry = false }) {
  invariant(path.resolve(out) === `${PRIVATE}/peace-anvil-comparison-20261021`, 'Use the new private comparison directory only');
  fs.mkdirSync(out, { recursive: true, mode: 0o700 });
  const packet = loadFrozenPacket();
  const names = ['DKIMRegistry', 'DKIMVerifier', 'SchnorrStakeRegistry', 'PeaceFourReportSchnorrConsumer', 'PeaceFourReportEvidenceGate'];
  const artifacts = Object.fromEntries(names.map(name => [name, artifact(name)]));
  // Encode every constructor before the first RPC mutation, including address validation.
  const expectedKeys = getContractAddress({ from: SETUP, nonce: 0n });
  const expectedVerifier = getContractAddress({ from: SETUP, nonce: 1n });
  const expectedRegistry = getContractAddress({ from: SETUP, nonce: 2n });
  for (const [name, args] of [
    ['DKIMRegistry', []], ['DKIMVerifier', [expectedKeys]],
    ['SchnorrStakeRegistry', [2n, 3n, SETUP, 0n]],
    ['PeaceFourReportSchnorrConsumer', [expectedVerifier, packet.proofs[0].publicKeyHash, expectedRegistry, AVS, packet.requests]],
  ]) encodeDeployData({ abi: artifacts[name].abi, bytecode: artifacts[name].bytecode.object, args });
  const plan = { schema: 'peace-local-anvil-baseline-v1', execute, resumeAfterRegistry, rpcUrl,
    runnerSHA256: sha(fs.readFileSync(fileURLToPath(import.meta.url))),
    clock: { genesis: GENESIS_TIMESTAMP, finalization: FINAL_TIMESTAMP, historicalReplay: true },
    consumer: CONSUMER, setupAccount: SETUP, publicTestDeployer: DEPLOYER, avs: AVS,
    packetHash: packet.packetHash, packetLength: packet.packetLength, requestKeys: packet.requestKeys,
    sourceOrder: ['bbc', 'cnn', 'abc', 'rfi'], gasPrice, txGasLimit: GAS_LIMIT,
    fixtures: { gate: packet.gatePath, actor: packet.actorPath },
    artifacts: Object.fromEntries(names.map(name => [name, { path: artifacts[name].artifactPath,
      sha256: artifacts[name].artifactSHA256, creationBytes: (artifacts[name].bytecode.object.length - 2) / 2 }])),
    limits: ['Local public TEST committee and synthetic balances only; no live AVS or production settlement.',
      'Relaxed code/initcode limits and 1B block gas are experimental, not default-chain feasibility.',
      'Actual prior actor CPU model execution is not an EVM model execution proof.',
      'Authorized SDK quorum can sign arbitrary STORE updates; typed receipts do not remove that trust.',
      'Initial direct receipt is provisional; final matched three-branch snapshot comparison supersedes it.',
      'Each receipt includes transaction calldata/intrinsic/cold access costs, unlike old single-test warm caller deltas.'] };
  saveNew(out, execute ? (resumeAfterRegistry ? 'baseline-resume-plan.private.json' : 'baseline-execution-plan.private.json') : 'baseline-offline-plan.private.json', plan);
  if (!execute) return plan;
  const rpc = new LocalRPC(rpcUrl);
  const chain = await rpc.call('eth_chainId');
  const client = await rpc.call('web3_clientVersion');
  const metadata = await rpc.call('anvil_metadata');
  const genesis = await rpc.call('eth_getBlockByNumber', ['latest', false]);
  invariant(BigInt(chain) === 31337n && /anvil/i.test(client), 'Only local Anvil chain31337 permitted');
  const nodeInfo = await rpc.call('anvil_nodeInfo');
  invariant(metadata.forkedNetwork == null && nodeInfo.forkConfig?.forkUrl === null
    && nodeInfo.forkConfig?.forkBlockNumber === null && nodeInfo.hardFork === 'Cancun', 'Non-fork Cancun required');
  const expectedHead = resumeAfterRegistry ? 102 : 0;
  invariant(BigInt(genesis.number) === BigInt(expectedHead) && Number(BigInt(genesis.timestamp)) === GENESIS_TIMESTAMP + expectedHead
    && BigInt(genesis.gasLimit) === 1000000000n, 'Expected untouched isolated genesis');
  saveNew(out, resumeAfterRegistry ? 'baseline-resume-rpc-guard.private.json' : 'baseline-rpc-guard.private.json', { chain, client, metadata, nodeInfo, genesis });
  // Explicit synthetic funding and impersonation; no private key is read or signed.
  if (!resumeAfterRegistry) {
    for (const account of [SETUP, DEPLOYER]) {
      await rpc.call('anvil_impersonateAccount', [account]);
      await rpc.call('anvil_setBalance', [account, hex(10n ** 24n)]);
    }
    await rpc.call('anvil_setNonce', [DEPLOYER, '0x3']);
  }
  const measurements = [];
  const nextClock = async () => GENESIS_TIMESTAMP + Number(BigInt(await rpc.call('eth_blockNumber'))) + 1;
  const send = async (label, tx) => {
    const result = await sendRecordedTx(rpc, out, label, tx, await nextClock(), gasPrice);
    measurements.push(result); return result;
  };
  const deploy = async (label, name, args, from = SETUP) => {
    const a = artifacts[name];
    const data = encodeDeployData({ abi: a.abi, bytecode: a.bytecode.object, args });
    return (await send(label, { from, data })).contractAddress;
  };
  const invoke = (label, address, name, functionName, args) => send(label, { from: SETUP, to: address,
    data: encodeFunctionData({ abi: artifacts[name].abi, functionName, args }) });
  let keys = expectedKeys, verifier = expectedVerifier, registry = expectedRegistry;
  if (!resumeAfterRegistry) {
    keys = await deploy('setup-01-dkim-registry', 'DKIMRegistry', []);
    verifier = await deploy('setup-02-dkim-verifier', 'DKIMVerifier', [keys]);
    registry = await deploy('setup-03-schnorr-registry', 'SchnorrStakeRegistry', [2n, 3n, SETUP, 0n]);
    invariant(eqHex(registry, expectedRegistry), 'Registry CREATE mismatch');
    await invoke('setup-04-google-key', keys, 'DKIMRegistry', 'registerKey', ['google.com', '20251104', packet.exponent, packet.modulus]);
  } else {
    const labels = ['setup-01-dkim-registry', 'setup-02-dkim-verifier', 'setup-03-schnorr-registry', 'setup-04-google-key',
      'setup-operator-0', 'setup-operator-1', 'setup-operator-2'];
    const checked = [];
    for (let i = 0; i < labels.length; i++) {
      const label = labels[i];
      const saved = JSON.parse(fs.readFileSync(path.join(out, `${label}-receipt.private.json`)));
      const tx = JSON.parse(fs.readFileSync(path.join(out, `${label}-transaction.private.json`)));
      const actualReceipt = await rpc.call('eth_getTransactionReceipt', [saved.receipt.transactionHash]);
      const actualTx = await rpc.call('eth_getTransactionByHash', [saved.receipt.transactionHash]);
      invariant(actualReceipt && actualReceipt.status === '0x1' && actualReceipt.blockHash === saved.receipt.blockHash
        && actualReceipt.gasUsed === saved.receipt.gasUsed && actualTx.input === tx.data
        && eqHex(actualTx.from, SETUP) && BigInt(actualTx.nonce) === BigInt(i), `Resume receipt/transaction mismatch: ${label}`);
      const expectedBlock = i < 4 ? i + 1 : i + 96;
      invariant(Number(BigInt(actualReceipt.blockNumber)) === expectedBlock, 'Unexpected original setup block');
      checked.push({ label, hash: actualTx.hash, block: expectedBlock });
      measurements.push({ label, hash: actualTx.hash, gasUsed: BigInt(actualReceipt.gasUsed),
        effectiveGasPrice: BigInt(actualReceipt.effectiveGasPrice), blockNumber: BigInt(actualReceipt.blockNumber),
        timestamp: tx.timestamp, contractAddress: actualReceipt.contractAddress, preservedFirstAttempt: true });
    }
    for (const address of [keys, verifier, registry]) invariant((await rpc.call('eth_getCode', [address, 'latest'])) !== '0x', 'Missing resumed deployed code');
    invariant(await rpc.call('eth_getCode', [CONSUMER, 'latest']) === '0x', 'Consumer already deployed');
    invariant(BigInt(await rpc.call('eth_getTransactionCount', [SETUP, 'latest'])) === 7n
      && BigInt(await rpc.call('eth_getTransactionCount', [DEPLOYER, 'latest'])) === 3n, 'Resume account nonces changed');
    invariant(await rpc.read(registry, artifacts.SchnorrStakeRegistry.abi, 'totalWeight') === 300n
      && await rpc.read(registry, artifacts.SchnorrStakeRegistry.abi, 'effectiveBlock') === 102n
      && await rpc.read(registry, artifacts.SchnorrStakeRegistry.abi, 'thresholdNum') === 2n
      && await rpc.read(registry, artifacts.SchnorrStakeRegistry.abi, 'thresholdDen') === 3n, 'Resume registry state changed');
    saveNew(out, 'baseline-resume-validated-setup.private.json', { checked, keys, verifier, registry });
  }
  const mineTo = async target => {
    const current = Number(BigInt(await rpc.call('eth_blockNumber')));
    invariant(target > current, 'Mine target must advance');
    await rpc.call('evm_setNextBlockTimestamp', [GENESIS_TIMESTAMP + current + 1]);
    await rpc.call('anvil_mine', [hex(target - current), '0x1']);
    const block = await rpc.call('eth_getBlockByNumber', ['latest', false]);
    invariant(Number(BigInt(block.number)) === target && Number(BigInt(block.timestamp)) === GENESIS_TIMESTAMP + target, 'Deterministic mining failed');
  };
  if (!resumeAfterRegistry) {
    await mineTo(99);
    for (let i = 0; i < 3; i++) {
      const o = packet.operators[i];
      await invoke(`setup-operator-${i}`, registry, 'SchnorrStakeRegistry', 'registerOperator', [o.x, o.y, o.weight, o.popS, o.popR]);
    }
  }
  const consumer = await deploy('setup-consumer', 'PeaceFourReportSchnorrConsumer', [verifier, packet.proofs[0].publicKeyHash, registry, AVS, packet.requests], DEPLOYER);
  invariant(eqHex(consumer, CONSUMER), 'Actual signed consumer CREATE address mismatch');
  const gateAddress = await rpc.read(CONSUMER, packet.consumer.abi, 'evidenceGate');
  await mineTo(109);
  for (let i = 0; i < 4; i++) {
    const c = packet.certificates[i];
    await invoke(`source-${i}-transport`, CONSUMER, 'PeaceFourReportSchnorrConsumer', 'verifyAndUpdate',
      [c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners]);
    await invoke(`source-${i}-observation`, CONSUMER, 'PeaceFourReportSchnorrConsumer', 'recordAuthenticatedObservation',
      [packet.requests[i], packet.proofs[i], packet.inputs[i], packet.ids[i], BigInt(i),
        { s: c.s, Raddr: c.Raddr, nonSigners: c.nonSigners, refBlock: BigInt(c.refBlock) }]);
  }
  const preState = await captureState(rpc, packet, gateAddress); assertState(preState, false);
  const preBlock = await rpc.call('eth_getBlockByNumber', ['latest', false]);
  saveNew(out, 'pre-finalize-state.private.json', preState);
  saveNew(out, 'pre-finalize-block.private.json', preBlock);
  saveNew(out, 'pre-finalize-anvil-dump.private.json', { state: await rpc.call('anvil_dumpState') });
  saveNew(out, 'finalize-calldata.private.json', { consumer: CONSUMER, data: packet.finalizeCalldata,
    packetHash: packet.packetHash, packetLength: packet.packetLength, timestamp: FINAL_TIMESTAMP });
  const snapshot = await rpc.call('evm_snapshot');
  saveNew(out, 'initial-pre-finalize-snapshot.private.json', { snapshot });
  const direct = await sendRecordedTx(rpc, out, 'initial-uncached-direct-finalize',
    { from: SETUP, to: CONSUMER, data: packet.finalizeCalldata }, FINAL_TIMESTAMP, gasPrice);
  const terminal = await captureState(rpc, packet, gateAddress); assertState(terminal, true);
  saveNew(out, 'initial-direct-terminal-state.private.json', terminal);
  invariant(await rpc.call('evm_revert', [snapshot]), 'Failed to restore pre-finalization snapshot');
  const restored = await captureState(rpc, packet, gateAddress); assertState(restored, false);
  invariant(json(restored) === json(preState), 'Restored state differs from prestate');
  const reusableSnapshot = await rpc.call('evm_snapshot');
  const addresses = { consumer: CONSUMER, gate: gateAddress, registry, verifier, keys, setup: SETUP, deployer: DEPLOYER, avs: AVS };
  const code = {};
  for (const [name, address] of Object.entries(addresses).filter(([name]) => !['setup', 'deployer', 'avs'].includes(name))) {
    const value = await rpc.call('eth_getCode', [address, 'latest']);
    code[name] = { address, keccak256: keccak256(value), bytes: (value.length - 2) / 2 };
  }
  const handoff = { ...plan, addresses, code, measurements, initialDirect: direct,
    preBlock, preState, restoredState: restored, reusableSnapshot,
    setupNextNonce: BigInt(await rpc.call('eth_getTransactionCount', [SETUP, 'latest'])),
    deployerNextNonce: BigInt(await rpc.call('eth_getTransactionCount', [DEPLOYER, 'latest'])),
    fullCalldataPath: path.join(out, 'finalize-calldata.private.json'),
    futureMatchedComparison: 'After publishing cache/relay and fixing actor anchor, use one common snapshot and identical next timestamp/sender for direct, cached direct, and actual-certified branches; revert and recreate between branches.' };
  saveNew(out, 'baseline-handoff.private.json', handoff);
  return handoff;
}

async function main() {
  const args = process.argv.slice(2), options = { rpcUrl: 'http://127.0.0.1:19545',
    out: `${PRIVATE}/peace-anvil-comparison-20261021`, execute: false, gasPrice: 0n, resumeAfterRegistry: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--rpc') options.rpcUrl = args[++i];
    else if (args[i] === '--out') options.out = args[++i];
    else if (args[i] === '--execute') options.execute = true;
    else if (args[i] === '--resume-after-registry') options.resumeAfterRegistry = true;
    else if (args[i] === '--gas-price-wei') options.gasPrice = BigInt(args[++i]);
    else throw new Error(`Unknown argument ${args[i]}`);
  }
  const result = await runBaseline(options);
  console.log(json({ executed: options.execute, consumer: CONSUMER, packetHash: result.packetHash,
    packetLength: result.packetLength, reusableSnapshot: result.reusableSnapshot,
    initialDirect: result.initialDirect }));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.stack); process.exitCode = 1; });
}
