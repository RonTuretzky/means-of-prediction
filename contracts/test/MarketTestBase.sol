// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ConditionalTokens} from "../src/tokens/ConditionalTokens.sol";
import {TestUSDC} from "../src/tokens/TestUSDC.sol";
import {IERC20} from "../src/tokens/ERC20.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {ILLMJudge} from "../src/judge/ILLMJudge.sol";
import {Rfc2822Formatter} from "./helpers/Rfc2822Formatter.sol";

/// @notice Shared fixture: deploys the whole stack and builds REAL DKIM email proofs —
/// each `makeProof` canonicalizes a header and signs it with the committed dev RSA key
/// (via ffi to test/helpers/rsa-sign.mjs), exactly as the onchain DKIMVerifier checks.
contract MarketTestBase is Test {
    ConditionalTokens ct;
    TestUSDC usdc;
    DKIMRegistry dkim;
    DKIMVerifier verifier;
    MarketFactory factory;
    Rfc2822Formatter rfc2822;

    bytes devModulus;
    bytes devExponent;
    bytes32 devKeyHash;

    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");
    address settler = makeAddr("settler");

    function setUp() public virtual {
        ct = new ConditionalTokens();
        rfc2822 = new Rfc2822Formatter();
        usdc = new TestUSDC();
        dkim = new DKIMRegistry();
        verifier = new DKIMVerifier(dkim);
        factory = new MarketFactory(ct, verifier, address(new HeadlineMarket()), address(new FPMM()), ILLMJudge(address(0)), 0, address(0));

        (devModulus, devExponent) = devPubKey();
        devKeyHash = keccak256(devModulus);
        dkim.registerKey("nytimes.com", "dev2026", devExponent, devModulus);
        dkim.registerKey("email.washingtonpost.com", "dev2026", devExponent, devModulus);
        dkim.registerKey("email.reuters.com", "dev2026", devExponent, devModulus);

        usdc.mint(alice, 1_000_000e6);
        usdc.mint(bob, 1_000_000e6);
        usdc.mint(carol, 1_000_000e6);
    }

    /// @dev Builds a REAL DKIM email proof: canonicalizes `from`/`subject` into a header,
    /// signs it with the dev RSA key, and packages it as the DKIMVerifier expects.
    /// `nullifier` seeds a distinct signature per call (so replays/dedup behave) by
    /// appending it to the signed header as a synthetic Message-ID.
    function makeProof(
        string memory domain,
        uint256 timestamp,
        string memory from,
        string memory subject,
        string memory body,
        bytes32 nullifier
    ) internal returns (EmailProof memory p) {
        // `body` is ignored: DKIMVerifier now refuses a non-empty bodyExcerpt, because the
        // header signature does not authenticate the body. Call sites keep passing their
        // descriptive filler text; it simply never reaches the proof. Use
        // makeProofWithBody() to exercise the rejection path deliberately.
        body;
        return makeProofWithBody(domain, timestamp, from, subject, "", nullifier);
    }

    /// @dev As makeProof, but carries `body` in bodyExcerpt — which a correct verifier
    /// rejects. Only for tests that pin that rejection.
    function makeProofWithBody(
        string memory domain,
        uint256 timestamp,
        string memory from,
        string memory subject,
        string memory body,
        bytes32 nullifier
    ) internal returns (EmailProof memory p) {
        // A real signed header carries `date:`, and the verifier binds proof.timestamp to
        // it, so the fixture must sign the date it claims.
        p.header = bytes.concat(signedHeader(from, subject, timestamp, nullifier),
            bytes(string.concat("\r\ndkim-signature:v=1; a=rsa-sha256; c=relaxed/relaxed; d=", domain, "; s=dev2026; b=")));
        p.signature = rsaSign(p.header);
        p.domainName = domain;
        p.publicKeyHash = devKeyHash;
        p.timestamp = timestamp;
        p.fromAddress = from;
        p.subject = subject;
        p.bodyExcerpt = body;
        p.emailNullifier = keccak256(p.signature);
    }

    /// @dev Kept out of makeProofWithBody: the concat's temporaries blow the stack there.
    function signedHeader(string memory from, string memory subject, uint256 timestamp, bytes32 nullifier)
        internal
        view
        returns (bytes memory)
    {
        return abi.encodePacked(
            "from:", from,
            "\r\nsubject:", subject,
            "\r\ndate:", rfc2822.format(timestamp),
            "\r\nmessage-id:<", vm.toString(nullifier), ">"
        );
    }

    function rsaSign(bytes memory message) internal returns (bytes memory) {
        string[] memory cmd = new string[](3);
        cmd[0] = "node";
        cmd[1] = "test/helpers/rsa-sign.mjs";
        cmd[2] = vm.toString(message);
        return vm.ffi(cmd);
    }

    function devPubKey() internal returns (bytes memory mod, bytes memory exp) {
        string[] memory cmd = new string[](3);
        cmd[0] = "node";
        cmd[1] = "test/helpers/rsa-sign.mjs";
        cmd[2] = "--pub-n";
        mod = vm.ffi(cmd);
        cmd[2] = "--pub-e";
        exp = vm.ffi(cmd);
    }

    function nytSources() internal pure returns (HeadlineMarket.Source[] memory sources) {
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

    function defaultParams() internal view returns (MarketFactory.CreateMarketParams memory params) {
        params = MarketFactory.CreateMarketParams({
            question: "Will the Fed cut rates before October 2026?",
            description: "Resolves YES if 2 of 3 sources (NYT, WaPo, Reuters) email a breaking-news"
                " alert matching the pattern before the deadline.",
            contentRegex: "(?i)fed (cuts|lowers|slashes) (interest )?rates",
            criteria: "",
            contentField: HeadlineMarket.ContentField.SubjectOrBody,
            sources: nytSources(),
            threshold: 2,
            windowStart: uint64(block.timestamp),
            deadline: uint64(block.timestamp + 30 days),
            resolutionBuffer: 1 days,
            collateralToken: IERC20(address(usdc)),
            fee: 2e16, // 2%
            initialLiquidity: 0,
            distributionHint: new uint256[](0)
        });
    }

    function createDefaultMarket() internal returns (HeadlineMarket market, FPMM fpmm) {
        (market, fpmm) = factory.createMarket(defaultParams());
    }

    function createFundedMarket(uint256 liquidity) internal returns (HeadlineMarket market, FPMM fpmm) {
        MarketFactory.CreateMarketParams memory params = defaultParams();
        params.initialLiquidity = liquidity;
        vm.startPrank(alice);
        usdc.approve(address(factory), liquidity);
        (market, fpmm) = factory.createMarket(params);
        vm.stopPrank();
    }
}
