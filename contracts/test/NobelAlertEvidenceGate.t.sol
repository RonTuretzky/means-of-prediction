// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {NobelAlertEvidenceGate} from "../src/judge/NobelAlertEvidenceGate.sol";

/// @dev Genuine private RSA fixture; no synthetic signature or model result acceptance.
contract NobelAlertEvidenceGateTest is Test {
    bytes32 private constant PROFILE = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    DKIMRegistry private registry;
    DKIMVerifier private verifier;
    NobelAlertEvidenceGate private gate;
    EmailProof private proof;
    LayaRequest.Request private request;
    bytes private exactInput;
    uint32[] private tokenIds;
    uint256 private signedAt;
    uint256 private expiresAt;

    function setUp() public {
        string memory path = vm.envOr("LAYA_NOBEL_GATE_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "LAYA_NOBEL_GATE_FIXTURE absent; genuine RSA gate suite not run");
            return;
        }
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory raw = vm.ffi(command);
        emit log_named_bytes32("genuine gate fixture JSON SHA256", sha256(raw));
        string memory fixture = string(raw);
        bytes memory exponent;
        bytes memory modulus;
        (proof, exponent, modulus, exactInput, tokenIds, request) = abi.decode(
            vm.parseJsonBytes(fixture, ".abiHex"), (EmailProof, bytes, bytes, bytes, uint32[], LayaRequest.Request)
        );
        signedAt = vm.parseJsonUint(fixture, ".signedAtUnix");
        expiresAt = vm.parseJsonUint(fixture, ".expiresAtUnix");
        assertEq(vm.parseJsonBytes32(fixture, ".profileSHA256"), PROFILE);
        vm.chainId(request.chainId);
        vm.warp(vm.parseJsonUint(fixture, ".validationTimeUnix"));
        assertGe(block.timestamp, signedAt);
        assertLe(block.timestamp, expiresAt);
        assertGt(request.expiresAt, expiresAt);
        assertEq(proof.domainName, "google.com");
        assertEq(proof.fromAddress, "googlealerts-noreply@google.com");
        assertEq(proof.canonicalBody.length, 20461);
        assertEq(sha256(proof.canonicalBody), 0xef09cd6700414ff97c243c6c7b564b457c19db3efdc26a0e84033bd033e939b4);
        assertEq(proof.bodyOffset, 8078);
        assertEq(proof.bodyLength, 1265);
        registry = new DKIMRegistry();
        verifier = new DKIMVerifier(registry);
        assertEq(registry.registerKey("google.com", "20251104", exponent, modulus), proof.publicKeyHash);
        gate = newGate(request);
    }

    function newGate(LayaRequest.Request memory r) private returns (NobelAlertEvidenceGate) {
        return new NobelAlertEvidenceGate(verifier, proof.publicKeyHash, PROFILE, r);
    }

    function submit() private returns (bytes32) {
        return gate.receiveEvidence(gate.requestDomain(), request, proof, exactInput, tokenIds);
    }

    function test_GenuineRSAFullBodyAndFrozenRequestReceipt() public {
        EmailProof memory headerOnly = proof;
        headerOnly.canonicalBody = "";
        headerOnly.bodyExcerpt = "";
        headerOnly.bodyOffset = 0;
        headerOnly.bodyLength = 0;
        uint256 before = gasleft();
        assertTrue(verifier.verify(headerOnly), "genuine full-header RSA failed");
        emit log_named_uint("genuine BBC full-header RSA verifier gas", before - gasleft());
        before = gasleft();
        bytes32 receipt = submit();
        emit log_named_uint("genuine BBC complete evidence gate gas", before - gasleft());
        assertEq(receipt, keccak256(abi.encode(gate.requestDomain(), LayaRequest.key(request), proof.emailNullifier)));
        assertTrue(gate.consumedRequests(LayaRequest.key(request)));
        assertTrue(gate.consumedEmails(proof.emailNullifier));
    }

    function test_ReplayRejectedOnlyAfterSuccess() public {
        gate.receiveEvidence(gate.requestDomain(), request, proof, bytes("wrong input"), tokenIds);
    }

    function test_InputFailureDoesNotConsumeThenSuccessThenReplay() public {
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.receiveEvidence(gate.requestDomain(), request, proof, bytes("wrong input"), tokenIds);
        assertFalse(gate.consumedRequests(LayaRequest.key(request)));
        assertFalse(gate.consumedEmails(proof.emailNullifier));
        submit();
        vm.expectRevert(NobelAlertEvidenceGate.AlreadyConsumed.selector);
        submit();
    }

    function test_ChangedSignedHeaderAndClaimedSubjectRejected() public {
        EmailProof memory p = proof;
        p.header[p.header.length - 1] ^= 0x01;
        vm.expectRevert();
        gate.receiveEvidence(gate.requestDomain(), request, p, exactInput, tokenIds);
        p = proof;
        p.subject = "unrelated independently supplied subject";
        vm.expectRevert(NobelAlertEvidenceGate.BadRSA.selector);
        gate.receiveEvidence(gate.requestDomain(), request, p, exactInput, tokenIds);
    }

    function test_ChangedBodyOutsideWindowRejectedEvenWhenRecommitted() public {
        EmailProof memory p = proof;
        LayaRequest.Request memory r = request;
        p.canonicalBody[p.canonicalBody.length - 8] ^= 0x01;
        r.emailHash = keccak256(abi.encode(p));
        r.canonicalBodySha256 = sha256(p.canonicalBody);
        NobelAlertEvidenceGate altered = newGate(r);
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        altered.receiveEvidence(altered.requestDomain(), r, p, exactInput, tokenIds);
    }

    function test_ChangedExcerptAndOffsetRejectedEvenWhenRecommitted() public {
        EmailProof memory p = proof;
        LayaRequest.Request memory r = request;
        p.bodyExcerpt = "fabricated laureate";
        r.emailHash = keccak256(abi.encode(p));
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
        NobelAlertEvidenceGate altered = newGate(r);
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        altered.receiveEvidence(altered.requestDomain(), r, p, exactInput, tokenIds);
        p = proof;
        r = request;
        p.bodyOffset++;
        r.emailHash = keccak256(abi.encode(p));
        r.bodyOffset++;
        altered = newGate(r);
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        altered.receiveEvidence(altered.requestDomain(), r, p, exactInput, tokenIds);
    }

    function test_WrongKeySenderAndDomainRejected() public {
        EmailProof memory p = proof;
        p.publicKeyHash ^= bytes32(uint256(1));
        vm.expectRevert(NobelAlertEvidenceGate.WrongGoogleIdentity.selector);
        gate.receiveEvidence(gate.requestDomain(), request, p, exactInput, tokenIds);
        p = proof;
        p.fromAddress = "attacker@google.com";
        vm.expectRevert(NobelAlertEvidenceGate.WrongGoogleIdentity.selector);
        gate.receiveEvidence(gate.requestDomain(), request, p, exactInput, tokenIds);
        p = proof;
        p.domainName = "attacker.example";
        vm.expectRevert(NobelAlertEvidenceGate.WrongGoogleIdentity.selector);
        gate.receiveEvidence(gate.requestDomain(), request, p, exactInput, tokenIds);
    }

    function test_WrongMarketChainAndRequestDomainRejected() public {
        LayaRequest.Request memory r = request;
        r.market = address(0xBAD);
        vm.expectRevert(LayaRequest.WrongContext.selector);
        gate.receiveEvidence(gate.requestDomain(), r, proof, exactInput, tokenIds);
        r = request;
        r.chainId++;
        vm.expectRevert(LayaRequest.WrongContext.selector);
        gate.receiveEvidence(gate.requestDomain(), r, proof, exactInput, tokenIds);
        vm.expectRevert(NobelAlertEvidenceGate.WrongDomain.selector);
        gate.receiveEvidence(bytes32(uint256(1)), request, proof, exactInput, tokenIds);
        NobelAlertEvidenceGate other = newGate(request);
        vm.expectRevert(NobelAlertEvidenceGate.WrongDomain.selector);
        other.receiveEvidence(gate.requestDomain(), request, proof, exactInput, tokenIds);
    }

    function test_EveryPolicyPinInputCommitmentAndNonceFrozen() public {
        bytes memory encoded = abi.encode(request);
        // Every non-context static ABI word, including nested model pins. The shared
        // validator may reject first for invalid versions/ranges; all changes must fail.
        for (uint256 i; i < encoded.length / 32; ++i) {
            encoded[i * 32 + 31] ^= 0x01;
            LayaRequest.Request memory r = abi.decode(encoded, (LayaRequest.Request));
            vm.expectRevert();
            gate.receiveEvidence(gate.requestDomain(), r, proof, exactInput, tokenIds);
            encoded[i * 32 + 31] ^= 0x01;
        }
    }

    function test_FutureAndExpiredSignatureUseBlockTimestamp() public {
        vm.warp(signedAt - 1);
        vm.expectRevert(NobelAlertEvidenceGate.SignatureOutsideValidity.selector);
        submit();
        vm.warp(expiresAt + 1);
        vm.expectRevert(NobelAlertEvidenceGate.SignatureOutsideValidity.selector);
        submit();
    }

    function test_RequestExpiryUsesBlockTimestamp() public {
        vm.warp(uint256(request.expiresAt) + 1);
        vm.expectRevert(LayaRequest.Expired.selector);
        submit();
    }

    function test_RevokedKeyRejectedAndNotConsumed() public {
        registry.revokeKey("google.com", proof.publicKeyHash);
        vm.expectRevert(NobelAlertEvidenceGate.BadRSA.selector);
        submit();
        assertFalse(gate.consumedEmails(proof.emailNullifier));
    }

    function test_MismatchedTokensRejected() public {
        uint32[] memory ids = tokenIds;
        ids[0]++;
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.receiveEvidence(gate.requestDomain(), request, proof, exactInput, ids);
    }

    function test_WrongProfileOrWeightsCannotConfigureGate() public {
        vm.expectRevert("wrong frozen model");
        new NobelAlertEvidenceGate(verifier, proof.publicKeyHash, bytes32(uint256(1)), request);
        LayaRequest.Request memory r = request;
        r.model.weights ^= bytes32(uint256(1));
        vm.expectRevert("wrong frozen model");
        newGate(r);
    }
}
