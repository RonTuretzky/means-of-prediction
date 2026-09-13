// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {ConditionalTokens} from "../src/tokens/ConditionalTokens.sol";
import {TestUSDC} from "../src/tokens/TestUSDC.sol";
import {IERC20} from "../src/tokens/ERC20.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {EmailBodyStore} from "../src/dkim/EmailBodyStore.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {ILLMJudge} from "../src/judge/ILLMJudge.sol";
import {LLMJudge} from "../src/judge/LLMJudge.sol";
import {Qwen35Pins} from "./Qwen35Pins.sol";

/// @notice Sepolia testnet deployment (chain 11155111). A hybrid of the local and
/// Gnosis scripts: like Gnosis it targets a public chain with the canonical
/// Multicall3 and real DKIM keys (demo dev key + the REAL nytimes.com key from DNS,
/// via deployments/dkim-keys.json), but like local it deploys a faucet TestUSDC as
/// collateral and seeds demo markets — so anyone with an injected wallet and free
/// Sepolia ETH can trade and even settle the seeded market with the sample .emls.
///
///   node ../app/scripts/dkim-keys.mjs   # refresh deployments/dkim-keys.json first
///   forge script script/DeploySepolia.s.sol:DeploySepolia \
///     --rpc-url https://ethereum-sepolia-rpc.publicnode.com --broadcast \
///     --private-key $PRIVATE_KEY
///
/// Also deploys the LLMJudge (AI-judged settlement via Gas Killer's sharded Qwen3.5-35B):
/// wired to the public testnet AVS + BLS checker from gaskiller.xyz/docs/solidity/configuration
/// (override with GK_AVS / GK_SIG_CHECKER env; they change when the operator set is
/// redeployed — `setGasKillerConfig` follows a rotation without redeploying) and owned by
/// GK_JUDGE_OWNER (default: the deployer; move it to a multisig).
contract DeploySepolia is Script {
    address constant GK_AVS_DEFAULT = 0xdCec8ce0a03848B55989Bcc711e424Ca31d9eeD9;
    address constant GK_SIG_CHECKER_DEFAULT = 0x6953fc47FC8b7568801f3fdc327bc0d9aD12E5b9;

    function run() external {
        vm.startBroadcast();

        LLMJudge judge = new LLMJudge(
            vm.envOr("GK_JUDGE_OWNER", msg.sender),
            vm.envOr("GK_AVS", GK_AVS_DEFAULT),
            vm.envOr("GK_SIG_CHECKER", GK_SIG_CHECKER_DEFAULT),
            Qwen35Pins.modelConfig()
        );

        ConditionalTokens ct = new ConditionalTokens();
        TestUSDC usdc = new TestUSDC();
        DKIMRegistry dkim = new DKIMRegistry();
        DKIMVerifier verifier = new DKIMVerifier(dkim);
        EmailBodyStore bodyStore = new EmailBodyStore();
        MarketFactory factory = new MarketFactory(
            ct, verifier, address(new HeadlineMarket()), address(new FPMM()), ILLMJudge(address(judge))
        , vm.envOr("PROTOCOL_FEE", uint256(1e16)), vm.envOr("FEE_RECIPIENT", msg.sender));

        registerKeysFromFile(dkim);

        usdc.mint(msg.sender, 1_000_000e6);
        usdc.approve(address(factory), type(uint256).max);

        // --- Seed market 1: Fed rate cut (settleable with the sample .eml fixtures) ---
        MarketFactory.CreateMarketParams memory p1;
        p1.question = "Fed rate cut announced by September 20, 2026?";
        p1.description = "Resolves YES if at least 2 of 3 sources (The New York Times, The Washington"
            " Post, Reuters) send a breaking-news alert email matching the pattern"
            " /(?i)fed (cuts|lowers|slashes) (interest )?rates/ on the signed subject,"
            " dated before the deadline. Settled permissionlessly by DKIM proofs of the"
            " alert emails; resolves NO 24h after the deadline otherwise.";
        p1.contentRegex = "(?i)fed (cuts|lowers|slashes) (interest )?rates";
        p1.contentField = HeadlineMarket.ContentField.Subject;
        p1.sources = threeWires();
        p1.threshold = 2;
        p1.windowStart = 0; // sample .emls stay valid: try settling with emails/nyt-fed-cut.eml
        p1.deadline = uint64(block.timestamp + 30 days);
        p1.resolutionBuffer = 1 days;
        p1.collateralToken = IERC20(address(usdc));
        p1.fee = 2e16;
        p1.initialLiquidity = 25_000e6;
        p1.distributionHint = new uint256[](0);
        factory.createMarket(p1);

        // --- Seed market 2: Bitcoin $150k, skewed odds ---
        MarketFactory.CreateMarketParams memory p2;
        p2.question = "Bitcoin above $150k headline by October 1, 2026?";
        p2.description = "Resolves YES if 1 of 2 sources (Reuters, CNN) emails a breaking-news"
            " alert whose subject matches /(?i)(bitcoin|btc).{0,60}(\\$?15[0-9],?[0-9]{3}|\\$?150k)/"
            " before the deadline.";
        p2.contentRegex = "(?i)(bitcoin|btc).{0,60}(\\$?15[0-9],?[0-9]{3}|\\$?150k)";
        p2.contentField = HeadlineMarket.ContentField.Subject;
        p2.sources = new HeadlineMarket.Source[](2);
        p2.sources[0] = HeadlineMarket.Source({
            name: "Reuters", dkimDomain: "email.reuters.com", fromRegex: "@email\\.reuters\\.com$", contentRegex: ""
        });
        p2.sources[1] = HeadlineMarket.Source({
            name: "CNN", dkimDomain: "mail.cnn.com", fromRegex: "@mail\\.cnn\\.com$", contentRegex: ""
        });
        p2.threshold = 1;
        p2.windowStart = 0;
        p2.deadline = uint64(block.timestamp + 41 days);
        p2.resolutionBuffer = 1 days;
        p2.collateralToken = IERC20(address(usdc));
        p2.fee = 2e16;
        p2.initialLiquidity = 10_000e6;
        p2.distributionHint = new uint256[](2);
        p2.distributionHint[0] = 3; // YES opens at ~25c
        p2.distributionHint[1] = 1;
        factory.createMarket(p2);

        // --- Seed market 3: AI-judged (no regex) — the Iran invasion market from the board ---
        MarketFactory.CreateMarketParams memory p3;
        p3.question = "Will the U.S. invade Iran by December 31, 2026?";
        p3.criteria = "Resolves YES if at least 2 of the listed newspapers send a breaking-news alert"
            " email whose subject reports that the United States has invaded Iran, before January 1, 2027."
            " Airstrike headlines ('U.S. strikes Iran'), threats ('threatens to invade'), speculative headlines"
            " ('ahead of possible invasion'), polls, and question headlines do not count."
            " Resolves NO at the deadline otherwise.";
        p3.description = string.concat(
            p3.criteria,
            "\n\nAI-judged: an on-chain language model (Qwen3.5-35B via Gas Killer) applies these rules to"
            " the DKIM-signed subject line of each alert. Attested by the Gas Killer operator set, not proven"
            " on-chain.\n\n[category:world]"
        );
        p3.contentRegex = "";
        p3.contentField = HeadlineMarket.ContentField.Subject;
        p3.sources = threeWires();
        p3.threshold = 2;
        p3.windowStart = 0;
        p3.deadline = uint64(block.timestamp + 120 days);
        p3.resolutionBuffer = 3 days; // absorb fleet latency/outages (verdicts take hours)
        p3.collateralToken = IERC20(address(usdc));
        p3.fee = 2e16;
        p3.initialLiquidity = 10_000e6;
        p3.distributionHint = new uint256[](2);
        p3.distributionHint[0] = 4; // YES opens at ~20c
        p3.distributionHint[1] = 1;
        factory.createMarket(p3);

        vm.stopBroadcast();

        string memory json = "deployment";
        vm.serializeAddress(json, "conditionalTokens", address(ct));
        vm.serializeAddress(json, "usdc", address(usdc));
        vm.serializeAddress(json, "dkimRegistry", address(dkim));
        vm.serializeAddress(json, "verifier", address(verifier));
        vm.serializeAddress(json, "emailBodyStore", address(bodyStore));
        vm.serializeUint(json, "bodyParsingVersion", 1);
        vm.serializeAddress(json, "llmJudge", address(judge));
        vm.serializeAddress(json, "gkAvs", judge.avsAddress());
        vm.serializeAddress(json, "gkSigChecker", judge.blsSignatureChecker());
        vm.serializeBytes32(json, "qwen35Manifest", judge.weightsManifest());
        // canonical Multicall3, predeployed on Sepolia
        vm.serializeAddress(json, "multicall3", 0xcA11bde05977b3631167028862bE2a173976CA11);
        vm.serializeUint(json, "chainId", block.chainid);
        vm.serializeUint(json, "deployBlock", block.number);
        string memory out = vm.serializeAddress(json, "factory", address(factory));
        vm.writeJson(out, "./deployments/sepolia.json");
    }

    function registerKeysFromFile(DKIMRegistry dkim) internal {
        string memory json = vm.readFile("./deployments/dkim-keys.json");
        uint256 n = vm.parseJsonUint(json, ".count");
        for (uint256 i = 0; i < n; i++) {
            string memory base = string.concat(".keys[", vm.toString(i), "]");
            dkim.registerKey(
                vm.parseJsonString(json, string.concat(base, ".domain")),
                vm.parseJsonString(json, string.concat(base, ".selector")),
                vm.parseJsonBytes(json, string.concat(base, ".exponent")),
                vm.parseJsonBytes(json, string.concat(base, ".modulus"))
            );
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
            name: "Reuters", dkimDomain: "email.reuters.com", fromRegex: "@email\\.reuters\\.com$", contentRegex: ""
        });
    }
}
