// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {LLMJudge} from "../src/judge/LLMJudge.sol";

/// @notice The Qwen3.5-35B-A3B pins every deployment of LLMJudge uses. Single source of truth
/// with app/scripts/judge/tokenizer.mjs (QWEN35) — change both or neither.
///
/// - manifest: the live Gas Killer overlay manifest of the 35B artifacts
///   (keccak(weights.bin) ++ keccak(tokenizer.bin)); verified byte-for-byte on the fleet's PVC
///   (service PR #336). Weight chunks = ceil(34,714,656,811 / 24,575) from the packed config's
///   weightLen; tokenizer = 2,836,777 bytes = 116 chunks (contracts/test/fixtures/qwen35).
/// - scaffold: `<|im_start|>user\n` … `<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n`
///   (thinking disabled), identical to the demo's QWEN_SCAFFOLDS["35b"].
/// - YES/NO: the single-token spellings the verdict accepts.
library Qwen35Pins {
    bytes32 internal constant MANIFEST = 0x7bdf4876a6861287521dadab3d3870f74dfa557507ed200d49f75bcb09f01fa9;
    uint256 internal constant WEIGHT_CHUNKS = 1_412_601;
    uint256 internal constant TOKENIZER_CHUNKS = 116;
    uint256 internal constant TOKENIZER_LENGTH = 2_836_777;
    uint32 internal constant SPECIAL_BASE = 248_044;

    function modelConfig(bytes32 manifest) internal pure returns (LLMJudge.ModelConfig memory m) {
        m.weightsManifest = manifest;
        m.weightChunks = WEIGHT_CHUNKS;
        m.tokenizerChunks = TOKENIZER_CHUNKS;
        m.tokenizerLength = TOKENIZER_LENGTH;
        m.specialBase = SPECIAL_BASE;
        m.prefixIds = new uint32[](3);
        m.prefixIds[0] = 248_045;
        m.prefixIds[1] = 846;
        m.prefixIds[2] = 198;
        uint32[9] memory suf = [uint32(248_046), 198, 248_045, 74_455, 198, 248_068, 271, 248_069, 271];
        m.suffixIds = new uint32[](9);
        for (uint256 i = 0; i < 9; ++i) {
            m.suffixIds[i] = suf[i];
        }
        uint32[6] memory y = [uint32(13_602), 9175, 9405, 13_677, 7179, 9542];
        uint32[6] memory n = [uint32(8725), 2665, 2083, 5486, 2233, 874];
        m.yesIds = new uint32[](6);
        m.noIds = new uint32[](6);
        for (uint256 i = 0; i < 6; ++i) {
            m.yesIds[i] = y[i];
            m.noIds[i] = n[i];
        }
    }

    function modelConfig() internal pure returns (LLMJudge.ModelConfig memory) {
        return modelConfig(MANIFEST);
    }
}
