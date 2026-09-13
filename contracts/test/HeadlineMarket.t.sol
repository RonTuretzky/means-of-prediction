// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MarketTestBase} from "./MarketTestBase.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";

contract HeadlineMarketTest is MarketTestBase {
    HeadlineMarket market;
    FPMM fpmm;

    string constant FED_SUBJECT = "Breaking News: Fed cuts rates by 25 basis points in surprise move";

    function setUp() public override {
        super.setUp();
        (market, fpmm) = createDefaultMarket();
    }

    function nytProof(bytes32 nullifier) internal returns (EmailProof memory) {
        return makeProof(
            "nytimes.com", block.timestamp + 1 days, "nytdirect@nytimes.com", FED_SUBJECT, "The Federal Reserve...",
            nullifier
        );
    }

    function wapoProof(bytes32 nullifier) internal returns (EmailProof memory) {
        return makeProof(
            "email.washingtonpost.com",
            block.timestamp + 1 days,
            "no-reply@email.washingtonpost.com",
            "Fed slashes rates amid market turmoil",
            "",
            nullifier
        );
    }

    // --- creation ---

    function test_CreateMarketValidatesConfig() public {
        MarketFactory.CreateMarketParams memory p = defaultParams();

        p.threshold = 4; // > sources
        vm.expectRevert(bytes("Market: bad threshold"));
        factory.createMarket(p);

        p = defaultParams();
        p.threshold = 0;
        vm.expectRevert(bytes("Market: bad threshold"));
        factory.createMarket(p);

        p = defaultParams();
        p.deadline = uint64(block.timestamp - 1);
        vm.expectRevert(bytes("Market: deadline in past"));
        factory.createMarket(p);

        p = defaultParams();
        p.contentRegex = "(unclosed";
        vm.expectRevert(bytes("Regex: missing ')'"));
        factory.createMarket(p);

        p = defaultParams();
        p.sources[0].fromRegex = "[bad";
        vm.expectRevert(bytes("Regex: unterminated class"));
        factory.createMarket(p);

        p = defaultParams();
        p.contentRegex = "";
        vm.expectRevert(bytes("Market: no content condition"));
        factory.createMarket(p);
    }

    function test_CannotBrickMarketByFrontRunningCondition() public {
        // Attacker predicts the next market's address (the factory's next CREATE — the
        // EIP-1167 clone) and pre-prepares its condition. Creation must still succeed
        // (idempotent prepare).
        address predictedMarket = vm.computeCreateAddress(address(factory), vm.getNonce(address(factory)));
        bytes32 qid = keccak256(abi.encodePacked("HEADLINE_MARKET_V1", predictedMarket));
        ct.prepareCondition(predictedMarket, qid, 2); // front-run

        (HeadlineMarket m2,) = createDefaultMarket();
        assertEq(address(m2), predictedMarket);
        // and it settles normally
        m2.submitProof(0, nytProof("f1"));
        m2.submitProof(1, wapoProof("f2"));
        assertEq(uint256(m2.resolution()), uint256(HeadlineMarket.Resolution.Yes));
    }

    function test_MarketRegisteredInFactory() public view {
        assertEq(factory.marketCount(), 1);
        MarketFactory.MarketRecord memory rec = factory.getMarket(0);
        assertEq(rec.market, address(market));
        assertEq(rec.fpmm, address(fpmm));
    }

    function test_ConditionPrepared() public view {
        assertEq(ct.getOutcomeSlotCount(market.conditionId()), 2);
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Unresolved));
    }

    // --- proof acceptance ---

    function test_AcceptsValidProof() public {
        EmailProof memory p = nytProof("n1"); // built before prank: makeProof does external calls
        vm.prank(settler);
        market.submitProof(0, p);
        assertEq(market.matchedCount(), 1);
        assertTrue(market.sourceMatched(0));
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Unresolved)); // 1 < threshold 2

        HeadlineMarket.Evidence[] memory ev = market.getEvidence();
        assertEq(ev.length, 1);
        assertEq(ev[0].submitter, settler);
        assertEq(ev[0].subject, FED_SUBJECT);
    }

    function test_ThresholdResolvesYes() public {
        market.submitProof(0, nytProof("n1"));
        market.submitProof(1, wapoProof("n2"));

        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Yes));
        // payout vector [1, 0] reported
        assertEq(ct.payoutDenominator(market.conditionId()), 1);
        assertEq(ct.payoutNumerators(market.conditionId(), 0), 1);
        assertEq(ct.payoutNumerators(market.conditionId(), 1), 0);
    }

    function test_RejectsWrongDomain() public {
        // valid WaPo-signed proof submitted against the NYT source slot
        EmailProof memory p = wapoProof("n1");
        vm.expectRevert(bytes("Market: wrong DKIM domain"));
        market.submitProof(0, p);
    }

    function test_RejectsWrongFromAddress() public {
        EmailProof memory p = makeProof(
            "nytimes.com", block.timestamp + 1 days, "phisher@nytimes.com", FED_SUBJECT, "", "n1"
        );
        vm.expectRevert(bytes("Market: from address mismatch"));
        market.submitProof(0, p);
    }

    function test_RejectsNonMatchingContent() public {
        EmailProof memory p = makeProof(
            "nytimes.com",
            block.timestamp + 1 days,
            "nytdirect@nytimes.com",
            "Breaking News: Fed holds rates steady",
            "",
            "n1"
        );
        vm.expectRevert(bytes("Market: content regex mismatch"));
        market.submitProof(0, p);
    }

    function test_RejectsTamperedProof() public {
        EmailProof memory p = nytProof("n1");
        p.subject = "Breaking News: Fed cuts rates!"; // outputs changed after proving
        vm.expectRevert(bytes("Market: invalid DKIM proof"));
        market.submitProof(0, p);
    }

    function test_RejectsUnregisteredDomain() public {
        EmailProof memory p = makeProof(
            "fakenews.example", block.timestamp + 1 days, "nytdirect@nytimes.com", FED_SUBJECT, "", "n1"
        );
        vm.expectRevert(bytes("Market: invalid DKIM proof"));
        market.submitProof(0, p);
    }

    function test_RejectsEmailOutsideWindow() public {
        EmailProof memory early = makeProof(
            "nytimes.com", market.windowStart() - 1, "nytdirect@nytimes.com", FED_SUBJECT, "", "n1"
        );
        vm.expectRevert(bytes("Market: email before window"));
        market.submitProof(0, early);

        EmailProof memory late = makeProof(
            "nytimes.com", uint256(market.deadline()) + 1, "nytdirect@nytimes.com", FED_SUBJECT, "", "n2"
        );
        vm.expectRevert(bytes("Market: email after deadline"));
        market.submitProof(0, late);
    }

    function test_RejectsReplayedProofSameSource() public {
        EmailProof memory p1 = nytProof("n1");
        market.submitProof(0, p1);
        vm.expectRevert(bytes("Market: source already matched"));
        market.submitProof(0, p1);
    }

    function test_RejectsDuplicateSource() public {
        EmailProof memory p1 = nytProof("n1");
        EmailProof memory p2 = nytProof("n2");
        market.submitProof(0, p1);
        vm.expectRevert(bytes("Market: source already matched"));
        market.submitProof(0, p2);
    }

    function test_RejectsDuplicateSourceDomain() public {
        // A K-of-N "distinct newspapers" threshold must not be satisfiable by one
        // domain occupying two slots.
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.sources[1] = p.sources[0];
        p.sources[1].name = "NYT duplicate slot";
        vm.expectRevert(bytes("Market: duplicate source domain"));
        factory.createMarket(p);
    }

    function test_PerSourceContentOverride() public {
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.sources[0].contentRegex = "(?i)federal reserve (cuts|lowers)"; // NYT words it differently
        p.threshold = 1;
        (HeadlineMarket m2,) = factory.createMarket(p);

        EmailProof memory bad = makeProof(
            "nytimes.com", block.timestamp + 1 days, "nytdirect@nytimes.com", FED_SUBJECT, "", "o1"
        );
        vm.expectRevert(bytes("Market: content regex mismatch"));
        m2.submitProof(0, bad);

        EmailProof memory good = makeProof(
            "nytimes.com",
            block.timestamp + 1 days,
            "nytdirect@nytimes.com",
            "Breaking News: Federal Reserve lowers benchmark rate",
            "",
            "o2"
        );
        m2.submitProof(0, good);
        assertEq(uint256(m2.resolution()), uint256(HeadlineMarket.Resolution.Yes));
    }

    function test_ContentFieldSubjectOnly() public {
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.contentField = HeadlineMarket.ContentField.Subject;
        p.threshold = 1;
        (HeadlineMarket m2,) = factory.createMarket(p);

        // pattern only in body — must NOT match in Subject-only mode
        EmailProof memory bodyOnly = makeProof(
            "nytimes.com",
            block.timestamp + 1 days,
            "nytdirect@nytimes.com",
            "Today's briefing",
            "The Fed cuts rates today.",
            "s1"
        );
        vm.expectRevert(bytes("Market: content regex mismatch"));
        m2.submitProof(0, bodyOnly);
    }

    // --- NO resolution ---

    function test_ResolveNoOnlyAfterDeadlinePlusBuffer() public {
        vm.expectRevert(bytes("Market: too early to resolve NO"));
        market.resolveNo();

        vm.warp(uint256(market.deadline()) + 1); // inside resolution buffer
        vm.expectRevert(bytes("Market: too early to resolve NO"));
        market.resolveNo();

        vm.warp(uint256(market.deadline()) + uint256(market.resolutionBuffer()) + 1);
        market.resolveNo();
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.No));
        assertEq(ct.payoutNumerators(market.conditionId(), 1), 1);
    }

    function test_LateProofStillSettlesYesDuringBuffer() public {
        vm.warp(uint256(market.deadline()) + 1 hours); // past deadline, inside buffer
        // emails dated within the window still count
        EmailProof memory p1 = makeProof(
            "nytimes.com", market.deadline() - 1, "nytdirect@nytimes.com", FED_SUBJECT, "", "n1"
        );
        EmailProof memory p2 = makeProof(
            "email.washingtonpost.com",
            market.deadline() - 1,
            "no-reply@email.washingtonpost.com",
            "Fed slashes rates amid market turmoil",
            "",
            "n2"
        );
        market.submitProof(0, p1);
        market.submitProof(1, p2);
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Yes));
    }

    function test_NoProofsAfterResolution() public {
        market.submitProof(0, nytProof("n1"));
        market.submitProof(1, wapoProof("n2"));
        EmailProof memory late =
            makeProof("email.reuters.com", block.timestamp, "x@email.reuters.com", FED_SUBJECT, "", "n3");
        vm.expectRevert(bytes("Market: already resolved"));
        market.submitProof(2, late);

        vm.warp(uint256(market.deadline()) + uint256(market.resolutionBuffer()) + 1);
        vm.expectRevert(bytes("Market: already resolved"));
        market.resolveNo();
    }

    // --- checkProof dry run ---

    function test_CheckProofReasons() public {
        (bool ok, string memory reason) = market.checkProof(0, nytProof("n1"));
        assertTrue(ok);
        assertEq(reason, "");

        (ok, reason) = market.checkProof(0, wapoProof("n1"));
        assertFalse(ok);
        assertEq(reason, "wrong DKIM domain");

        // Tampering a field bound to the RSA-signed header breaks verification: change
        // the subject after signing and the header no longer contains it.
        EmailProof memory tampered = nytProof("n1");
        tampered.subject = "Breaking News: Fed HIKES rates";
        (ok, reason) = market.checkProof(0, tampered);
        assertFalse(ok);
        assertEq(reason, "invalid DKIM proof");

        market.submitProof(0, nytProof("n1"));
        (ok, reason) = market.checkProof(0, nytProof("n2"));
        assertFalse(ok);
        assertEq(reason, "source already matched");
    }
}
