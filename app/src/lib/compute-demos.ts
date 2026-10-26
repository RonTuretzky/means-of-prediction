import { createPublicClient, decodeEventLog, decodeFunctionData, http, keccak256, parseAbi, type PublicClient } from "viem";
import { sepolia } from "viem/chains";
import type { ComputeDemo } from "../data/compute-demos.ts";

export const COMPUTE_RPC = "https://ethereum-sepolia-rpc.publicnode.com";
export const computeDemoAbi = parseAbi([
  "event Projected(bytes32 outputHash, uint256 outputScalarCount)",
  "function outputHash() view returns (bytes32)",
  "function outputScalarCount() view returns (uint256)",
  "function stateTransitionCount() view returns (uint256)",
  "function owner() view returns (address)",
  "function contextChainId() view returns (uint256)",
  "function avsAddress() view returns (address)",
  "function schnorrRegistry() view returns (address)",
  "function MODEL_SHA256() view returns (bytes32)",
  "function RUNTIME_SHA256() view returns (bytes32)",
  "function EXPORT_SHA256() view returns (bytes32)",
  "function inputSHA256() view returns (bytes32)",
  "function weightsSHA256() view returns (bytes32)",
  "function shiftsSHA256() view returns (bytes32)",
  "function verifyAndUpdate(bytes32 msgHash, uint32 referenceBlockNumber, bytes storageUpdates, uint256 transitionIndex, bytes4 targetFunction, uint256 s, address Raddr, address[] nonSigners) payable",
]);

// This index always reads Sepolia. The wallet and the market network selector
// cannot change its chain, and viewing it never needs the private operator API.
const client = createPublicClient({
  chain: sepolia,
  transport: http(COMPUTE_RPC, { batch: { wait: 16 }, timeout: 12_000, retryCount: 0 }),
});

export interface ComputeDemoResult {
  verified: boolean;
  checks: { label: string; passed: boolean }[];
  blockNumber: bigint;
  checkedAt: string;
  outputHash: string;
  outputCount: bigint;
  transitionCount: bigint;
  gasUsed: bigint;
  eventCount: number;
}

type Reader = Pick<PublicClient, "getChainId" | "getBlockNumber" | "getTransactionReceipt" | "getTransaction" | "getBytecode" | "readContract">;
const same = (a: unknown, b: unknown) => typeof a === "string" && typeof b === "string" && a.toLowerCase() === b.toLowerCase();

export async function readComputeDemo(demo: ComputeDemo, rpc: Reader = client): Promise<ComputeDemoResult> {
  if (await rpc.getChainId() !== demo.chainId || demo.chainId !== sepolia.id) throw new Error("The read endpoint is not Sepolia.");
  const blockNumber = await rpc.getBlockNumber();
  const readNames = ["outputHash", "outputScalarCount", "stateTransitionCount", "owner", "contextChainId", "avsAddress", "schnorrRegistry", "MODEL_SHA256", "RUNTIME_SHA256", "EXPORT_SHA256", "inputSHA256", "weightsSHA256", "shiftsSHA256"] as const;
  const [deployment, receipt, transaction, code, state] = await Promise.all([
    rpc.getTransactionReceipt({ hash: demo.deploymentTx }),
    rpc.getTransactionReceipt({ hash: demo.settlementTx }),
    rpc.getTransaction({ hash: demo.settlementTx }),
    rpc.getBytecode({ address: demo.contract, blockNumber }),
    Promise.all(readNames.map(functionName => rpc.readContract({ address: demo.contract, abi: computeDemoAbi, functionName, blockNumber }))),
  ]);
  const [outputHash, outputCount, transitionCount, owner, chainId, avs, registry, model, runtime, exported, input, weights, shifts] = state;
  const projected = receipt.logs.filter(log => same(log.address, demo.contract)).flatMap(log => {
    try {
      const event = decodeEventLog({ abi: computeDemoAbi, topics: log.topics, data: log.data, strict: true });
      return event.eventName === "Projected" ? [event.args] : [];
    } catch { return []; }
  });
  let certificateCall = false;
  try {
    const call = decodeFunctionData({ abi: computeDemoAbi, data: transaction.input });
    certificateCall = call.functionName === "verifyAndUpdate" && call.args[3] === 0n && call.args[4] === "0xe8aa2982";
  } catch { /* An unknown call is a failed check, not a verified certificate. */ }
  const checks = [
    { label: "Deployment receipt creates the indexed contract", passed: deployment.status === "success" && same(deployment.transactionHash, demo.deploymentTx) && same(deployment.contractAddress, demo.contract) && deployment.blockNumber === BigInt(demo.deploymentBlock) },
    { label: "Certificate transaction succeeded on Sepolia", passed: receipt.status === "success" && same(receipt.transactionHash, demo.settlementTx) && same(receipt.to, demo.contract) && receipt.blockNumber === BigInt(demo.settlementBlock) && receipt.blockNumber <= blockNumber },
    { label: "Transaction applies the expected computation certificate", passed: certificateCall && same(transaction.hash, demo.settlementTx) && same(transaction.to, demo.contract) && same(transaction.from, demo.owner) && transaction.value === 0n && transaction.blockHash === receipt.blockHash },
    { label: "Deployed code matches the verified demo", passed: !!code && same(keccak256(code), demo.runtimeCodeHash) },
    { label: "Owner, Sepolia chain and operator registry match", passed: same(owner, demo.owner) && chainId === BigInt(demo.chainId) && same(avs, demo.avs) && same(registry, demo.registry) },
    { label: "Model, arithmetic and input commitments match", passed: same(model, demo.modelHash) && same(runtime, demo.runtimeHash) && same(exported, demo.exportHash) && same(input, demo.inputHash) && same(weights, demo.weightsHash) && same(shifts, demo.shiftsHash) },
    { label: "Stored output hash matches the expected result", passed: same(outputHash, demo.expectedOutputHash) },
    { label: "32 outputs and one completed transition are stored", passed: outputCount === BigInt(demo.expectedOutputCount) && transitionCount === BigInt(demo.expectedTransitionCount) },
    { label: "Projected event agrees with the stored result", passed: projected.length === 1 && same(projected[0].outputHash, demo.expectedOutputHash) && projected[0].outputScalarCount === BigInt(demo.expectedOutputCount) },
  ];
  return {
    verified: checks.every(check => check.passed), checks, blockNumber, checkedAt: new Date().toISOString(),
    outputHash: String(outputHash), outputCount: BigInt(outputCount), transitionCount: BigInt(transitionCount),
    gasUsed: receipt.gasUsed, eventCount: projected.length,
  };
}
