// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {stdStorage, StdStorage} from "forge-std/StdStorage.sol";
import {console2} from "forge-std/console2.sol";
import {SchnorrStakeRegistry} from "../lib/chemistry-schnorr-sdk/src/SchnorrStakeRegistry.sol";
import {GasKillerSDK} from "../lib/chemistry-schnorr-sdk/src/GasKillerSDK.sol";
import {StateChangeHandlerLib} from "../lib/chemistry-schnorr-sdk/src/StateChangeHandlerLib.sol";
import {QuorumSignature} from "../lib/chemistry-schnorr-sdk/src/interface/ISchnorrApprovalRegistry.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {PeaceFourReportEvidenceGate} from "../src/judge/PeaceFourReportEvidenceGate.sol";
import {PeaceFourReportSchnorrConsumer} from "../src/judge/PeaceFourReportSchnorrConsumer.sol";

/// @notice Actual actor-produced signatures through actual SDK/registry, not mocked
/// positive authentication. Four exact pre-score reviewed reports are checked at
/// the frozen current-time snapshot and consumed atomically. Local Yes is not live settlement.
contract PeaceFourReportSchnorrConsumerTest is Test {
    using stdStorage for StdStorage;
    struct OperatorPoP { uint256 x; uint256 y; uint256 weight; uint256 popS; address popR; }
    struct Certificate {
        bytes32 digest;
        uint32 refBlock;
        bytes payload;
        uint256 transitionIndex;
        bytes4 targetFunction;
        uint256 s;
        address Raddr;
        address[] nonSigners;
    }

    // Filled only with the actual independently executed actor artifact, never a
    // generated mock certificate or a caller-selected probability fixture.
    bytes32 constant ACTOR_FIXTURE_SHA256 =
        0x6fed0a096e6f04454d38e4fa7a29f3966e5969ca03eee192fe877b253a723a29;
    address constant TEST_DEPLOYER = address(0xC0FFEE);
    address constant EXPECTED_CONSUMER = 0xBE48387535e1dE07361eF51B57aaa5758c445D79;
    SchnorrStakeRegistry registry;
    PeaceFourReportSchnorrConsumer consumer;
    OperatorPoP[] operators;
    PeaceFourReportSchnorrConsumer.Receipt[] receipts;
    Certificate[] certificates;
    EmailProof[] proofs;
    LayaRequest.Request[] requests;
    bytes[] inputs;
    uint32[][] ids;
    uint256 currentClock;

    function fileBytes(string memory path) private returns (bytes memory raw) {
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        return vm.ffi(command);
    }

    function setUp() public {
        string memory gatePath = vm.envOr("LAYA_PEACE_FOUR_GATE_FIXTURE", string(""));
        string memory actorPath = vm.envOr("LAYA_PEACE_FOUR_SCHNORR_FIXTURE", string(""));
        if (bytes(gatePath).length == 0 || bytes(actorPath).length == 0) {
            vm.skip(true, "Actual actor signature and genuine evidence fixtures required; no positive claim");
            return;
        }
        bytes memory gateRaw = fileBytes(gatePath);
        assertEq(sha256(gateRaw), 0x0c409ee7a6c16f4629f42101d0c9aa99135b7ce4ec7176e7d3a816ac28d33d7b);
        string memory gateFixture = string(gateRaw);
        bytes memory exponent;
        bytes memory modulus;
        (proofs, exponent, modulus, inputs, ids, requests) = abi.decode(vm.parseJsonBytes(gateFixture, ".abiHex"),
            (EmailProof[], bytes, bytes, bytes[], uint32[][], LayaRequest.Request[]));
        bytes memory actorRaw = fileBytes(actorPath);
        assertEq(sha256(actorRaw), ACTOR_FIXTURE_SHA256, "Actual actor artifact must be immutably pinned");
        (operators, receipts, certificates) = abi.decode(vm.parseJsonBytes(string(actorRaw), ".abiHex"),
            (OperatorPoP[], PeaceFourReportSchnorrConsumer.Receipt[], Certificate[]));
        assertEq(operators.length, 3);
        assertEq(receipts.length, 4);
        assertEq(certificates.length, 4);
        vm.chainId(31337);
        currentClock = vm.parseJsonUint(gateFixture, ".currentTimeUnix");
        vm.warp(currentClock);
        vm.roll(100);
        registry = new SchnorrStakeRegistry(2, 3, address(this), 0);
        for (uint256 i; i < 3; ++i) {
            OperatorPoP memory op = operators[i];
            assertEq(op.weight, 100);
            assertEq(registry.pointAddress(op.x, op.y), vm.addr((i + 1) * 101), "Published decimal TEST key identity");
            registry.registerOperator(op.x, op.y, op.weight, op.popS, op.popR);
        }
        assertEq(registry.totalWeight(), 300);
        vm.roll(110);
        DKIMRegistry keys = new DKIMRegistry();
        keys.registerKey("google.com", "20251104", exponent, modulus);
        DKIMVerifier verifier = new DKIMVerifier(keys);
        vm.setNonce(TEST_DEPLOYER, 3);
        vm.prank(TEST_DEPLOYER);
        consumer = new PeaceFourReportSchnorrConsumer(verifier, proofs[0].publicKeyHash, registry,
            address(0xA55), requests);
        assertEq(address(consumer), EXPECTED_CONSUMER);
        for (uint256 i; i < 4; ++i) {
            requests[i].market = address(consumer);
            assertEq(receipts[i].requestKey, LayaRequest.key(requests[i]));
            assertEq(receipts[i].consumer, address(consumer));
            assertEq(receipts[i].version, 3);
            assertEq(receipts[i].contextDomain, consumer.receiptContextDomain());
            assertEq(receipts[i].marketId, 5371292);
            assertEq(receipts[i].modelPinsHash, keccak256(abi.encode(requests[i].model)));
            assertEq(certificates[i].transitionIndex, i);
            assertEq(certificates[i].refBlock, 109);
            assertEq(certificates[i].targetFunction, consumer.acceptCertifiedReport.selector);
            assertEq(certificates[i].digest, consumer.receiptDigest(i, receipts[i]));
            assertEq(certificates[i].payload, consumer.receiptPayload(receipts[i]));
            assertEq(certificates[i].nonSigners.length, 0, "Actual fixture is all three public TEST operators");
            // Assert actual independently executed artifact; never choose supplied scores.
            assertGe(receipts[i].aPpm, 550000);
            assertLt(receipts[i].bPpm, 550000);
        }
    }

    function transport(uint256 i) private {
        Certificate memory c = certificates[i];
        assertTrue(registry.isValidSignature(c.digest, c.s, c.Raddr, c.nonSigners, c.refBlock));
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
    }

    function signature(uint256 i) private view returns (QuorumSignature memory) {
        Certificate memory c = certificates[i];
        return QuorumSignature(c.s, c.Raddr, c.nonSigners, c.refBlock);
    }

    function recordObservation(uint256 i) private {
        consumer.recordAuthenticatedObservation(requests[i], proofs[i], inputs[i], ids[i], i, signature(i));
    }

    function assertNoConsumption() private view {
        assertEq(uint256(consumer.decision()), uint256(PeaceFourReportSchnorrConsumer.Decision.Unresolved));
        assertEq(consumer.evidenceGate().consumedSourceMask(), 0);
        for (uint256 i; i < 4; ++i) {
            assertFalse(consumer.evidenceGate().consumedRequests(LayaRequest.key(requests[i])));
            assertFalse(consumer.evidenceGate().consumedEmails(proofs[i].emailNullifier));
        }
    }

    function recordAll() private {
        for (uint256 i; i < 4; ++i) { transport(i); recordObservation(i); }
    }

    function assertAllConsumed() private view {
        assertEq(uint256(consumer.decision()), uint256(PeaceFourReportSchnorrConsumer.Decision.Yes));
        assertEq(consumer.evidenceGate().consumedSourceMask(), 15);
        for (uint256 i; i < 4; ++i) {
            assertTrue(consumer.evidenceGate().consumedRequests(LayaRequest.key(requests[i])));
            assertTrue(consumer.evidenceGate().consumedEmails(proofs[i].emailNullifier));
        }
    }

    function test_ActualFourActorsFullProofsAndAOnlyResultsConsumeExactPacketAtOneClock() public {
        for (uint256 i; i < 4; ++i) {
            Certificate memory c = certificates[i];
            assertTrue(registry.isValidSignature(c.digest, c.s, c.Raddr, c.nonSigners, c.refBlock));
            uint256 gasBefore = gasleft();
            consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
                c.s, c.Raddr, c.nonSigners);
            console2.log("actual four-report SDK transport caller gas delta", i, gasBefore - gasleft());
            gasBefore = gasleft(); recordObservation(i);
            console2.log("complete original report observation caller gas delta", i, gasBefore - gasleft());
            assertEq(consumer.observationCount(), i + 1);
            (bool recorded, bool a, bool b,) = consumer.observations(LayaRequest.key(requests[i]));
            assertTrue(recorded); assertTrue(a); assertFalse(b);
        }
        assertEq(consumer.stateTransitionCount(), 4);
        assertEq(consumer.supportingSourceMask(), 15); assertFalse(consumer.anyBSupport());
        assertNoConsumption();
        uint256 gasBefore = gasleft();
        consumer.finalize(proofs, inputs, ids);
        console2.log("same-clock all-four reauthentication and atomic finalize caller gas delta", gasBefore - gasleft());
        assertAllConsumed();
    }

    function test_NoReceiptCannotRecordGenuineEmailOrFinalize() public {
        vm.expectRevert(PeaceFourReportSchnorrConsumer.MissingReceipt.selector);
        recordObservation(0);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.IncompleteObservations.selector);
        consumer.finalize(proofs, inputs, ids);
        assertNoConsumption();
    }

    function test_DirectReceiptInjectionRejected() public {
        vm.expectRevert(PeaceFourReportSchnorrConsumer.NotCertifiedTransition.selector);
        consumer.acceptCertifiedReport(receipts[0]);
        assertNoConsumption();
    }

    function test_RealSignatureTamperRejectedWithoutTransition() public {
        Certificate memory c = certificates[0];
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s ^ 1, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function test_RealSignatureCannotAuthenticateChangedScorePayload() public {
        Certificate memory c = certificates[0];
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.bPpm = 1000000;
        bytes memory payload = consumer.receiptPayload(changed);
        bytes32 digest = consumer.receiptDigest(0, changed);
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(digest, c.refBlock, payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function rejectChangedReceipt(PeaceFourReportSchnorrConsumer.Receipt memory changed) private {
        Certificate memory c = certificates[0];
        bytes memory payload = consumer.receiptPayload(changed);
        bytes32 digest = consumer.receiptDigest(0, changed);
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(digest, c.refBlock, payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_OriginalCertificateRejectsModifiedExecutionRoot() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.executionRoot = bytes32(uint256(changed.executionRoot) ^ 1);
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongMarket() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.marketId = 5371179;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongChain() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.chainId = 31338;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongRequest() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.requestKey = receipts[1].requestKey;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongInput() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.inputHash = receipts[1].inputHash;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongTokenCommitment() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.tokenIdsHash = receipts[1].tokenIdsHash;
        rejectChangedReceipt(changed);
    }

    function test_ActualCertificateCannotSubstituteDifferentInputBytes() public {
        transport(0);
        inputs[0][0] = bytes1(uint8(inputs[0][0]) ^ 1);
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_ActualCertificateCannotSubstituteDifferentTokenIds() public {
        transport(0);
        ids[0][0] ^= 1;
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_RealCertificateAndObservationReplaysRejected() public {
        transport(0);
        recordObservation(0);
        Certificate memory c = certificates[0];
        vm.expectRevert(GasKillerSDK.InvalidTransitionIndex.selector);
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.AlreadyRecorded.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 1);
        assertNoConsumption();
    }

    function test_BelowStakeThresholdRejectedByActualRegistry() public {
        Certificate memory c = certificates[0];
        address[] memory ns = new address[](2);
        address a = registry.pointAddress(operators[1].x, operators[1].y);
        address b = registry.pointAddress(operators[2].x, operators[2].y);
        (ns[0], ns[1]) = a < b ? (a, b) : (b, a);
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, ns);
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function test_StaleReferenceBlockRejectedByActualSDK() public {
        vm.roll(410); // ref109 + staleMeasure300 < current410
        Certificate memory c = certificates[0];
        vm.expectRevert(GasKillerSDK.StaleBlockNumber.selector);
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_FutureAndEqualReferenceBlocksRejectedByActualSDK() public {
        Certificate memory c = certificates[0];
        vm.roll(109); // equal reference block
        vm.expectRevert(GasKillerSDK.FutureBlockNumber.selector);
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        vm.roll(108); // future reference block
        vm.expectRevert(GasKillerSDK.FutureBlockNumber.selector);
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_CertificateCannotSubstituteTamperedOriginalFullBody() public {
        transport(0);
        proofs[0].canonicalBody[100] = bytes1(uint8(proofs[0].canonicalBody[100]) ^ 1);
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_ExpiredOriginalBBCDKIMRejectsAtObservation() public {
        transport(0);
        vm.warp(1792897109);
        vm.expectRevert(PeaceFourReportEvidenceGate.SignatureOutsideValidity.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_CrossChainReceiptRejectedByTypedCallback() public {
        vm.chainId(31338);
        Certificate memory c = certificates[0];
        vm.expectRevert(abi.encodeWithSelector(
            StateChangeHandlerLib.RevertingContext.selector,
            uint256(0), address(consumer),
            abi.encodeWithSelector(PeaceFourReportSchnorrConsumer.BadReceiptContext.selector),
            abi.encodeCall(consumer.acceptCertifiedReport, (receipts[0]))
        ));
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function test_RegistrySnapshotMutationFailsClosedBeforeObservation() public {
        transport(0);
        vm.roll(111);
        registry.deregisterOperator(registry.pointAddress(operators[2].x, operators[2].y));
        vm.expectRevert(PeaceFourReportSchnorrConsumer.BadRegistry.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }
    function test_FinalizeMissingOneActualCertifiedObservationStaysUnresolved() public {
        for (uint256 i; i < 3; ++i) { transport(i); recordObservation(i); }
        vm.expectRevert(PeaceFourReportSchnorrConsumer.IncompleteObservations.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_FinalizeFreshlyReverifiesCNNExpiryAfterAllEarlierObservations() public {
        recordAll(); vm.warp(1792599290); // CNN x+1; BBC/ABC/RFI signatures still valid.
        vm.expectRevert(PeaceFourReportEvidenceGate.SignatureOutsideValidity.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_FinalizeLastProofTamperRollsBackEntirePacket() public {
        recordAll(); proofs[3].canonicalBody[100] = bytes1(uint8(proofs[3].canonicalBody[100]) ^ 1);
        vm.expectRevert(LayaRequest.EvidenceMismatch.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_FinalizeRejectsWrongOrderWithoutPartialConsumption() public {
        recordAll(); EmailProof memory first = proofs[0]; proofs[0] = proofs[1]; proofs[1] = first;
        vm.expectRevert(PeaceFourReportEvidenceGate.BadHeaderPolicy.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_FinalizeRejectsInputAndTokenTamperingWithoutConsumption() public {
        recordAll(); inputs[3][0] = bytes1(uint8(inputs[3][0]) ^ 1);
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
        inputs[3][0] = bytes1(uint8(inputs[3][0]) ^ 1); ids[3][0] ^= 1;
        vm.expectRevert(LayaRequest.InputMismatch.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_FinalizeCannotReplayAfterActualAtomicConsumption() public {
        recordAll(); consumer.finalize(proofs, inputs, ids); assertAllConsumed();
        vm.expectRevert(PeaceFourReportSchnorrConsumer.AlreadyRecorded.selector);
        consumer.finalize(proofs, inputs, ids); assertAllConsumed();
    }

    function test_FinalizeWrongArrayLengthLeavesNoConsumption() public {
        recordAll(); EmailProof[] memory short = new EmailProof[](3);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.BadEvidenceArray.selector);
        consumer.finalize(short, inputs, ids); assertNoConsumption();
    }

    function test_SYNTHETIC_STORAGE_FAULT_BSupportBlocksYesNotAnActualModelResult() public {
        recordAll();
        // Negative fault injection only. No synthetic positive certificate is used.
        stdstore.target(address(consumer)).sig("anyBSupport()").enable_packed_slots().checked_write(true);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.ConflictingSupport.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_SYNTHETIC_STORAGE_FAULT_AbstentionBlocksYesNotAnActualModelResult() public {
        recordAll();
        stdstore.target(address(consumer)).sig("supportingSourceMask()").enable_packed_slots().checked_write(uint256(7));
        vm.expectRevert(PeaceFourReportSchnorrConsumer.InsufficientSupport.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_OriginalCertificateRejectsOldProtocolVersionOrDomain() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0]; changed.version = 2;
        rejectChangedReceipt(changed);
        changed = receipts[0]; changed.contextDomain = keccak256("PEACE_BBC_SCHNORR_OBSERVATION_V1");
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsModelProfileOrRuntimeMismatch() public {
        PeaceFourReportSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.modelPinsHash = bytes32(uint256(changed.modelPinsHash) ^ 1); rejectChangedReceipt(changed);
        changed = receipts[0]; changed.profileHash = bytes32(uint256(changed.profileHash) ^ 1); rejectChangedReceipt(changed);
        transport(0); requests[0].model.runtime = bytes32(uint256(requests[0].model.runtime) ^ 1);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.MissingReceipt.selector); recordObservation(0); assertNoConsumption();
    }

    function test_UnknownSourcePolicyCannotBeAdmittedByCaller() public {
        transport(0); requests[0].sourcePolicyHash = bytes32(uint256(requests[0].sourcePolicyHash) ^ 1);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.MissingReceipt.selector); recordObservation(0); assertNoConsumption();
    }

    function test_FinalizeRejectsRegistryDriftAfterAllGenuineObservations() public {
        recordAll(); vm.roll(111);
        registry.deregisterOperator(registry.pointAddress(operators[2].x, operators[2].y));
        vm.expectRevert(PeaceFourReportSchnorrConsumer.BadRegistry.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_FinalizeRejectsDuplicatedGenuineProofWithoutPartialConsumption() public {
        recordAll(); proofs[3] = proofs[2];
        vm.expectRevert(PeaceFourReportEvidenceGate.BadHeaderPolicy.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_SourceIndexAliasCannotReuseGenuineCertificate() public {
        transport(0); requests[0].sourceIndex = 1;
        vm.expectRevert(PeaceFourReportSchnorrConsumer.MissingReceipt.selector);
        recordObservation(0); assertNoConsumption();
    }

    function test_SYNTHETIC_STORAGE_FAULT_BothFlagsBlockYesNotAnActualModelResult() public {
        recordAll();
        stdstore.target(address(consumer)).sig("observations(bytes32)").with_key(LayaRequest.key(requests[0]))
            .depth(2).enable_packed_slots().checked_write(true);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.ConflictingSupport.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_SYNTHETIC_STORAGE_FAULT_OppositeOnlyBlocksYesNotAnActualModelResult() public {
        recordAll();
        stdstore.target(address(consumer)).sig("observations(bytes32)").with_key(LayaRequest.key(requests[0]))
            .depth(1).enable_packed_slots().checked_write(false);
        stdstore.target(address(consumer)).sig("observations(bytes32)").with_key(LayaRequest.key(requests[0]))
            .depth(2).enable_packed_slots().checked_write(true);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.ConflictingSupport.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }

    function test_SYNTHETIC_STORAGE_FAULT_NeitherBlocksYesNotAnActualModelResult() public {
        recordAll();
        stdstore.target(address(consumer)).sig("observations(bytes32)").with_key(LayaRequest.key(requests[0]))
            .depth(1).enable_packed_slots().checked_write(false);
        vm.expectRevert(PeaceFourReportSchnorrConsumer.ConflictingSupport.selector);
        consumer.finalize(proofs, inputs, ids); assertNoConsumption();
    }
}
