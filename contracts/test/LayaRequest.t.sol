// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";

// Test-only pure wrapper: never a verdict store or a substitute for an authenticated judge.
contract LayaBindingHarness {
    function flags(LayaRequest.Request memory r, LayaRequest.Result memory result)
        external
        pure
        returns (LayaRequest.SupportFlags memory)
    {
        return LayaRequest.supportFlags(r, result);
    }

    function validate(LayaRequest.Request memory r, uint256 now_, uint256 chainId_, address market_) external pure {
        LayaRequest.validate(r, now_, chainId_, market_);
    }

    function evidence(LayaRequest.Request memory r, EmailProof calldata p) external pure {
        LayaRequest.validateEvidence(r, p);
    }

    function input(LayaRequest.Request memory r, bytes memory text, uint32[] memory ids) external pure {
        LayaRequest.validateInput(r, text, ids);
    }
}

contract LayaRequestTest is Test {
    LayaBindingHarness private harness;
    uint256 private constant NOW = 1_800_000_000;
    address private constant MARKET = address(0x1234);

    function setUp() public {
        harness = new LayaBindingHarness();
    }

    function fixture() private pure returns (LayaRequest.Request memory r) {
        r.version = 1;
        r.chainId = 100;
        r.market = MARKET;
        r.rulesHash = keccak256("question+A+B+window+resolution-rules");
        r.sourcePolicyHash = keccak256("ordered-source-domains+from+host+K");
        r.sourceIndex = 0;
        r.emailHash = keccak256("full-email-proof");
        r.emailNullifier = keccak256("signature");
        r.canonicalBodySha256 = sha256("full-body");
        r.parserVersion = 2;
        r.parserPolicyHash = keccak256("GoogleAlertBodyParser-v2+alert-extraction-v1");
        r.bodyOffset = 3;
        r.bodyLength = 20;
        r.decodedBytesHash = keccak256("decoded-source");
        r.inputBytesHash = keccak256("serialized-rules+alert");
        r.tokenIdsHash = keccak256("canonical-ids");
        r.tokenCount = 3;
        r.model = LayaRequest.ModelPins({
            weights: keccak256("weights"),
            tokenizer: keccak256("tokenizer"),
            schema: keccak256("schema"),
            arithmetic: keccak256("integer-rounding"),
            preprocessing: keccak256("preprocessing"),
            calibration: keccak256("temperatures"),
            runtime: keccak256("runtime-code+segment-layout"),
            maxTokens: 512
        });
        r.thresholdPpm = 550_000;
        r.decisionPolicy = LayaRequest.ALERT_STUDENT_BASE_SUPPORT_V1;
        r.expiresAt = uint64(NOW + 100);
        r.nonce = 1;
    }

    function resultFor(LayaRequest.Request memory r, uint32 a, uint32 b)
        private
        pure
        returns (LayaRequest.Result memory)
    {
        return LayaRequest.Result(1, LayaRequest.key(r), keccak256("UNAUTHENTICATED test root"), a, b);
    }

    function test_ValidContextAndExpiryBoundary() public view {
        LayaRequest.Request memory r = fixture();
        harness.validate(r, NOW, 100, MARKET);
        harness.validate(r, r.expiresAt, 100, MARKET);
    }

    function test_ExpiredAndWrongContextRejected() public {
        LayaRequest.Request memory r = fixture();
        vm.expectRevert(LayaRequest.Expired.selector);
        harness.validate(r, uint256(r.expiresAt) + 1, 100, MARKET);
        vm.expectRevert(LayaRequest.WrongContext.selector);
        harness.validate(r, NOW, 101, MARKET);
        vm.expectRevert(LayaRequest.WrongContext.selector);
        harness.validate(r, NOW, 100, address(0x5678));
        r.chainId = 0;
        vm.expectRevert(LayaRequest.WrongContext.selector);
        harness.validate(r, NOW, 0, MARKET);
    }

    function test_UnknownVersionsAndDecisionPolicyRejected() public {
        LayaRequest.Request memory r = fixture();
        r.version = 2;
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.version = 1;
        r.parserVersion = 3;
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.parserVersion = 1;
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.parserVersion = 2;
        r.decisionPolicy = 0;
        vm.expectRevert(LayaRequest.UnsupportedDecisionPolicy.selector);
        harness.validate(r, NOW, 100, MARKET);
    }

    function test_RequestRangesRejected() public {
        LayaRequest.Request memory r = fixture();
        r.thresholdPpm = 0;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.thresholdPpm = 1_000_001;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.thresholdPpm = 550_000;
        r.bodyLength = 0;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.bodyLength = 4097;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.bodyLength = 1;
        r.bodyOffset = 196608;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.bodyOffset = type(uint32).max;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.bodyOffset = 0;
        r.tokenCount = 0;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.tokenCount = r.model.maxTokens + 1;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.validate(r, NOW, 100, MARKET);
    }

    function test_AllRequestFieldsAndPinsIndividuallyChangeKey() public pure {
        LayaRequest.Request memory r = fixture();
        bytes32 original = LayaRequest.key(r);
        // Request and its nested ModelPins are entirely static ABI words. Mutate each
        // word independently (including every runtime pin, policy, threshold and nonce).
        bytes memory encoded = abi.encode(r);
        for (uint256 i; i < encoded.length / 32; ++i) {
            uint256 at = i * 32 + 31;
            encoded[at] ^= 0x01;
            LayaRequest.Request memory changed = abi.decode(encoded, (LayaRequest.Request));
            assertNotEq(original, LayaRequest.key(changed), "unbound request word");
            encoded[at] ^= 0x01;
        }
    }

    function test_MissingPinsRejectedIndividually() public {
        LayaRequest.Request memory r = fixture();
        bytes memory encoded = abi.encode(r);
        // Named commitment fields (all others are numeric/context fields).
        uint256[16] memory fields = [uint256(3), 4, 6, 7, 8, 10, 13, 14, 15, 17, 18, 19, 20, 21, 22, 23];
        for (uint256 i; i < fields.length; ++i) {
            uint256 field = fields[i];
            bytes32 old;
            assembly ("memory-safe") { old := mload(add(add(encoded, 32), mul(field, 32))) }
            assembly ("memory-safe") { mstore(add(add(encoded, 32), mul(field, 32)), 0) }
            LayaRequest.Request memory changed = abi.decode(encoded, (LayaRequest.Request));
            vm.expectRevert(LayaRequest.MissingCommitment.selector);
            harness.validate(changed, NOW, 100, MARKET);
            assembly ("memory-safe") { mstore(add(add(encoded, 32), mul(field, 32)), old) }
        }
    }

    function test_AlertSupportFlagsKeepBothQualifyingAndTies() public view {
        LayaRequest.Request memory r = fixture();
        r.decisionPolicy = LayaRequest.ALERT_STUDENT_BASE_SUPPORT_V1;
        r.thresholdPpm = 550_000;
        harness.validate(r, NOW, 100, MARKET);
        LayaRequest.SupportFlags memory flags = harness.flags(r, resultFor(r, 549_999, 549_999));
        assertFalse(flags.a);
        assertFalse(flags.b);
        flags = harness.flags(r, resultFor(r, 550_000, 549_999));
        assertTrue(flags.a);
        assertFalse(flags.b);
        flags = harness.flags(r, resultFor(r, 549_999, 550_000));
        assertFalse(flags.a);
        assertTrue(flags.b);
        flags = harness.flags(r, resultFor(r, 550_000, 550_000));
        assertTrue(flags.a);
        assertTrue(flags.b);
        flags = harness.flags(r, resultFor(r, 600_000, 800_000));
        assertTrue(flags.a);
        assertTrue(flags.b);
        flags = harness.flags(r, resultFor(r, 800_000, 600_000));
        assertTrue(flags.a);
        assertTrue(flags.b);
    }

    function test_AlertSupportRejectsOtherThresholdsProfilesAndRequests() public {
        LayaRequest.Request memory r = fixture();
        LayaRequest.Result memory result = resultFor(r, 600_000, 800_000);
        r.decisionPolicy = 1;
        result = resultFor(r, 600_000, 800_000);
        vm.expectRevert(LayaRequest.UnsupportedDecisionPolicy.selector);
        harness.flags(r, result);
        r.decisionPolicy = LayaRequest.ALERT_STUDENT_BASE_SUPPORT_V1;
        r.thresholdPpm = 400_000;
        result = resultFor(r, 600_000, 800_000);
        vm.expectRevert(LayaRequest.PolicyThresholdMismatch.selector);
        harness.flags(r, result);
        r.thresholdPpm = 700_000;
        vm.expectRevert(LayaRequest.PolicyThresholdMismatch.selector);
        harness.validate(r, NOW, 100, MARKET);
        r.thresholdPpm = 550_000;
        result = resultFor(r, 600_000, 800_000);
        r.nonce++;
        vm.expectRevert(LayaRequest.RequestMismatch.selector);
        harness.flags(r, result);
        r.nonce--;
        result.aPpm = 1_000_001;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.flags(r, result);
    }

    function testFuzz_AlertIndependentSupportFlags(uint32 a, uint32 b) public view {
        a = uint32(bound(a, 0, 1_000_000));
        b = uint32(bound(b, 0, 1_000_000));
        LayaRequest.Request memory r = fixture();
        r.decisionPolicy = LayaRequest.ALERT_STUDENT_BASE_SUPPORT_V1;
        r.thresholdPpm = 550_000;
        LayaRequest.SupportFlags memory flags = harness.flags(r, resultFor(r, a, b));
        assertEq(flags.a, a >= 550_000);
        assertEq(flags.b, b >= 550_000);
    }

    function test_ResultMismatchAndRangesRejected() public {
        LayaRequest.Request memory r = fixture();
        LayaRequest.Result memory result = resultFor(r, 550_000, 0);
        r.nonce++;
        vm.expectRevert(LayaRequest.RequestMismatch.selector);
        harness.flags(r, result);
        r.nonce--;
        result.version = 2;
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.flags(r, result);
        result.version = 1;
        result.aPpm = 1_000_001;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.flags(r, result);
        result.aPpm = 0;
        result.bPpm = 1_000_001;
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.flags(r, result);
        result.bPpm = 0;
        result.executionRoot = 0;
        vm.expectRevert(LayaRequest.MissingCommitment.selector);
        harness.flags(r, result);
        result.executionRoot = keccak256("root");
        r.version = 2;
        result.requestKey = LayaRequest.key(r);
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.flags(r, result);
    }

    function test_EveryResultFieldChangesCommitment() public pure {
        LayaRequest.Request memory r = fixture();
        LayaRequest.Result memory result = resultFor(r, 550_000, 0);
        bytes32 original = LayaRequest.resultKey(r, result);
        result.aPpm++;
        assertNotEq(original, LayaRequest.resultKey(r, result));
        result.aPpm--;
        result.bPpm++;
        assertNotEq(original, LayaRequest.resultKey(r, result));
        result.bPpm--;
        result.executionRoot = keccak256("other-root");
        assertNotEq(original, LayaRequest.resultKey(r, result));
        // Version/requestKey mutations are rejected by test_ResultMismatchAndRangesRejected.
    }

    function test_InputAndIdsCommitmentsRejectMutations() public {
        LayaRequest.Request memory r = fixture();
        bytes memory text = "rules+decoded-alert";
        uint32[] memory ids = new uint32[](3);
        ids[0] = 11;
        ids[1] = 22;
        ids[2] = 33;
        r.inputBytesHash = keccak256(text);
        r.tokenIdsHash = keccak256(abi.encode(ids));
        harness.input(r, text, ids);
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        harness.input(r, "other-input", ids);
        ids[1]++;
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        harness.input(r, text, ids);
        ids[1]--;
        r.tokenCount++;
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        harness.input(r, text, ids);
    }

    function bodyFixture() private pure returns (LayaRequest.Request memory r, EmailProof memory p) {
        r = fixture();
        bytes memory prefix = bytes(
            "--laya-alert-fixture\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\nSGVsbG8=\r\n"
            "--laya-alert-fixture\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
        );
        bytes memory encoded = "<h3>Headline</h3><p>Completed=20event.</p>";
        p.canonicalBody = bytes.concat(prefix, encoded, "\r\n--laya-alert-fixture--\r\n");
        p.bodyOffset = prefix.length;
        p.bodyLength = encoded.length;
        p.bodyExcerpt = "<h3>Headline</h3><p>Completed event.</p>";
        p.header = bytes(
            string.concat(
                'content-type:multipart/alternative; boundary="laya-alert-fixture"',
                "\r\ndkim-signature:c=relaxed/relaxed; bh=",
                vm.toBase64(abi.encodePacked(sha256(p.canonicalBody))),
                "; h=content-type; b="
            )
        );
        p.signature = hex"010203"; // Deliberately NOT RSA: validates the scaffold's trust boundary.
        p.emailNullifier = keccak256(p.signature);
        r.emailHash = keccak256(abi.encode(p));
        r.emailNullifier = p.emailNullifier;
        r.canonicalBodySha256 = sha256(p.canonicalBody);
        r.bodyOffset = uint32(p.bodyOffset);
        r.bodyLength = uint32(p.bodyLength);
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
    }

    function test_EvidenceBindingAloneIsExplicitlyNotRSAAuthentication() public view {
        (LayaRequest.Request memory r, EmailProof memory p) = bodyFixture();
        harness.evidence(r, p);
    }

    function test_AlertEvidenceRejectsOtherParserVersions() public {
        (LayaRequest.Request memory r, EmailProof memory p) = bodyFixture();
        r.parserVersion = 1;
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.evidence(r, p);
        r.parserVersion = 3;
        vm.expectRevert(LayaRequest.BadVersion.selector);
        harness.evidence(r, p);
    }

    function test_WindowOutsideHtmlRejectedEvenIfRecommitted() public {
        (LayaRequest.Request memory r, EmailProof memory p) = bodyFixture();
        p.bodyOffset = 0;
        p.bodyLength = 20;
        p.bodyExcerpt = "--laya-alert-fixture";
        r.emailHash = keccak256(abi.encode(p));
        r.bodyOffset = 0;
        r.bodyLength = 20;
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
    }

    function test_UnsupportedSinglePartRejectedEvenIfRecommitted() public {
        (LayaRequest.Request memory r, EmailProof memory p) = bodyFixture();
        p.canonicalBody = "Completed event.\r\n";
        p.bodyOffset = 0;
        p.bodyLength = p.canonicalBody.length;
        p.bodyExcerpt = string(p.canonicalBody);
        p.header = bytes(
            string.concat(
                "content-type:text/plain; charset=utf-8\r\ndkim-signature:c=relaxed/relaxed; bh=",
                vm.toBase64(abi.encodePacked(sha256(p.canonicalBody))),
                "; h=content-type; b="
            )
        );
        r.emailHash = keccak256(abi.encode(p));
        r.canonicalBodySha256 = sha256(p.canonicalBody);
        r.bodyOffset = 0;
        r.bodyLength = uint32(p.bodyLength);
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
    }

    function test_ForgedExcerptAndChangedBodyRejectedEvenWithRecommittedEmail() public {
        (LayaRequest.Request memory r, EmailProof memory p) = bodyFixture();
        p.bodyExcerpt = "Forged event";
        r.emailHash = keccak256(abi.encode(p));
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
        (r, p) = bodyFixture();
        p.canonicalBody[0] = "X";
        r.emailHash = keccak256(abi.encode(p));
        r.canonicalBodySha256 = sha256(p.canonicalBody);
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
    }

    function test_EmailMetadataWindowAndNullifierMutationsRejected() public {
        (LayaRequest.Request memory r, EmailProof memory p) = bodyFixture();
        p.timestamp++;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
        p.timestamp--;
        p.domainName = "another-domain.example";
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
        p.domainName = "";
        p.bodyOffset = 1;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
        (r, p) = bodyFixture();
        p.emailNullifier = keccak256("forged");
        r.emailHash = keccak256(abi.encode(p));
        r.emailNullifier = p.emailNullifier;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        harness.evidence(r, p);
    }

    function testFuzz_OutOfRangeScoresRejected(uint32 score, bool useA) public {
        score = uint32(bound(score, 1_000_001, type(uint32).max));
        LayaRequest.Request memory r = fixture();
        LayaRequest.Result memory result = resultFor(r, useA ? score : 0, useA ? 0 : score);
        vm.expectRevert(LayaRequest.BadRange.selector);
        harness.flags(r, result);
    }
}
