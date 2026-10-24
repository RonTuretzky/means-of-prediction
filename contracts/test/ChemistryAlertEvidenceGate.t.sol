// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {ChemistryAlertEvidenceGate} from "../src/judge/ChemistryAlertEvidenceGate.sol";

/// @dev Genuine Google RSA success path; no verifier mock or caller-supplied verdict.
/// Historical vm.warp is explicit. No live deployment, inference certificate or payout.
contract ChemistryAlertEvidenceGateTest is Test {
    bytes32 private constant PROFILE = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 private constant FIXTURE_SHA256 = 0x3397f4b408d083efcb885fb627d990bac0b498cc837a6b1b086f48e3fc084327;
    DKIMRegistry private registry;
    DKIMVerifier private verifier;
    ChemistryAlertEvidenceGate private gate;
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
        string memory path = vm.envOr("LAYA_CHEMISTRY_GATE_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "LAYA_CHEMISTRY_GATE_FIXTURE absent; genuine RSA suite not run");
            return;
        }
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory raw = vm.ffi(command);
        assertEq(sha256(raw), FIXTURE_SHA256, "genuine frozen fixture changed");
        emit log_named_bytes32("Chemistry genuine fixture JSON SHA256", sha256(raw));
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
        assertEq(proofs.length, 3);
        assertEq(inputs.length, 3);
        assertEq(ids.length, 3);
        assertEq(requests.length, 3);
        vm.chainId(requests[0].chainId);
        vm.warp(historicalTime);
        // Bind the local test consumer address, never change frozen evidence/input pins.
        for (uint256 i; i < 3; ++i) {
            requests[i].market = address(this);
            assertEq(requests[i].sourceIndex, i == 1 ? 1 : 0);
            assertGe(historicalTime, signedAt[i]);
            assertLe(historicalTime, expiresAt[i]);
            assertGt(requests[i].expiresAt, maxExpiry());
            assertEq(keccak256(abi.encode(proofs[i])), requests[i].emailHash);
            assertEq(sha256(proofs[i].canonicalBody), requests[i].canonicalBodySha256);
            assertEq(keccak256(inputs[i]), requests[i].inputBytesHash);
            assertEq(keccak256(abi.encode(ids[i])), requests[i].tokenIdsHash);
        }
        assertEq(proofs[0].canonicalBody.length, 166050);
        assertEq(proofs[1].canonicalBody.length, 95589);
        assertEq(proofs[2].canonicalBody.length, 111580);
        assertEq(sha256(proofs[0].canonicalBody), 0x4253bb1eb8d92f70371b821cab8590d56a216daf82eb559885549df329e0b3a9);
        assertEq(sha256(proofs[1].canonicalBody), 0x3e951f87b242b83604595f7a84bfc9df2aa7a48cd6419f330dc560cd7f3373ff);
        registry = new DKIMRegistry();
        assertEq(registry.registerKey("google.com", "20251104", exponent, modulus), proofs[0].publicKeyHash);
        verifier = new DKIMVerifier(registry);
        gate = newGate(verifier, requests);
        gateDomain = gate.requestDomain();
    }

    function maxExpiry() private view returns (uint256 n) {
        for (uint256 i; i < expiresAt.length; ++i) {
            if (expiresAt[i] > n) n = expiresAt[i];
        }
    }

    function newGate(DKIMVerifier v, LayaRequest.Request[] memory r) private returns (ChemistryAlertEvidenceGate) {
        return new ChemistryAlertEvidenceGate(
            v, address(this), proofs[0].publicKeyHash, PROFILE, r[0].rulesHash, r[0].sourcePolicyHash, r
        );
    }

    function verifyAt(uint256 i) private view returns (bytes32 key, uint8 group) {
        return gate.verifyEvidence(gateDomain, requests[i], proofs[i], inputs[i], ids[i]);
    }

    function consumeAt(uint256 i) private returns (bytes32 receipt, uint8 group) {
        return gate.consumeEvidence(gateDomain, requests[i], proofs[i], inputs[i], ids[i]);
    }

    function rebind(LayaRequest.Request memory r, EmailProof memory p)
        private
        pure
        returns (LayaRequest.Request memory)
    {
        r.emailHash = keccak256(abi.encode(p));
        r.emailNullifier = p.emailNullifier;
        r.canonicalBodySha256 = sha256(p.canonicalBody);
        r.bodyOffset = uint32(p.bodyOffset);
        r.bodyLength = uint32(p.bodyLength);
        r.decodedBytesHash = keccak256(bytes(p.bodyExcerpt));
        return r;
    }

    function test_GenuineRSAAndCompleteBodiesForAllThreeFrozenVariants() public {
        for (uint256 i; i < 3; ++i) {
            EmailProof memory headerOnly = proofs[i];
            headerOnly.canonicalBody = "";
            headerOnly.bodyExcerpt = "";
            headerOnly.bodyOffset = 0;
            headerOnly.bodyLength = 0;
            uint256 before = gasleft();
            assertTrue(verifier.verify(headerOnly), "genuine RSA failed");
            emit log_named_uint(string.concat("Chemistry RSA header gas variant ", vm.toString(i)), before - gasleft());
            before = gasleft();
            (bytes32 key, uint8 group) = verifyAt(i);
            emit log_named_uint(
                string.concat("Chemistry full-body gate view gas variant ", vm.toString(i)), before - gasleft()
            );
            assertEq(key, LayaRequest.key(requests[i]));
            assertEq(group, i == 1 ? 1 : 0);
            (bool allowed, uint8 storedGroup, uint8 variant) = gate.frozenRequestKeys(key);
            assertTrue(allowed);
            assertEq(storedGroup, group);
            assertEq(variant, i);
        }
        assertEq(gate.consumedSourceMask(), 0, "view verification must not consume abstention");
    }

    /// @dev Authorization/control-flow test only: this test contract stands in for a
    /// consumer that has already admitted support. Actual frozen float results abstain;
    /// they do not authorize the real certificate consumer to accumulate these sources.
    function test_AuthorizedHarnessCanConsumeTwoOriginalSources() public {
        uint256 before = gasleft();
        consumeAt(0);
        emit log_named_uint("Chemistry early Reuters consume gas", before - gasleft());
        assertEq(gate.consumedSourceMask(), 1);
        before = gasleft();
        consumeAt(1);
        emit log_named_uint("Chemistry AP consume gas", before - gasleft());
        assertEq(gate.consumedSourceMask(), 3);
        // Receipt consumption is deliberately not a verdict or a market payout.
        verifyAt(0); // View authentication remains available after consumption.
    }

    function test_LaterReutersDoesNotInflateSourceCount() public {
        consumeAt(0);
        vm.expectRevert(ChemistryAlertEvidenceGate.DuplicateSource.selector);
        consumeAt(2);
        assertFalse(gate.consumedRequests(LayaRequest.key(requests[2])));
        assertEq(gate.consumedSourceMask(), 1);
    }

    function test_ReplayRejected() public {
        consumeAt(1);
        vm.expectRevert(ChemistryAlertEvidenceGate.AlreadyConsumed.selector);
        consumeAt(1);
    }

    function test_OnlyConsumerCanConsume() public {
        bytes32 domain = gateDomain;
        vm.prank(address(0xBAD));
        vm.expectRevert(ChemistryAlertEvidenceGate.NotConsumer.selector);
        gate.consumeEvidence(domain, requests[0], proofs[0], inputs[0], ids[0]);
    }

    function consumeThenFail(uint256 i) external {
        consumeAt(i);
        revert DeliberateConsumerFailure();
    }

    function test_LaterConsumerFailureRollsBackAllConsumption() public {
        vm.expectRevert(DeliberateConsumerFailure.selector);
        this.consumeThenFail(0);
        assertFalse(gate.consumedRequests(LayaRequest.key(requests[0])));
        assertFalse(gate.consumedEmails(proofs[0].emailNullifier));
        assertEq(gate.consumedSourceMask(), 0);
    }

    function test_FailedInputDoesNotConsumeThenValidInputSucceeds() public {
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        gate.consumeEvidence(gateDomain, requests[0], proofs[0], bytes("bad input"), ids[0]);
        assertEq(gate.consumedSourceMask(), 0);
        consumeAt(0);
        assertEq(gate.consumedSourceMask(), 1);
    }

    function test_ChangedHeaderAndIndependentSubjectRejected() public {
        EmailProof memory p = proofs[0];
        // Keep all required field names/tags well formed, so real RSA must reject
        // changed signed bytes rather than failing an earlier structural check.
        p.header = replaced(p.header, "subject:", "subject:X");
        vm.expectRevert(ChemistryAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        p.subject = "an independently provided subject proof cannot replace the authenticated field";
        vm.expectRevert(ChemistryAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
    }

    function test_ChangedBodyOutsideWindowRejectedEvenWhenRecommitted() public {
        EmailProof memory p = proofs[0];
        p.canonicalBody[p.canonicalBody.length - 8] ^= 0x01;
        LayaRequest.Request[] memory rr = requests;
        rr[0] = rebind(rr[0], p);
        ChemistryAlertEvidenceGate altered = newGate(verifier, rr);
        bytes32 alteredDomain = altered.requestDomain();
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        altered.verifyEvidence(alteredDomain, rr[0], p, inputs[0], ids[0]);
    }

    function test_CrossEmailBodyCannotBorrowGenuineHeader() public {
        EmailProof memory p = proofs[0];
        p.canonicalBody = proofs[1].canonicalBody;
        p.bodyExcerpt = proofs[1].bodyExcerpt;
        p.bodyOffset = proofs[1].bodyOffset;
        p.bodyLength = proofs[1].bodyLength;
        LayaRequest.Request[] memory rr = requests;
        rr[0] = rebind(rr[0], p);
        ChemistryAlertEvidenceGate altered = newGate(verifier, rr);
        bytes32 alteredDomain = altered.requestDomain();
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        altered.verifyEvidence(alteredDomain, rr[0], p, inputs[0], ids[0]);
    }

    function test_ChangedExcerptAndOffsetRejectedEvenWhenRecommitted() public {
        for (uint256 i; i < 2; ++i) {
            EmailProof memory p = proofs[0];
            if (i == 0) p.bodyExcerpt = "fabricated winner set";
            else ++p.bodyOffset;
            LayaRequest.Request[] memory rr = requests;
            rr[0] = rebind(rr[0], p);
            ChemistryAlertEvidenceGate altered = newGate(verifier, rr);
            bytes32 alteredDomain = altered.requestDomain();
            vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
            altered.verifyEvidence(alteredDomain, rr[0], p, inputs[0], ids[0]);
        }
    }

    function test_OversizedAndCroppedBodyRejectedWithoutFallback() public {
        for (uint256 i; i < 2; ++i) {
            EmailProof memory p = proofs[0];
            if (i == 0) {
                p.canonicalBody = new bytes(196609);
            } else {
                bytes memory cropped = p.canonicalBody;
                assembly ("memory-safe") { mstore(cropped, sub(mload(cropped), 8)) }
                p.canonicalBody = cropped;
            }
            LayaRequest.Request[] memory rr = requests;
            rr[0] = rebind(rr[0], p);
            ChemistryAlertEvidenceGate altered = newGate(verifier, rr);
            bytes32 alteredDomain = altered.requestDomain();
            vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
            altered.verifyEvidence(alteredDomain, rr[0], p, inputs[0], ids[0]);
        }
    }

    function test_WrongGoogleIdentityKeyAndRevocationRejected() public {
        EmailProof memory p = proofs[0];
        p.publicKeyHash ^= bytes32(uint256(1));
        vm.expectRevert(ChemistryAlertEvidenceGate.WrongGoogleIdentity.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        p.domainName = "attacker.example";
        vm.expectRevert(ChemistryAlertEvidenceGate.WrongGoogleIdentity.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        p.fromAddress = "attacker@google.com";
        vm.expectRevert(ChemistryAlertEvidenceGate.WrongGoogleIdentity.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        registry.revokeKey("google.com", proofs[0].publicKeyHash);
        vm.expectRevert(ChemistryAlertEvidenceGate.BadRSA.selector);
        verifyAt(0);
    }

    function test_RegistryWithWrongRSAExponentCannotAuthenticate() public {
        DKIMRegistry wrong = new DKIMRegistry();
        wrong.registerKey("google.com", "20251104", hex"03", modulus);
        ChemistryAlertEvidenceGate altered = newGate(new DKIMVerifier(wrong), requests);
        bytes32 alteredDomain = altered.requestDomain();
        vm.expectRevert(ChemistryAlertEvidenceGate.BadRSA.selector);
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
        vm.expectRevert(ChemistryAlertEvidenceGate.WrongDomain.selector);
        gate.verifyEvidence(bytes32(uint256(1)), requests[0], proofs[0], inputs[0], ids[0]);
        ChemistryAlertEvidenceGate other = newGate(verifier, requests);
        vm.expectRevert(ChemistryAlertEvidenceGate.WrongDomain.selector);
        other.verifyEvidence(gateDomain, requests[0], proofs[0], inputs[0], ids[0]);
        bytes32 oldChainDomain = gateDomain;
        vm.chainId(block.chainid + 1);
        vm.expectRevert(ChemistryAlertEvidenceGate.WrongDomain.selector);
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

    function test_HistoricalClockExplicitAndCurrentExpiryRejected() public {
        vm.warp(signedAt[0] - 1);
        vm.expectRevert(ChemistryAlertEvidenceGate.SignatureOutsideValidity.selector);
        verifyAt(0);
        vm.warp(expiresAt[0] + 1);
        vm.expectRevert(ChemistryAlertEvidenceGate.SignatureOutsideValidity.selector);
        verifyAt(0);
        vm.warp(currentTime);
        for (uint256 i; i < 3; ++i) {
            vm.expectRevert(ChemistryAlertEvidenceGate.SignatureOutsideValidity.selector);
            verifyAt(i);
        }
    }

    function test_RequestExpiryRejected() public {
        vm.warp(uint256(requests[0].expiresAt) + 1);
        vm.expectRevert(LayaRequest.Expired.selector);
        verifyAt(0);
    }

    function replaced(bytes memory source, bytes memory needle, bytes memory replacement)
        private
        pure
        returns (bytes memory)
    {
        for (uint256 i; i + needle.length <= source.length; ++i) {
            bool equal = true;
            for (uint256 j; j < needle.length; ++j) {
                if (source[i + j] != needle[j]) equal = false;
            }
            if (!equal) continue;
            bytes memory result = new bytes(source.length - needle.length + replacement.length);
            for (uint256 j; j < i; ++j) {
                result[j] = source[j];
            }
            for (uint256 j; j < replacement.length; ++j) {
                result[i + j] = replacement[j];
            }
            for (uint256 j = i + needle.length; j < source.length; ++j) {
                result[i + replacement.length + j - i - needle.length] = source[j];
            }
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
            vm.expectRevert(ChemistryAlertEvidenceGate.BadHeaderPolicy.selector);
            gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        }
    }

    function test_NullifierAndClaimedDateCannotBeChanged() public {
        EmailProof memory p = proofs[0];
        p.emailNullifier ^= bytes32(uint256(1));
        vm.expectRevert(ChemistryAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
        p = proofs[0];
        ++p.timestamp;
        vm.expectRevert(ChemistryAlertEvidenceGate.BadRSA.selector);
        gate.verifyEvidence(gateDomain, requests[0], p, inputs[0], ids[0]);
    }

    function test_ConfigurationRejectsWrongProfileModelSourceGroupOrPolicy() public {
        vm.expectRevert(ChemistryAlertEvidenceGate.BadConfiguration.selector);
        new ChemistryAlertEvidenceGate(
            verifier,
            address(this),
            proofs[0].publicKeyHash,
            bytes32(uint256(1)),
            requests[0].rulesHash,
            requests[0].sourcePolicyHash,
            requests
        );
        LayaRequest.Request[] memory rr = requests;
        rr[2].sourceIndex = 1;
        vm.expectRevert(ChemistryAlertEvidenceGate.BadConfiguration.selector);
        newGate(verifier, rr);
        rr = requests;
        rr[1].sourcePolicyHash ^= bytes32(uint256(1));
        vm.expectRevert(ChemistryAlertEvidenceGate.BadConfiguration.selector);
        newGate(verifier, rr);
        rr = requests;
        rr[0].model.weights ^= bytes32(uint256(1));
        vm.expectRevert(ChemistryAlertEvidenceGate.BadConfiguration.selector);
        newGate(verifier, rr);
    }
}
