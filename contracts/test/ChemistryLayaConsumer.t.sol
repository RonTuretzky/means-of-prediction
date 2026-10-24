// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {ChemistryAlertEvidenceGate} from "../src/judge/ChemistryAlertEvidenceGate.sol";
import {ChemistryLayaConsumer} from "../src/judge/ChemistryLayaConsumer.sol";
import {ChemistryLayaResultInbox, ChemistryNonemptyQuorumChecker} from "../src/judge/ChemistryLayaResultInbox.sol";
import {
    IBLSSignatureChecker,
    IBLSSignatureCheckerTypes
} from "@eigenlayer-middleware/interfaces/IBLSSignatureChecker.sol";

/// @dev Only represents the ABSENCE of the required real operator certificate.
/// It rejects every call. No positive authentication or settlement test uses a mock.
contract MissingOperatorCertificate {
    error NoOperatorExecutionCertificate();

    fallback() external {
        revert NoOperatorExecutionCertificate();
    }
}

/// @notice Genuine-email consumer rejection tests. These intentionally do NOT
/// claim a successful quorum execution, stored inference result, or settlement.
contract ChemistryLayaConsumerTest is Test {
    ChemistryLayaConsumer consumer;
    EmailProof[] proofs;
    LayaRequest.Request[] requests;
    bytes[] inputs;
    uint32[][] ids;

    function setUp() public {
        string memory path = vm.envOr("LAYA_CHEMISTRY_GATE_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "Genuine fixture absent; consumer suite not run");
            return;
        }
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory raw = vm.ffi(command);
        assertEq(sha256(raw), 0x3397f4b408d083efcb885fb627d990bac0b498cc837a6b1b086f48e3fc084327);
        string memory fixture = string(raw);
        bytes memory exponent;
        bytes memory modulus;
        (proofs, exponent, modulus, inputs, ids, requests) = abi.decode(
            vm.parseJsonBytes(fixture, ".abiHex"),
            (EmailProof[], bytes, bytes, bytes[], uint32[][], LayaRequest.Request[])
        );
        vm.chainId(requests[0].chainId);
        vm.warp(vm.parseJsonUint(fixture, ".validationTimeUnix"));
        DKIMRegistry registry = new DKIMRegistry();
        registry.registerKey("google.com", "20251104", exponent, modulus);
        DKIMVerifier verifier = new DKIMVerifier(registry);
        consumer = new ChemistryLayaConsumer(
            verifier,
            proofs[0].publicKeyHash,
            address(0xA55),
            IBLSSignatureChecker(address(new MissingOperatorCertificate())),
            hex"00",
            requests,
            false
        );
        for (uint256 i; i < requests.length; ++i) {
            requests[i].market = address(consumer);
        }
    }

    function test_GenuineEvidenceCanBeReviewedWithoutAResultOrSettlement() public {
        for (uint256 i; i < 3; ++i) {
            (bytes32 key, uint8 group) = consumer.reviewEvidence(requests[i], proofs[i], inputs[i], ids[i]);
            assertEq(key, LayaRequest.key(requests[i]));
            assertEq(group, i == 1 ? 1 : 0);
        }
        assertUnresolved();
    }

    function test_LocalScoresWithoutQuorumCertificateCannotBeRecorded() public {
        for (uint256 i; i < 3; ++i) {
            vm.expectRevert(ChemistryLayaResultInbox.MissingCertificate.selector);
            consumer.recordAuthenticatedObservation(requests[i], proofs[i], inputs[i], ids[i]);
        }
        assertUnresolved();
    }

    function test_DirectResultInjectionRejected() public {
        ChemistryLayaResultInbox inbox = consumer.resultInbox();
        bytes32 domain = inbox.resultDomain();
        LayaRequest.Result memory result =
            LayaRequest.Result(1, LayaRequest.key(requests[0]), bytes32(uint256(1)), 0, 1000000);
        vm.expectRevert(ChemistryLayaResultInbox.NotCertifiedTransition.selector);
        inbox.acceptCertifiedResult(domain, requests[0], result);
        assertUnresolved();
    }

    function test_SelfAddressWithoutCertifiedTransitionRejected() public {
        ChemistryLayaResultInbox inbox = consumer.resultInbox();
        bytes32 domain = inbox.resultDomain();
        LayaRequest.Result memory result =
            LayaRequest.Result(1, LayaRequest.key(requests[0]), bytes32(uint256(1)), 0, 1000000);
        vm.prank(address(inbox));
        vm.expectRevert(ChemistryLayaResultInbox.NotCertifiedTransition.selector);
        inbox.acceptCertifiedResult(domain, requests[0], result);
        assertUnresolved();
    }

    function test_EmptyQuorumCannotCreateCounterOnlyOrResultTransition() public {
        ChemistryLayaResultInbox inbox = consumer.resultInbox();
        vm.roll(100);
        bytes memory update = abi.encode(new uint8[](0), new bytes[](0));
        bytes32 digest = inbox.getMessageHash(0, inbox.acceptCertifiedResult.selector, update);
        IBLSSignatureCheckerTypes.NonSignerStakesAndSignature memory signature;
        vm.expectRevert(ChemistryNonemptyQuorumChecker.EmptyOrInvalidQuorum.selector);
        inbox.verifyAndUpdate(digest, "", 99, update, 0, inbox.acceptCertifiedResult.selector, signature);
        assertEq(inbox.stateTransitionCount(), 0);
        assertUnresolved();
    }

    function test_NonemptyQuorumWithoutRealSignatureAlsoFails() public {
        ChemistryLayaResultInbox inbox = consumer.resultInbox();
        vm.roll(100);
        bytes memory update = abi.encode(new uint8[](0), new bytes[](0));
        bytes32 digest = inbox.getMessageHash(0, inbox.acceptCertifiedResult.selector, update);
        IBLSSignatureCheckerTypes.NonSignerStakesAndSignature memory signature;
        vm.expectRevert(MissingOperatorCertificate.NoOperatorExecutionCertificate.selector);
        inbox.verifyAndUpdate(digest, hex"00", 99, update, 0, inbox.acceptCertifiedResult.selector, signature);
        assertEq(inbox.stateTransitionCount(), 0);
        assertUnresolved();
    }

    function test_DifferentQuorumCannotChooseAnUnconfiguredSignerSet() public {
        ChemistryLayaResultInbox inbox = consumer.resultInbox();
        vm.roll(100);
        bytes memory update = abi.encode(new uint8[](0), new bytes[](0));
        bytes32 digest = inbox.getMessageHash(0, inbox.acceptCertifiedResult.selector, update);
        IBLSSignatureCheckerTypes.NonSignerStakesAndSignature memory signature;
        vm.expectRevert(ChemistryNonemptyQuorumChecker.EmptyOrInvalidQuorum.selector);
        inbox.verifyAndUpdate(digest, hex"01", 99, update, 0, inbox.acceptCertifiedResult.selector, signature);
        assertEq(inbox.stateTransitionCount(), 0);
        assertUnresolved();
    }

    function test_WrongChainCannotReuseGenuineProof() public {
        vm.chainId(31338);
        vm.expectRevert(LayaRequest.WrongContext.selector);
        consumer.reviewEvidence(requests[0], proofs[0], inputs[0], ids[0]);
        assertUnresolved();
    }

    function assertUnresolved() private view {
        assertEq(uint256(consumer.decision()), uint256(ChemistryLayaConsumer.Decision.Unresolved));
        assertEq(consumer.observationCount(), 0);
        assertEq(consumer.evidenceGate().consumedSourceMask(), 0);
        for (uint256 i; i < 3; ++i) {
            (bool recorded,,,) = consumer.observations(LayaRequest.key(requests[i]));
            assertFalse(recorded);
        }
    }
}
