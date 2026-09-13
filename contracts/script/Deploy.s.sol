// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {ConditionalTokens} from "../src/tokens/ConditionalTokens.sol";
import {TestUSDC} from "../src/tokens/TestUSDC.sol";
import {IERC20} from "../src/tokens/ERC20.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {ILLMJudge} from "../src/judge/ILLMJudge.sol";
import {LLMJudge} from "../src/judge/LLMJudge.sol";
import {Qwen35Pins} from "./Qwen35Pins.sol";
import {IBLSSignatureCheckerTypes} from "@eigenlayer-middleware/interfaces/IBLSSignatureChecker.sol";

/// @dev Local-only BLS checker that approves every submission with full stake, so the
/// judge's `verifyAndUpdate` can be exercised on anvil (see app/scripts/judge/e2e).
contract LocalMockBLSSignatureChecker {
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
import {EmailBodyStore} from "../src/dkim/EmailBodyStore.sol";
import {Multicall3} from "../src/utils/Multicall3.sol";

/// @notice Deploys the full stack to a local anvil chain, seeds demo markets and
/// writes the addresses to deployments/local.json for the frontend.
///
///   forge script script/Deploy.s.sol --rpc-url http://localhost:8545 --broadcast \
///     --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
contract Deploy is Script {
    // default anvil accounts 1-3 get faucet funds for manual testing
    address constant ANVIL_1 = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;
    address constant ANVIL_2 = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC;
    address constant ANVIL_3 = 0x90F79bf6EB2c4f870365E785982E1f101E93b906;

    function run() external {
        vm.startBroadcast();

        Multicall3 multicall = new Multicall3();
        EmailBodyStore bodyStore = new EmailBodyStore();
        ConditionalTokens ct = new ConditionalTokens();
        TestUSDC usdc = new TestUSDC();
        DKIMRegistry dkim = new DKIMRegistry();
        DKIMVerifier verifier = new DKIMVerifier(dkim);
        // AI-judged settlement (local: mock quorum; the overlay tokenizer is mounted by the e2e script)
        LocalMockBLSSignatureChecker checker = new LocalMockBLSSignatureChecker();
        LLMJudge judge = new LLMJudge(
            msg.sender, address(0xA5), address(checker), Qwen35Pins.modelConfig(keccak256("local-qwen35"))
        );
        MarketFactory factory =
            new MarketFactory(ct, verifier, address(new HeadlineMarket()), address(new FPMM()), ILLMJudge(address(judge)), vm.envOr("PROTOCOL_FEE", uint256(1e16)), vm.envOr("FEE_RECIPIENT", msg.sender));

        // Register real DKIM public keys. The demo fixtures are signed by a committed
        // dev key (keys/dev-dkim.pub) registered for the newspaper domains; the REAL
        // NYT key is registered too so a real NYT email verifies against it. Keys are
        // read from deployments/dkim-keys.json (written by app/scripts/dkim-keys.mjs).
        registerKeysFromFile(dkim);

        // Fund the deployer and the standard anvil test accounts.
        usdc.mint(msg.sender, 1_000_000e6);
        usdc.mint(ANVIL_1, 100_000e6);
        usdc.mint(ANVIL_2, 100_000e6);
        usdc.mint(ANVIL_3, 100_000e6);

        usdc.approve(address(factory), type(uint256).max);

        // --- Seed market 1: Fed rate cut (matches the sample .eml files) ---
        MarketFactory.CreateMarketParams memory p1;
        p1.question = "Fed rate cut announced by September 10, 2026?";
        p1.description = "Resolves YES if at least 2 of 3 sources (The New York Times, The Washington"
            " Post, Reuters) send a breaking-news alert email matching the pattern"
            " /(?i)fed (cuts|lowers|slashes) (interest )?rates/ on the signed subject,"
            " dated before the deadline. Settled permissionlessly by DKIM proofs of the"
            " alert emails; resolves NO 24h after the deadline otherwise.";
        p1.contentRegex = "(?i)fed (cuts|lowers|slashes) (interest )?rates";
        p1.contentField = HeadlineMarket.ContentField.Subject;
        p1.sources = threeWires();
        p1.threshold = 2;
        p1.windowStart = 0; // accept any email date up to the deadline (sample .emls stay valid)
        p1.deadline = uint64(block.timestamp + 30 days);
        p1.resolutionBuffer = 1 days;
        p1.collateralToken = IERC20(address(usdc));
        p1.fee = 2e16;
        p1.initialLiquidity = 25_000e6;
        p1.distributionHint = new uint256[](0);
        factory.createMarket(p1);

        // --- Seed market 2: Bitcoin $150k, skewed odds via distribution hint ---
        MarketFactory.CreateMarketParams memory p2;
        p2.question = "Bitcoin above $150k headline by October 1, 2026?";
        p2.description = "Resolves YES if 1 of 2 sources (Reuters, CNN) emails a breaking-news"
            " alert whose subject matches /(?i)(bitcoin|btc).{0,60}(\\$?15[0-9],?[0-9]{3}|\\$?150k)/"
            " before the deadline.";
        p2.contentRegex = "(?i)(bitcoin|btc).{0,60}(\\$?15[0-9],?[0-9]{3}|\\$?150k)";
        p2.contentField = HeadlineMarket.ContentField.Subject;
        p2.sources = new HeadlineMarket.Source[](2);
        p2.sources[0] = HeadlineMarket.Source({
            name: "Reuters",
            dkimDomain: "email.reuters.com",
            fromRegex: "@email\\.reuters\\.com$",
            contentRegex: ""
        });
        p2.sources[1] = HeadlineMarket.Source({
            name: "CNN",
            dkimDomain: "mail.cnn.com",
            fromRegex: "@mail\\.cnn\\.com$",
            contentRegex: ""
        });
        p2.threshold = 1;
        p2.windowStart = 0;
        p2.deadline = uint64(block.timestamp + 51 days);
        p2.resolutionBuffer = 1 days;
        p2.collateralToken = IERC20(address(usdc));
        p2.fee = 2e16;
        p2.initialLiquidity = 10_000e6;
        p2.distributionHint = new uint256[](2);
        p2.distributionHint[0] = 3; // YES starts at 25c
        p2.distributionHint[1] = 1;
        factory.createMarket(p2);

        // --- Seed market 3: near deadline, demonstrates the NO-resolution path ---
        MarketFactory.CreateMarketParams memory p3;
        p3.question = "Alien contact confirmed this week?";
        p3.description = "Resolves YES if 2 of 3 sources (NYT, WaPo, Reuters) send a breaking-news"
            " alert matching /(?i)(alien|extraterrestrial) (life|contact|signal) (confirmed|verified)/"
            " before the deadline (7 days). Almost certainly resolves NO - useful for demoing"
            " the permissionless NO path.";
        p3.contentRegex = "(?i)(alien|extraterrestrial) (life|contact|signal) (confirmed|verified)";
        p3.contentField = HeadlineMarket.ContentField.Subject;
        p3.sources = threeWires();
        p3.threshold = 2;
        p3.windowStart = uint64(block.timestamp);
        p3.deadline = uint64(block.timestamp + 7 days);
        p3.resolutionBuffer = 1 hours;
        p3.collateralToken = IERC20(address(usdc));
        p3.fee = 2e16;
        p3.initialLiquidity = 5_000e6;
        p3.distributionHint = new uint256[](2);
        p3.distributionHint[0] = 19; // pool keeps 19x YES => YES starts at ~5c, NO at ~95c
        p3.distributionHint[1] = 1;
        factory.createMarket(p3);

        vm.stopBroadcast();

        // Addresses for the frontend + e2e tests.
        string memory json = "deployment";
        vm.serializeAddress(json, "conditionalTokens", address(ct));
        vm.serializeAddress(json, "usdc", address(usdc));
        vm.serializeAddress(json, "dkimRegistry", address(dkim));
        vm.serializeAddress(json, "verifier", address(verifier));
        vm.serializeAddress(json, "llmJudge", address(judge));
        vm.serializeAddress(json, "mockChecker", address(checker));
        vm.serializeBytes32(json, "qwen35Manifest", judge.weightsManifest());
        vm.serializeAddress(json, "multicall3", address(multicall));
        vm.serializeUint(json, "chainId", block.chainid);
        vm.serializeUint(json, "bodyParsingVersion", 1);
        vm.serializeAddress(json, "emailBodyStore", address(bodyStore));
        string memory out = vm.serializeAddress(json, "factory", address(factory));
        vm.writeJson(out, "./deployments/local.json");
    }

    /// @dev Reads deployments/dkim-keys.json and registers each {domain, exp, modulus}.
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

    function threeWires() internal pure returns (HeadlineMarket.Source[] memory sources) {
        sources = new HeadlineMarket.Source[](3);
        sources[0] = HeadlineMarket.Source({
            name: "The New York Times",
            dkimDomain: "nytimes.com",
            fromRegex: "^nytdirect@nytimes\\.com$",
            contentRegex: ""
        });
        sources[1] = HeadlineMarket.Source({
            name: "The Washington Post",
            dkimDomain: "email.washingtonpost.com",
            fromRegex: "@email\\.washingtonpost\\.com$",
            contentRegex: ""
        });
        sources[2] = HeadlineMarket.Source({
            name: "Reuters",
            dkimDomain: "email.reuters.com",
            fromRegex: "@email\\.reuters\\.com$",
            contentRegex: ""
        });
    }
}
