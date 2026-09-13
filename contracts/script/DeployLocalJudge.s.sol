// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {IBLSSignatureCheckerTypes} from "@eigenlayer-middleware/interfaces/IBLSSignatureChecker.sol";
import {ConditionalTokens} from "../src/tokens/ConditionalTokens.sol";
import {TestUSDC} from "../src/tokens/TestUSDC.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {LLMJudge} from "../src/judge/LLMJudge.sol";

/// @notice BLS checker stub that approves every submission with full stake (copy of the mock in
/// test/LLMJudge.t.sol, which is itself the SDK's own test mock). LOCAL E2E ONLY: it stands in
/// for the Gas Killer operator quorum so the bot's `verifyAndUpdate` transaction is accepted
/// without real BLS signatures.
contract MockBLSSignatureChecker {
    function checkSignatures(
        bytes32,
        bytes calldata quorumNumbers,
        uint32,
        IBLSSignatureCheckerTypes.NonSignerStakesAndSignature calldata
    ) external pure returns (IBLSSignatureCheckerTypes.QuorumStakeTotals memory totals, bytes32) {
        uint256 n = quorumNumbers.length;
        totals.signedStakeForQuorum = new uint96[](n);
        totals.totalStakeForQuorum = new uint96[](n);
        for (uint256 i = 0; i < n; ++i) {
            totals.signedStakeForQuorum[i] = 100;
            totals.totalStakeForQuorum[i] = 100;
        }
        return (totals, bytes32(0));
    }
}

/// @notice Deploys the judged-market stack to a local anvil chain for the Gas Killer local
/// end-to-end (app/scripts/judge/e2e): the usual market stack + a MockBLSSignatureChecker +
/// an LLMJudge pinned to the Qwen3.5-35B-A3B tokenizer (app/scripts/judge/tokenizer.mjs
/// QWEN35) + a MarketFactory wired to that judge. Writes deployments/local-judge.json.
///
///   forge script script/DeployLocalJudge.s.sol --rpc-url http://localhost:8549 --broadcast \
///     --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
contract DeployLocalJudge is Script {
    // Qwen3.5-35B-A3B pins (see app/scripts/judge/tokenizer.mjs QWEN35)
    bytes32 constant MANIFEST = keccak256("local-qwen35"); // addresses of the overlay chunks derive from it
    uint256 constant WEIGHT_CHUNKS = 1_412_601;
    uint256 constant TOKENIZER_CHUNKS = 116;
    uint256 constant TOKENIZER_LENGTH = 2_836_777;
    uint32 constant SPECIAL_BASE = 248_044;

    address constant ANVIL_1 = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;

    function run() external {
        vm.startBroadcast();

        ConditionalTokens ct = new ConditionalTokens();
        TestUSDC usdc = new TestUSDC();
        DKIMRegistry dkim = new DKIMRegistry();
        DKIMVerifier verifier = new DKIMVerifier(dkim);
        registerKeysFromFile(dkim);

        MockBLSSignatureChecker checker = new MockBLSSignatureChecker();
        LLMJudge judge = new LLMJudge(msg.sender, address(0xA5), address(checker), modelConfig());
        MarketFactory factory =
            new MarketFactory(ct, verifier, address(new HeadlineMarket()), address(new FPMM()), judge, vm.envOr("PROTOCOL_FEE", uint256(1e16)), vm.envOr("FEE_RECIPIENT", msg.sender));

        usdc.mint(msg.sender, 1_000_000e6);
        usdc.mint(ANVIL_1, 100_000e6);
        usdc.approve(address(factory), type(uint256).max);

        vm.stopBroadcast();

        string memory json = "deployment";
        vm.serializeAddress(json, "conditionalTokens", address(ct));
        vm.serializeAddress(json, "usdc", address(usdc));
        vm.serializeAddress(json, "dkimRegistry", address(dkim));
        vm.serializeAddress(json, "verifier", address(verifier));
        vm.serializeAddress(json, "llmJudge", address(judge));
        vm.serializeAddress(json, "mockChecker", address(checker));
        vm.serializeBytes32(json, "manifest", MANIFEST);
        vm.serializeUint(json, "weightChunks", WEIGHT_CHUNKS);
        vm.serializeUint(json, "tokenizerChunks", TOKENIZER_CHUNKS);
        vm.serializeUint(json, "tokenizerLength", TOKENIZER_LENGTH);
        vm.serializeUint(json, "chainId", block.chainid);
        vm.serializeUint(json, "deployBlock", block.number);
        string memory out = vm.serializeAddress(json, "factory", address(factory));
        vm.writeJson(out, "./deployments/local-judge.json");
    }

    function modelConfig() internal pure returns (LLMJudge.ModelConfig memory m) {
        m.weightsManifest = MANIFEST;
        m.weightChunks = WEIGHT_CHUNKS;
        m.tokenizerChunks = TOKENIZER_CHUNKS;
        m.tokenizerLength = TOKENIZER_LENGTH;
        m.specialBase = SPECIAL_BASE;
        m.prefixIds = new uint32[](3); // <|im_start|>user\n
        m.prefixIds[0] = 248_045;
        m.prefixIds[1] = 846;
        m.prefixIds[2] = 198;
        // <|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n
        uint32[9] memory suf = [uint32(248_046), 198, 248_045, 74_455, 198, 248_068, 271, 248_069, 271];
        m.suffixIds = new uint32[](9);
        for (uint256 i = 0; i < 9; ++i) m.suffixIds[i] = suf[i];
        uint32[6] memory y = [uint32(13_602), 9175, 9405, 13_677, 7179, 9542]; // YES Yes yes ' YES' ' Yes' ' yes'
        uint32[6] memory n = [uint32(8725), 2665, 2083, 5486, 2233, 874]; // NO No no ' NO' ' No' ' no'
        m.yesIds = new uint32[](6);
        m.noIds = new uint32[](6);
        for (uint256 i = 0; i < 6; ++i) {
            m.yesIds[i] = y[i];
            m.noIds[i] = n[i];
        }
    }

    /// @dev Same as script/Deploy.s.sol: reads deployments/dkim-keys.json and registers each key
    /// (the committed dev key for the newspaper domains + the real NYT key).
    function registerKeysFromFile(DKIMRegistry dkim) internal {
        string memory json = vm.readFile("./deployments/dkim-keys.json");
        uint256 n = vm.parseJsonUint(json, ".count");
        for (uint256 i = 0; i < n; i++) {
            string memory base = string.concat(".keys[", vm.toString(i), "]");
            string memory domain = vm.parseJsonString(json, string.concat(base, ".domain"));
            string memory selector = vm.parseJsonString(json, string.concat(base, ".selector"));
            bytes memory exp = vm.parseJsonBytes(json, string.concat(base, ".exponent"));
            bytes memory modulus = vm.parseJsonBytes(json, string.concat(base, ".modulus"));
            dkim.registerKey(domain, selector, exp, modulus);
        }
    }
}
