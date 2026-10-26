// Public deployment index. No mailbox data, credentials, or operator API access.
// Source: docs/laya-gaskiller-sepolia-validation-20261026.json.
import type { Address, Hex } from "viem";

export interface ComputeDemo {
  id: string; title: string; description: string; chainId: number;
  contract: Address; owner: Address; avs: Address; registry: Address;
  deploymentTx: Hex; deploymentBlock: string; settlementTx: Hex; settlementBlock: string;
  expectedOutputHash: Hex; expectedOutputCount: number; expectedTransitionCount: number;
  recordedAt: string; recordedBlock: string; recordedGasUsed: string; taskId: string;
  runtimeCodeHash: Hex; modelHash: Hex; runtimeHash: Hex; exportHash: Hex;
  inputHash: Hex; weightsHash: Hex; shiftsHash: Hex;
}

export const COMPUTE_DEMOS: readonly ComputeDemo[] = [
  {
    "id": "laya-qkv-sepolia",
    "title": "Laya × GasKiller",
    "description": "A real Laya computation, certified by GasKiller and recorded on Sepolia.",
    "chainId": 11155111,
    "contract": "0x6b43b0bb9ce3329cd678724c6b673500aa3b0f8e",
    "owner": "0x6636A1CCBdf54485067304C1a590DE016DeaD9F0",
    "avs": "0x0eF3c25243004C0F81Dc678c3411E619D61577ef",
    "registry": "0xC3550328D09EDC4dfda4f171fB1CE39269A2E4f0",
    "deploymentTx": "0xe7679022470c984e37bc7f39a923625348e3ef143740c266c83144ebd553eca3",
    "deploymentBlock": "11996369",
    "settlementTx": "0x1331a73495eb89db1db4c01412f7305b4c4df9a9f3ea183220c956912b447dbb",
    "settlementBlock": "11996370",
    "expectedOutputHash": "0xe901e7fab31cdfa2551ef72352ca1648d5b778ce346f6a442084f2f859390a63",
    "expectedOutputCount": 32,
    "expectedTransitionCount": 1,
    "recordedAt": "2026-10-26T07:06:03.135Z",
    "recordedBlock": "11996374",
    "recordedGasUsed": "382979",
    "taskId": "c97e7acb-27ea-4c7b-ab22-50a72847bc8a",
    "runtimeCodeHash": "0x1c5c36819f7eec8aa5a5517e4008e020ef2f069a710daf982340845437eaee55",
    "modelHash": "0x5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169",
    "runtimeHash": "0xb06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766",
    "exportHash": "0xb863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d",
    "inputHash": "0xecda0377dcf4ccf79538ac011b4d5d585b574c0c0dba0c59f4afa6fdbabca76e",
    "weightsHash": "0x301143b03e15c1073737f103c7fd29b08a384690d02560987a8351beed806808",
    "shiftsHash": "0x66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"
  }
];
