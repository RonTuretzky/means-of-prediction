// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {PeaceBBCAlertEvidenceGate} from "../src/judge/PeaceBBCAlertEvidenceGate.sol";

/// @dev Genuine frozen Google RSA and complete-body fixture; no verifier mock or scores.
contract PeaceBBCAlertEvidenceGateTest is Test {
    bytes32 private constant PROFILE = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 private constant FIXTURE_SHA256 =
        0x6fffae4d298c6fd4431a5828f99cad62ebb503d288da87bc64e3b2a24e99f030;
    DKIMRegistry private registry;
    DKIMVerifier private verifier;
    PeaceBBCAlertEvidenceGate private gate;
    bytes32 private domain;
    EmailProof private proof;
    LayaRequest.Request private request;
    bytes private exactInput;
    uint32[] private ids;
    bytes private exponent;
    bytes private modulus;
    uint256 private signedAt;
    uint256 private expiresAt;
    uint256 private currentTime;
    error DeliberateConsumerFailure();

    function setUp() public {
        string memory path = vm.envOr("LAYA_PEACE_GATE_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "LAYA_PEACE_GATE_FIXTURE absent; genuine RSA suite not run");
            return;
        }
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory raw = vm.ffi(command);
        assertTrue(FIXTURE_SHA256 != 0, "new fixture not yet pinned; no success claim");
        assertEq(sha256(raw), FIXTURE_SHA256, "frozen genuine fixture changed");
        string memory fixture = string(raw);
        (proof, exponent, modulus, exactInput, ids, request) = abi.decode(vm.parseJsonBytes(fixture, ".abiHex"),
            (EmailProof, bytes, bytes, bytes, uint32[], LayaRequest.Request));
        signedAt = vm.parseJsonUint(fixture, ".signedAtUnix");
        expiresAt = vm.parseJsonUint(fixture, ".expiresAtUnix");
        currentTime = vm.parseJsonUint(fixture, ".currentTimeUnix");
        assertEq(vm.parseJsonBytes32(fixture, ".profileSHA256"), PROFILE);
        vm.chainId(request.chainId);
        vm.warp(vm.parseJsonUint(fixture, ".validationTimeUnix"));
        request.market = address(this); // Only local consumer context rebound.
        assertGe(block.timestamp, signedAt);
        assertLe(block.timestamp, expiresAt);
        assertGt(request.expiresAt, expiresAt);
        assertEq(proof.canonicalBody.length, 20461);
        assertEq(sha256(proof.header), 0x21d51e434d69f0e402759041b46d92fc792cf4953425243169ee8bae3645fa43);
        assertEq(sha256(proof.canonicalBody), 0xef09cd6700414ff97c243c6c7b564b457c19db3efdc26a0e84033bd033e939b4);
        assertEq(proof.bodyOffset, 8078);
        assertEq(proof.bodyLength, 1265);
        assertEq(keccak256(abi.encode(proof)), request.emailHash);
        assertEq(keccak256(exactInput), request.inputBytesHash);
        assertEq(keccak256(abi.encode(ids)), request.tokenIdsHash);
        registry = new DKIMRegistry();
        assertEq(registry.registerKey("google.com", "20251104", exponent, modulus), proof.publicKeyHash);
        verifier = new DKIMVerifier(registry);
        gate = newGate(verifier, request);
        domain = gate.requestDomain();
    }

    function newGate(DKIMVerifier v, LayaRequest.Request memory r) private returns (PeaceBBCAlertEvidenceGate) {
        return new PeaceBBCAlertEvidenceGate(v, address(this), proof.publicKeyHash, PROFILE, r);
    }
    function verify() private view returns (bytes32 key, uint8 group) {
        return gate.verifyEvidence(domain, request, proof, exactInput, ids);
    }
    function consume() private returns (bytes32 receipt, uint8 group) {
        return gate.consumeEvidence(domain, request, proof, exactInput, ids);
    }

    function test_GenuineRSAAndOriginalCompleteBBCBody() public {
        EmailProof memory headerOnly = proof;
        headerOnly.canonicalBody = ""; headerOnly.bodyExcerpt = ""; headerOnly.bodyOffset = 0; headerOnly.bodyLength = 0;
        uint256 before = gasleft();
        assertTrue(verifier.verify(headerOnly), "genuine RSA failed");
        emit log_named_uint("Peace BBC RSA header gas", before - gasleft());
        before = gasleft();
        (bytes32 key, uint8 group) = verify();
        emit log_named_uint("Peace BBC complete-body gate view gas", before - gasleft());
        assertEq(key, LayaRequest.key(request)); assertEq(group, 0);
        assertEq(gate.consumedSourceMask(), 0);
    }
    function test_OneBBCObservationDoesNotEstablishOriginalSourceRule() public {
        assertFalse(gate.originalRuleSourceAdmissionEstablished());
        assertEq(gate.MARKET_ID(), 5371292);
        consume();
        assertFalse(gate.originalRuleSourceAdmissionEstablished());
        assertEq(gate.consumedSourceMask(), 1); // Only an observation receipt bit.
        verify(); // Authentication view remains available after consumption.
    }
    function test_ObservationReplayRejected() public {
        consume();
        vm.expectRevert(PeaceBBCAlertEvidenceGate.AlreadyConsumed.selector);
        consume();
    }
    function test_OnlyConfiguredConsumerCanConsume() public {
        vm.prank(address(0xBAD)); vm.expectRevert(PeaceBBCAlertEvidenceGate.NotConsumer.selector);
        gate.consumeEvidence(domain, request, proof, exactInput, ids);
    }
    function consumeThenFail() external { consume(); revert DeliberateConsumerFailure(); }
    function test_LaterConsumerFailureRollsBackObservation() public {
        vm.expectRevert(DeliberateConsumerFailure.selector); this.consumeThenFail();
        assertFalse(gate.consumedRequests(LayaRequest.key(request)));
        assertFalse(gate.consumedEmails(proof.emailNullifier)); assertEq(gate.consumedSourceMask(), 0);
    }
    function test_FailedInputDoesNotConsumeThenCorrectInputSucceeds() public {
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.consumeEvidence(domain, request, proof, bytes("bad input"), ids);
        assertEq(gate.consumedSourceMask(), 0); consume(); assertEq(gate.consumedSourceMask(), 1);
    }
    function test_ChangedSignedHeaderAndIndependentSubjectRejected() public {
        EmailProof memory p = proof; p.header = replaced(p.header, "subject:", "subject:X");
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
        p = proof; p.subject = "independent subject proof";
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
    }
    function test_ChangedFarBodyTailCannotBorrowAuthenticatedHeader() public {
        EmailProof memory p = proof; p.canonicalBody[p.canonicalBody.length - 8] ^= 0x01;
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
        LayaRequest.Request memory r = request; r.canonicalBodySha256 = sha256(p.canonicalBody);
        r.emailHash = keccak256(abi.encode(p));
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadConfiguration.selector); newGate(verifier, r);
    }
    function test_ChangedExcerptOffsetAndLengthRejected() public {
        for (uint256 i; i < 3; ++i) {
            EmailProof memory p = proof;
            if (i == 0) p.bodyExcerpt = "fabricated named laureate";
            if (i == 1) ++p.bodyOffset;
            if (i == 2) --p.bodyLength;
            vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
            gate.verifyEvidence(domain, request, p, exactInput, ids);
        }
    }
    function test_OversizedAndCroppedBodyRejectedWithoutFallback() public {
        for (uint256 i; i < 2; ++i) {
            EmailProof memory p = proof;
            if (i == 0) p.canonicalBody = new bytes(196609);
            else {bytes memory body = p.canonicalBody; assembly ("memory-safe") {mstore(body, sub(mload(body), 8))} p.canonicalBody = body;}
            vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
            gate.verifyEvidence(domain, request, p, exactInput, ids);
        }
    }
    function test_WrongGoogleIdentityAndRevokedKeyRejected() public {
        for (uint256 i; i < 3; ++i) {
            EmailProof memory p = proof;
            if (i == 0) p.publicKeyHash ^= bytes32(uint256(1));
            if (i == 1) p.domainName = "attacker.example";
            if (i == 2) p.fromAddress = "attacker@google.com";
            vm.expectRevert(PeaceBBCAlertEvidenceGate.WrongGoogleIdentity.selector);
            gate.verifyEvidence(domain, request, p, exactInput, ids);
        }
        registry.revokeKey("google.com", proof.publicKeyHash);
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadRSA.selector); verify();
    }
    function test_WrongRegisteredRSAExponentRejected() public {
        DKIMRegistry wrong = new DKIMRegistry(); wrong.registerKey("google.com", "20251104", hex"03", modulus);
        PeaceBBCAlertEvidenceGate altered = newGate(new DKIMVerifier(wrong), request);
        bytes32 d = altered.requestDomain(); vm.expectRevert(PeaceBBCAlertEvidenceGate.BadRSA.selector);
        altered.verifyEvidence(d, request, proof, exactInput, ids);
    }
    function test_WrongConsumerChainAndInstanceDomainRejected() public {
        LayaRequest.Request memory r = request; r.market = address(0xBAD);
        vm.expectRevert(LayaRequest.WrongContext.selector); gate.verifyEvidence(domain, r, proof, exactInput, ids);
        r = request; ++r.chainId;
        vm.expectRevert(LayaRequest.WrongContext.selector); gate.verifyEvidence(domain, r, proof, exactInput, ids);
        vm.expectRevert(PeaceBBCAlertEvidenceGate.WrongDomain.selector);
        gate.verifyEvidence(bytes32(uint256(1)), request, proof, exactInput, ids);
        PeaceBBCAlertEvidenceGate other = newGate(verifier, request);
        vm.expectRevert(PeaceBBCAlertEvidenceGate.WrongDomain.selector);
        other.verifyEvidence(domain, request, proof, exactInput, ids);
        vm.chainId(block.chainid + 1); vm.expectRevert(PeaceBBCAlertEvidenceGate.WrongDomain.selector); verify();
    }
    function test_EveryRequestPolicyPinAndNonceFrozen() public {
        bytes memory encoded = abi.encode(request);
        for (uint256 i; i < encoded.length / 32; ++i) {
            encoded[i * 32 + 31] ^= 0x01; LayaRequest.Request memory r = abi.decode(encoded, (LayaRequest.Request));
            vm.expectRevert(); gate.verifyEvidence(domain, r, proof, exactInput, ids); encoded[i * 32 + 31] ^= 0x01;
        }
    }
    function test_TokenMutationRejected() public {
        uint32[] memory changed = ids; ++changed[0]; vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.verifyEvidence(domain, request, proof, exactInput, changed);
    }
    function test_InclusiveSignedValidityBoundariesAndExpiryRejection() public {
        vm.warp(signedAt); verify(); vm.warp(expiresAt); verify();
        vm.warp(signedAt - 1); vm.expectRevert(PeaceBBCAlertEvidenceGate.SignatureOutsideValidity.selector); verify();
        vm.warp(expiresAt + 1); vm.expectRevert(PeaceBBCAlertEvidenceGate.SignatureOutsideValidity.selector); verify();
    }
    function test_FrozenWallClockClassifiedHonestly() public {
        vm.warp(currentTime);
        if (currentTime >= signedAt && currentTime <= expiresAt) verify();
        else {vm.expectRevert(PeaceBBCAlertEvidenceGate.SignatureOutsideValidity.selector); verify();}
        assertFalse(gate.originalRuleSourceAdmissionEstablished());
    }
    function test_RequestExpiryIndependentOfDKIMExpiry() public {
        vm.warp(uint256(request.expiresAt) + 1); vm.expectRevert(LayaRequest.Expired.selector); verify();
    }
    function test_RequiredSignedFieldsSelectorAndDuplicateTagsRejected() public {
        for (uint256 i; i < 4; ++i) {
            EmailProof memory p = proof;
            if (i == 0) p.header = replaced(p.header, ":mime-version:", ":xime-version:");
            if (i == 1) p.header = bytes.concat(bytes("subject:duplicate\r\n"), p.header);
            if (i == 2) p.header = replaced(p.header, "s=20251104", "s=20251105");
            if (i == 3) p.header = bytes.concat(p.header, ";t=1");
            vm.expectRevert(PeaceBBCAlertEvidenceGate.BadHeaderPolicy.selector);
            gate.verifyEvidence(domain, request, p, exactInput, ids);
        }
    }
    function test_ExactTimestampTagsCannotBeReplaced() public {
        EmailProof memory p = proof; p.header = replaced(p.header, "t=1792292308", "t=1792292307");
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadHeaderPolicy.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
        p = proof; p.header = replaced(p.header, "x=1792897108", "x=1792897109");
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadHeaderPolicy.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
    }
    function test_ClaimedDateAndNullifierCannotChange() public {
        EmailProof memory p = proof; ++p.timestamp; vm.expectRevert(PeaceBBCAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
        p = proof; p.emailNullifier ^= bytes32(uint256(1)); vm.expectRevert(PeaceBBCAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(domain, request, p, exactInput, ids);
    }
    function test_ConstructorRejectsWrongProfileSourceOrModel() public {
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadConfiguration.selector);
        new PeaceBBCAlertEvidenceGate(verifier, address(this), proof.publicKeyHash, bytes32(uint256(1)), request);
        LayaRequest.Request memory r = request; ++r.sourceIndex;
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadConfiguration.selector); newGate(verifier, r);
        r = request; r.model.weights ^= bytes32(uint256(1));
        vm.expectRevert(PeaceBBCAlertEvidenceGate.BadConfiguration.selector); newGate(verifier, r);
    }
    function replaced(bytes memory source, bytes memory needle, bytes memory replacement) private pure returns (bytes memory) {
        for (uint256 i; i + needle.length <= source.length; ++i) {
            bool equal = true; for (uint256 j; j < needle.length; ++j) if (source[i + j] != needle[j]) equal = false;
            if (!equal) continue;
            bytes memory result = new bytes(source.length - needle.length + replacement.length);
            for (uint256 j; j < i; ++j) result[j] = source[j];
            for (uint256 j; j < replacement.length; ++j) result[i + j] = replacement[j];
            for (uint256 j = i + needle.length; j < source.length; ++j) result[i + replacement.length + j - i - needle.length] = source[j];
            return result;
        }
        revert("fixture needle missing");
    }
}
