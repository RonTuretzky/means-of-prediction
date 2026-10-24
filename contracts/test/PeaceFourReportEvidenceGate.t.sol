// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {PeaceFourReportEvidenceGate} from "../src/judge/PeaceFourReportEvidenceGate.sol";

/// @dev Genuine Google RSA success path; no verifier mock or caller-supplied verdict.
/// Historical vm.warp is explicit. No live deployment, inference certificate or payout.
contract PeaceFourReportEvidenceGateTest is Test {
    bytes32 private constant PROFILE = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 private constant FIXTURE_SHA256 =
        0x0c409ee7a6c16f4629f42101d0c9aa99135b7ce4ec7176e7d3a816ac28d33d7b;
    DKIMRegistry private registry;
    DKIMVerifier private verifier;
    PeaceFourReportEvidenceGate private gate;
    bytes32 private gateDomain;
    EmailProof[] private proofs;
    LayaRequest.Request[] private requests;
    bytes[] private inputs;
    uint32[][] private ids;
    bytes private exponent;
    bytes private modulus;
    uint256[] private signedAt;
    uint256[] private expiresAt;
    uint256 private historicalTime;
    uint256 private currentTime;

    error DeliberateConsumerFailure();

    function setUp() public {
        string memory path = vm.envOr("LAYA_PEACE_FOUR_GATE_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "LAYA_PEACE_FOUR_GATE_FIXTURE absent; genuine RSA suite not run");
            return;
        }
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory raw = vm.ffi(command);
        assertEq(sha256(raw), FIXTURE_SHA256, "genuine frozen fixture changed");
        emit log_named_bytes32("Peace four-report genuine fixture JSON SHA256", sha256(raw));
        string memory fixture = string(raw);
        (proofs, exponent, modulus, inputs, ids, requests) = abi.decode(
            vm.parseJsonBytes(fixture, ".abiHex"),
            (EmailProof[], bytes, bytes, bytes[], uint32[][], LayaRequest.Request[])
        );
        signedAt = vm.parseJsonUintArray(fixture, ".signedAtUnix");
        expiresAt = vm.parseJsonUintArray(fixture, ".expiresAtUnix");
        historicalTime = vm.parseJsonUint(fixture, ".validationTimeUnix");
        currentTime = vm.parseJsonUint(fixture, ".currentTimeUnix");
        assertEq(vm.parseJsonBytes32(fixture, ".profileSHA256"), PROFILE);
        assertEq(proofs.length, 4);
        assertEq(inputs.length, 4);
        assertEq(ids.length, 4);
        assertEq(requests.length, 4);
        vm.chainId(requests[0].chainId);
        vm.warp(historicalTime);
        // Bind the local test consumer address, never change frozen evidence/input pins.
        for (uint256 i; i < 4; ++i) {
            requests[i].market = address(this);
            assertEq(requests[i].sourceIndex, i);
            assertGe(historicalTime, signedAt[i]);
            assertLe(historicalTime, expiresAt[i]);
            assertGt(requests[i].expiresAt, maxExpiry());
            assertEq(keccak256(abi.encode(proofs[i])), requests[i].emailHash);
            assertEq(sha256(proofs[i].canonicalBody), requests[i].canonicalBodySha256);
            assertEq(keccak256(inputs[i]), requests[i].inputBytesHash);
            assertEq(keccak256(abi.encode(ids[i])), requests[i].tokenIdsHash);
        }
        uint256[4] memory sizes = [uint256(20461), 44557, 28521, 39678];
        for (uint256 i; i < 4; ++i) assertEq(proofs[i].canonicalBody.length, sizes[i]);
        registry = new DKIMRegistry();
        assertEq(registry.registerKey("google.com", "20251104", exponent, modulus), proofs[0].publicKeyHash);
        verifier = new DKIMVerifier(registry);
        gate = newGate(verifier, requests);
        gateDomain = gate.requestDomain();
    }

    function maxExpiry() private view returns (uint256 n) {
        for (uint256 i; i < expiresAt.length; ++i) if (expiresAt[i] > n) n = expiresAt[i];
    }

    function newGate(DKIMVerifier v, LayaRequest.Request[] memory r) private returns (PeaceFourReportEvidenceGate) {
        return new PeaceFourReportEvidenceGate(v, address(this), proofs[0].publicKeyHash, PROFILE, r);
    }

    function verifyAt(uint256 i) private view returns (bytes32 key, uint8 group) {
        return gate.verifyEvidence(gateDomain, requests[i], proofs[i], inputs[i], ids[i]);
    }

    function consumeBundle() private returns (bytes32 receipt) {
        return gate.consumeBundle(gateDomain, requests, proofs, inputs, ids);
    }
    function verifyBundle() private view returns (bytes32 receipt) {
        return gate.verifyBundle(gateDomain, requests, proofs, inputs, ids);
    }
    function rebind(LayaRequest.Request memory r, EmailProof memory p) private pure returns (LayaRequest.Request memory) {
        r.emailHash = keccak256(abi.encode(p));
        r.emailNullifier = p.emailNullifier;
        r.canonicalBodySha256 = sha256(p.canonicalBody);
        r.bodyOffset = uint32(p.bodyOffset);
        r.bodyLength = uint32(p.bodyLength);
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
        return r;
    }

    function test_GenuineRSAAndCompleteBodiesForAllFourNamedReports() public {
        for (uint256 i; i < 4; ++i) {
            EmailProof memory headerOnly = proofs[i];
            headerOnly.canonicalBody = "";
            headerOnly.bodyExcerpt = "";
            headerOnly.bodyOffset = 0;
            headerOnly.bodyLength = 0;
            uint256 before = gasleft();
            assertTrue(verifier.verify(headerOnly), "genuine RSA failed");
            emit log_named_uint(string.concat("Peace report RSA header gas index ", vm.toString(i)), before - gasleft());
            before = gasleft();
            (bytes32 key, uint8 group) = verifyAt(i);
            emit log_named_uint(string.concat("Peace report full-body view gas index ", vm.toString(i)), before - gasleft());
            assertEq(key, LayaRequest.key(requests[i]));
            assertEq(group, i);
            (bool allowed, uint8 storedGroup, uint8 variant) = gate.frozenRequestKeys(key);
            assertTrue(allowed);
            assertEq(storedGroup, group);
            assertEq(variant, i);
        }
        assertEq(gate.consumedSourceMask(), 0, "view verification must not consume evidence");
    }

    /// @dev Control-flow harness only: no caller-supplied scores or inference claim.
    function test_ExactReviewedPacketCanBeConsumedOnlyAsOneAtomicBundle() public {
        assertEq(gate.SOURCE_POLICY_FILE_SHA256(),
            0x464871658b2543c7cfd2fac61ecaf84ec32e437a06265dd12e648ea2750ea3a2);
        uint256 before = gasleft();
        bytes32 receipt = consumeBundle();
        emit log_named_uint("Peace exact four-report consumeBundle gas", before - gasleft());
        assertTrue(receipt != 0); assertEq(gate.consumedSourceMask(), 15);
        for (uint256 i; i < 4; ++i) {
            assertTrue(gate.consumedRequests(LayaRequest.key(requests[i])));
            assertTrue(gate.consumedEmails(proofs[i].emailNullifier));
        }
        verifyBundle(); // View authentication remains available after consumption.
    }
    function test_MissingUnknownDuplicateAndReorderedPacketRejected() public {
        LayaRequest.Request[] memory short = new LayaRequest.Request[](3);
        for (uint256 i; i < 3; ++i) short[i] = requests[i];
        vm.expectRevert(PeaceFourReportEvidenceGate.BadBundle.selector);
        gate.verifyBundle(gateDomain, short, proofs, inputs, ids);
        LayaRequest.Request[] memory rr = requests; ++rr[3].nonce;
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongFrozenRequest.selector);
        gate.verifyBundle(gateDomain, rr, proofs, inputs, ids);
        rr = requests; EmailProof[] memory pp = proofs; bytes[] memory ii = inputs; uint32[][] memory tt = ids;
        rr[1] = rr[0]; pp[1] = pp[0]; ii[1] = ii[0]; tt[1] = tt[0];
        vm.expectRevert(PeaceFourReportEvidenceGate.BadBundle.selector);
        gate.verifyBundle(gateDomain, rr, pp, ii, tt);
        rr = requests; pp = proofs; ii = inputs; tt = ids;
        (rr[0],rr[1])=(rr[1],rr[0]); (pp[0],pp[1])=(pp[1],pp[0]);
        (ii[0],ii[1])=(ii[1],ii[0]); (tt[0],tt[1])=(tt[1],tt[0]);
        vm.expectRevert(PeaceFourReportEvidenceGate.BadBundle.selector);
        gate.verifyBundle(gateDomain, rr, pp, ii, tt);
        assertEq(gate.consumedSourceMask(), 0);
    }
    function test_ReplayRejected() public {
        consumeBundle(); vm.expectRevert(PeaceFourReportEvidenceGate.AlreadyConsumed.selector); consumeBundle();
    }

    function test_OnlyConsumerCanConsume() public {
        bytes32 domain = gateDomain;
        vm.prank(address(0xBAD));
        vm.expectRevert(PeaceFourReportEvidenceGate.NotConsumer.selector);
        gate.consumeBundle(domain, requests, proofs, inputs, ids);
    }

    function consumeThenFail() external {
        consumeBundle();
        revert DeliberateConsumerFailure();
    }

    function test_LaterConsumerFailureRollsBackAllConsumption() public {
        vm.expectRevert(DeliberateConsumerFailure.selector);
        this.consumeThenFail();
        assertFalse(gate.consumedRequests(LayaRequest.key(requests[0])));
        assertFalse(gate.consumedEmails(proofs[0].emailNullifier));
        assertEq(gate.consumedSourceMask(), 0);
    }

    function test_FailedLastProofDoesNotPartiallyConsumePacket() public {
        EmailProof[] memory pp = proofs; pp[3].canonicalBody[pp[3].canonicalBody.length - 8] ^= 0x01;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        gate.consumeBundle(gateDomain, requests, pp, inputs, ids);
        assertEq(gate.consumedSourceMask(), 0);
        for (uint256 i; i < 4; ++i) {
            assertFalse(gate.consumedRequests(LayaRequest.key(requests[i])));
            assertFalse(gate.consumedEmails(proofs[i].emailNullifier));
        }
    }
    function test_FailedInputDoesNotConsumeThenValidInputSucceeds() public {
        bytes[] memory bad = inputs; bad[2] = bytes("bad input");
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.consumeBundle(gateDomain, requests, proofs, bad, ids);
        assertEq(gate.consumedSourceMask(), 0); consumeBundle(); assertEq(gate.consumedSourceMask(), 15);
    }

    function test_ChangedHeaderAndIndependentSubjectRejected() public {
        EmailProof memory p = proofs[0];
        // Keep all required field names/tags well formed, so real RSA must reject
        // changed signed bytes rather than failing an earlier structural check.
        p.header = replaced(p.header, "subject:", "subject:X");
        vm.expectRevert(PeaceFourReportEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        p.subject = "an independently provided subject proof cannot replace the authenticated field";
        vm.expectRevert(PeaceFourReportEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
    }

    function test_ChangedBodyOutsideWindowRejectedEvenWhenRecommitted() public {
        EmailProof memory p = proofs[1]; p.canonicalBody[p.canonicalBody.length - 8] ^= 0x01;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        gate.verifyEvidence(gateDomain, requests[1], p, inputs[1], ids[1]);
        LayaRequest.Request[] memory rr = requests; rr[1] = rebind(rr[1], p);
        vm.expectRevert(PeaceFourReportEvidenceGate.BadConfiguration.selector); newGate(verifier, rr);
    }
    function test_CrossEmailBodyCannotBorrowGenuineHeader() public {
        EmailProof memory p = proofs[0]; p.canonicalBody = proofs[1].canonicalBody;
        p.bodyExcerpt = proofs[1].bodyExcerpt; p.bodyOffset = proofs[1].bodyOffset; p.bodyLength = proofs[1].bodyLength;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
    }
    function test_ChangedExcerptOffsetAndLengthRejected() public {
        for (uint256 i; i < 3; ++i) {
            EmailProof memory p = proofs[2];
            if (i == 0) p.bodyExcerpt = "fabricated winner";
            if (i == 1) ++p.bodyOffset;
            if (i == 2) --p.bodyLength;
            vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
            gate.verifyEvidence(gateDomain, requests[2], p, inputs[2], ids[2]);
        }
    }
    function test_OversizedAndCroppedBodyRejectedWithoutFallback() public {
        for (uint256 i; i < 2; ++i) {
            EmailProof memory p = proofs[3];
            if (i == 0) p.canonicalBody = new bytes(196609);
            else {bytes memory body = p.canonicalBody; assembly ("memory-safe") {mstore(body, sub(mload(body), 8))} p.canonicalBody = body;}
            vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
            gate.verifyEvidence(gateDomain, requests[3], p, inputs[3], ids[3]);
        }
    }

    function test_WrongGoogleIdentityKeyAndRevocationRejected() public {
        EmailProof memory p = proofs[0];
        p.publicKeyHash ^= bytes32(uint256(1));
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongGoogleIdentity.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        p.domainName = "attacker.example";
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongGoogleIdentity.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        p.fromAddress = "attacker@google.com";
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongGoogleIdentity.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        registry.revokeKey("google.com", proofs[0].publicKeyHash);
        vm.expectRevert(PeaceFourReportEvidenceGate.BadRSA.selector);
        verifyAt(0);
    }

    function test_RegistryWithWrongRSAExponentCannotAuthenticate() public {
        DKIMRegistry wrong = new DKIMRegistry();
        wrong.registerKey("google.com", "20251104", hex"03", modulus);
        PeaceFourReportEvidenceGate altered = newGate(new DKIMVerifier(wrong), requests);
        bytes32 alteredDomain = altered.requestDomain();
        vm.expectRevert(PeaceFourReportEvidenceGate.BadRSA.selector);
        altered.verifyEvidence(alteredDomain, requests[0], proofs[0], inputs[0], ids[0]);
    }

    function test_WrongMarketChainAndRequestDomainRejected() public {
        LayaRequest.Request memory r = requests[0];
        r.market = address(0xBAD);
        vm.expectRevert(LayaRequest.WrongContext.selector);
        gate.verifyEvidence(gateDomain, r, proofs[0], inputs[0], ids[0]);
        r = requests[0];
        ++r.chainId;
        vm.expectRevert(LayaRequest.WrongContext.selector);
        gate.verifyEvidence(gateDomain, r, proofs[0], inputs[0], ids[0]);
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongDomain.selector);
        gate.verifyEvidence(bytes32(uint256(1)), requests[0], proofs[0], inputs[0], ids[0]);
        PeaceFourReportEvidenceGate other = newGate(verifier, requests);
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongDomain.selector);
        other.verifyEvidence(gateDomain, requests[0], proofs[0], inputs[0], ids[0]);
        bytes32 oldChainDomain = gateDomain;
        vm.chainId(block.chainid + 1);
        vm.expectRevert(PeaceFourReportEvidenceGate.WrongDomain.selector);
        gate.verifyEvidence(oldChainDomain, requests[0], proofs[0], inputs[0], ids[0]);
    }

    function test_AllRequestPolicyPinsAndNonceFrozen() public {
        bytes memory encoded = abi.encode(requests[0]);
        for (uint256 i; i < encoded.length / 32; ++i) {
            encoded[i * 32 + 31] ^= 0x01;
            LayaRequest.Request memory r = abi.decode(encoded, (LayaRequest.Request));
            vm.expectRevert();
            gate.verifyEvidence(gateDomain, r, proofs[0], inputs[0], ids[0]);
            encoded[i * 32 + 31] ^= 0x01;
        }
    }

    function test_TokenMutationRejected() public {
        uint32[] memory changed = ids[0];
        ++changed[0];
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.verifyEvidence(gateDomain, requests[0], proofs[0], inputs[0], changed);
    }

    function test_AllFourMustBeValidAtOneClockIncludingExpiryBoundaries() public {
        uint256 commonStart; uint256 commonEnd = type(uint256).max;
        for (uint256 i; i < 4; ++i) {
            if (signedAt[i] > commonStart) commonStart = signedAt[i];
            if (expiresAt[i] < commonEnd) commonEnd = expiresAt[i];
        }
        assertEq(commonStart, 1792292308); assertEq(commonEnd, 1792599289);
        vm.warp(commonStart); verifyBundle(); vm.warp(commonEnd); verifyBundle();
        vm.warp(commonStart - 1); vm.expectRevert(PeaceFourReportEvidenceGate.SignatureOutsideValidity.selector); verifyBundle();
        vm.warp(commonEnd + 1); vm.expectRevert(PeaceFourReportEvidenceGate.SignatureOutsideValidity.selector); verifyBundle();
    }
    function test_CurrentSnapshotValidButLaterFinalizationCannotUseStaleObservation() public {
        vm.warp(currentTime); verifyBundle();
        vm.warp(expiresAt[1] + 1);
        vm.expectRevert(PeaceFourReportEvidenceGate.SignatureOutsideValidity.selector); consumeBundle();
        assertEq(gate.consumedSourceMask(), 0);
    }

    function test_RequestExpiryRejected() public {
        vm.warp(uint256(requests[0].expiresAt) + 1);
        vm.expectRevert(LayaRequest.Expired.selector);
        verifyAt(0);
    }

    function replaced(bytes memory source, bytes memory needle, bytes memory replacement) private pure returns (bytes memory) {
        for (uint256 i; i + needle.length <= source.length; ++i) {
            bool equal = true;
            for (uint256 j; j < needle.length; ++j) if (source[i + j] != needle[j]) equal = false;
            if (!equal) continue;
            bytes memory result = new bytes(source.length - needle.length + replacement.length);
            for (uint256 j; j < i; ++j) result[j] = source[j];
            for (uint256 j; j < replacement.length; ++j) result[i + j] = replacement[j];
            for (uint256 j = i + needle.length; j < source.length; ++j) result[i + replacement.length + j - i - needle.length] = source[j];
            return result;
        }
        revert("fixture needle missing");
    }

    function test_MissingSignedRequiredFieldDuplicateHeaderSelectorAndTimestampTagsRejected() public {
        for (uint256 i; i < 4; ++i) {
            EmailProof memory p = proofs[0];
            if (i == 0) p.header = replaced(p.header, ":mime-version:", ":xime-version:");
            if (i == 1) p.header = bytes.concat(bytes("subject:duplicate\r\n"), p.header);
            if (i == 2) p.header = replaced(p.header, "s=20251104", "s=20251105");
            if (i == 3) p.header = bytes.concat(p.header, ";t=1");
            vm.expectRevert(PeaceFourReportEvidenceGate.BadHeaderPolicy.selector);
            gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        }
    }

    function test_NullifierAndClaimedDateCannotBeChanged() public {
        EmailProof memory p = proofs[0];
        p.emailNullifier ^= bytes32(uint256(1));
        vm.expectRevert(PeaceFourReportEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        ++p.timestamp;
        vm.expectRevert(PeaceFourReportEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
    }

    function test_ConfigurationRejectsWrongProfileModelSourceGroupOrPolicy() public {
        vm.expectRevert(PeaceFourReportEvidenceGate.BadConfiguration.selector);
        new PeaceFourReportEvidenceGate(verifier, address(this), proofs[0].publicKeyHash, bytes32(uint256(1)), requests);
        LayaRequest.Request[] memory rr = requests;
        rr[2].sourceIndex = 1;
        vm.expectRevert(PeaceFourReportEvidenceGate.BadConfiguration.selector);
        newGate(verifier, rr);
        rr = requests;
        rr[1].sourcePolicyHash ^= bytes32(uint256(1));
        vm.expectRevert(PeaceFourReportEvidenceGate.BadConfiguration.selector);
        newGate(verifier, rr);
        rr = requests;
        rr[0].model.weights ^= bytes32(uint256(1));
        vm.expectRevert(PeaceFourReportEvidenceGate.BadConfiguration.selector);
        newGate(verifier, rr);
    }
}
