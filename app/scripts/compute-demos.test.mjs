import test from 'node:test';
import assert from 'node:assert/strict';
import { encodeAbiParameters, encodeFunctionData, keccak256, toEventSelector } from 'viem';
import { COMPUTE_DEMOS } from '../src/data/compute-demos.ts';
import { computeDemoAbi, readComputeDemo } from '../src/lib/compute-demos.ts';

const ZERO = '0x' + '00'.repeat(32);
const OTHER = '0x' + '22'.repeat(20);
function scenario() {
  const code = '0x6001600055';
  const demo = { ...COMPUTE_DEMOS[0], runtimeCodeHash: keccak256(code) };
  const head = BigInt(demo.recordedBlock);
  const state = {
    outputHash: demo.expectedOutputHash, outputScalarCount: 32n, stateTransitionCount: 1n,
    owner: demo.owner, contextChainId: 11155111n, avsAddress: demo.avs, schnorrRegistry: demo.registry,
    MODEL_SHA256: demo.modelHash, RUNTIME_SHA256: demo.runtimeHash, EXPORT_SHA256: demo.exportHash,
    inputSHA256: demo.inputHash, weightsSHA256: demo.weightsHash, shiftsSHA256: demo.shiftsHash,
  };
  const log = { address: demo.contract, topics: [toEventSelector('Projected(bytes32,uint256)')],
    data: encodeAbiParameters([{ type: 'bytes32' }, { type: 'uint256' }], [demo.expectedOutputHash, 32n]) };
  const receipt = { status: 'success', transactionHash: demo.settlementTx, to: demo.contract,
    blockNumber: BigInt(demo.settlementBlock), blockHash: ZERO, gasUsed: 382979n, logs: [log] };
  const deployment = { status: 'success', transactionHash: demo.deploymentTx, contractAddress: demo.contract, blockNumber: BigInt(demo.deploymentBlock) };
  const transaction = { hash: demo.settlementTx, from: demo.owner, to: demo.contract, value: 0n, blockHash: ZERO,
    input: encodeFunctionData({ abi: computeDemoAbi, functionName: 'verifyAndUpdate', args: [ZERO, 11996368, '0x', 0n, '0xe8aa2982', 1n, OTHER, []] }) };
  const rpc = {
    getChainId: async () => 11155111,
    getBlockNumber: async () => head,
    getTransactionReceipt: async ({ hash }) => hash === demo.deploymentTx ? deployment : receipt,
    getTransaction: async () => transaction,
    getBytecode: async ({ address, blockNumber }) => { assert.equal(address, demo.contract); assert.equal(blockNumber, head); return code; },
    readContract: async ({ address, functionName, blockNumber }) => { assert.equal(address, demo.contract); assert.equal(blockNumber, head); return state[functionName]; },
  };
  return { demo, rpc, state, receipt, deployment, transaction, log };
}

test('indexes the pinned receipt and Projected event with consistent-block contract reads', async () => {
  const { demo, rpc } = scenario();
  const result = await readComputeDemo(demo, rpc);
  assert.equal(result.verified, true);
  assert.equal(result.checks.length, 9);
  assert.equal(result.outputCount, 32n);
  assert.equal(result.transitionCount, 1n);
  assert.equal(result.gasUsed, 382979n);
  assert.equal(result.eventCount, 1);
});

test('refuses a wrong chain or unavailable RPC instead of treating the saved snapshot as live', async () => {
  const { demo, rpc } = scenario();
  await assert.rejects(readComputeDemo(demo, { ...rpc, getChainId: async () => 100 }), /not Sepolia/);
  await assert.rejects(readComputeDemo(demo, { ...rpc, getTransactionReceipt: async () => { throw Error('offline'); } }), /offline/);
});

test('wrong result, counter, pins, owner or code cannot become verified', async () => {
  for (const [field, value] of [['outputHash', ZERO], ['outputScalarCount', 31n], ['stateTransitionCount', 0n], ['owner', OTHER], ['MODEL_SHA256', ZERO], ['weightsSHA256', ZERO], ['schnorrRegistry', OTHER]]) {
    const s = scenario(); s.state[field] = value;
    assert.equal((await readComputeDemo(s.demo, s.rpc)).verified, false, field);
  }
  const s = scenario(); s.rpc.getBytecode = async () => '0x';
  assert.equal((await readComputeDemo(s.demo, s.rpc)).verified, false);
});

test('a failed, unrelated or unconfirmed receipt cannot verify the computation', async () => {
  for (const change of [{ status: 'reverted' }, { to: OTHER }, { transactionHash: ZERO }, { blockNumber: 999999999n }]) {
    const s = scenario(); Object.assign(s.receipt, change);
    assert.equal((await readComputeDemo(s.demo, s.rpc)).verified, false);
  }
  const s = scenario(); s.deployment.contractAddress = OTHER;
  assert.equal((await readComputeDemo(s.demo, s.rpc)).verified, false);
});

test('requires the matching event from this contract and the actual certificate entrypoint', async () => {
  for (const mutate of [
    s => { s.receipt.logs = []; },
    s => { s.log.address = OTHER; },
    s => { s.receipt.logs.push(s.log); },
    s => { s.log.data = encodeAbiParameters([{ type: 'bytes32' }, { type: 'uint256' }], [ZERO, 32n]); },
    s => { s.transaction.input = '0x12345678'; },
    s => { s.transaction.to = OTHER; },
    s => { s.transaction.value = 1n; },
    s => { s.transaction.blockHash = '0x' + '11'.repeat(32); },
  ]) {
    const s = scenario(); mutate(s);
    assert.equal((await readComputeDemo(s.demo, s.rpc)).verified, false);
  }
});
