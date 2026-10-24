// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";
import {SchnorrStakeRegistry} from "../lib/chemistry-schnorr-sdk/src/SchnorrStakeRegistry.sol";
import {GasKillerSDK} from "../lib/chemistry-schnorr-sdk/src/GasKillerSDK.sol";
import {StateChangeHandlerLib} from "../lib/chemistry-schnorr-sdk/src/StateChangeHandlerLib.sol";
import {QuorumSignature} from "../lib/chemistry-schnorr-sdk/src/interface/ISchnorrApprovalRegistry.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/dkim/DKIMVerifier.sol";
import {LayaRequest} from "../src/judge/LayaRequest.sol";
import {PeaceBBCAlertEvidenceGate} from "../src/judge/PeaceBBCAlertEvidenceGate.sol";
import {PeaceBBCSchnorrConsumer} from "../src/judge/PeaceBBCSchnorrConsumer.sol";

/// @notice Actual actor-produced signatures through actual SDK/registry, not mocked
/// positive authentication. Genuine BBC mail must pass at the actual current-time
/// fixture. One publisher cannot establish original-rule source consensus. No live AVS.
contract PeaceBBCSchnorrConsumerTest is Test {
    struct OperatorPoP {
        uint256 x;
        uint256 y;
        uint256 weight;
        uint256 popS;
        address popR;
    }

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
    bytes32 constant ACTOR_FIXTURE_SHA256 = 0x6cbcf08f1dd33039df672e7a33197606da4206d37628162ae6706b98d11f935b;
    address constant TEST_DEPLOYER = address(0xC0FFEE);
    address constant EXPECTED_CONSUMER = 0x6354F0d8b4A45a30Af3D961A0153353a3a048590;
    SchnorrStakeRegistry registry;
    PeaceBBCSchnorrConsumer consumer;
    OperatorPoP[] operators;
    PeaceBBCSchnorrConsumer.Receipt[] receipts;
    Certificate[] certificates;
    EmailProof[] proofs;
    LayaRequest.Request[] requests;
    bytes[] inputs;
    uint32[][] ids;
    uint256 currentClock;
    uint256 expiresAt;
    uint256 signedAt;

    function fileBytes(string memory path) private returns (bytes memory raw) {
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        return vm.ffi(command);
    }

    function setUp() public {
        string memory gatePath = vm.envOr("LAYA_PEACE_GATE_FIXTURE", string(""));
        string memory actorPath = vm.envOr("LAYA_PEACE_SCHNORR_FIXTURE", string(""));
        if (bytes(gatePath).length == 0 || bytes(actorPath).length == 0) {
            vm.skip(true, "Actual actor signature and genuine evidence fixtures required; no positive claim");
            return;
        }
        bytes memory gateRaw = fileBytes(gatePath);
        assertEq(sha256(gateRaw), 0x6fffae4d298c6fd4431a5828f99cad62ebb503d288da87bc64e3b2a24e99f030);
        string memory gateFixture = string(gateRaw);
        bytes memory exponent;
        bytes memory modulus;
        EmailProof memory proof;
        bytes memory exactInput;
        uint32[] memory tokenIds;
        LayaRequest.Request memory request;
        (proof, exponent, modulus, exactInput, tokenIds, request) = abi.decode(
            vm.parseJsonBytes(gateFixture, ".abiHex"), (EmailProof, bytes, bytes, bytes, uint32[], LayaRequest.Request)
        );
        proofs.push(proof);
        inputs.push(exactInput);
        ids.push(tokenIds);
        requests.push(request);
        bytes memory actorRaw = fileBytes(actorPath);
        assertEq(sha256(actorRaw), ACTOR_FIXTURE_SHA256, "Actual actor artifact must be immutably pinned");
        (operators, receipts, certificates) = abi.decode(
            vm.parseJsonBytes(string(actorRaw), ".abiHex"),
            (OperatorPoP[], PeaceBBCSchnorrConsumer.Receipt[], Certificate[])
        );
        assertEq(operators.length, 3);
        assertEq(receipts.length, 1);
        assertEq(certificates.length, 1);
        vm.chainId(31337);
        currentClock = vm.parseJsonUint(gateFixture, ".currentTimeUnix");
        vm.warp(currentClock);
        expiresAt = vm.parseJsonUint(gateFixture, ".expiresAtUnix");
        signedAt = vm.parseJsonUint(gateFixture, ".signedAtUnix");
        assertGe(currentClock, signedAt);
        assertLe(currentClock, expiresAt);
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
        vm.setNonce(TEST_DEPLOYER, 2);
        vm.prank(TEST_DEPLOYER);
        consumer = new PeaceBBCSchnorrConsumer(verifier, proofs[0].publicKeyHash, registry, address(0xA55), requests[0]);
        assertEq(address(consumer), EXPECTED_CONSUMER);
        requests[0].market = address(consumer);
        assertEq(receipts[0].version, 2);
        assertEq(receipts[0].requestKey, LayaRequest.key(requests[0]));
        assertEq(receipts[0].consumer, address(consumer));
        assertEq(receipts[0].contextDomain, consumer.receiptContextDomain());
        assertEq(receipts[0].marketId, 5371292);
        assertEq(receipts[0].modelPinsHash, keccak256(abi.encode(requests[0].model)));
        assertEq(certificates[0].transitionIndex, 0);
        assertEq(certificates[0].refBlock, 109);
        assertEq(certificates[0].targetFunction, consumer.acceptCertifiedReceipt.selector);
        assertEq(certificates[0].digest, consumer.receiptDigest(0, receipts[0]));
        assertEq(certificates[0].payload, consumer.receiptPayload(receipts[0]));
        assertEq(certificates[0].nonSigners.length, 0);
        // Actual independent complete integer runtime must produce A-only support;
        // these inequalities assert the artifact, they never choose signed scores.
        assertGe(receipts[0].aPpm, 550000);
        assertLt(receipts[0].bPpm, 550000);
    }

    function transport(uint256 i) private {
        Certificate memory c = certificates[i];
        assertTrue(registry.isValidSignature(c.digest, c.s, c.Raddr, c.nonSigners, c.refBlock));
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
    }

    function signature(uint256 i) private view returns (QuorumSignature memory) {
        Certificate memory c = certificates[i];
        return QuorumSignature(c.s, c.Raddr, c.nonSigners, c.refBlock);
    }

    function recordObservation(uint256 i) private {
        consumer.recordAuthenticatedObservation(requests[i], proofs[i], inputs[i], ids[i], i, signature(i));
    }

    function assertNoConsumption() private view {
        assertEq(uint256(consumer.decision()), uint256(PeaceBBCSchnorrConsumer.Decision.Unresolved));
        assertEq(consumer.evidenceGate().consumedSourceMask(), 0);
        for (uint256 i; i < 1; ++i) {
            assertFalse(consumer.evidenceGate().consumedRequests(LayaRequest.key(requests[i])));
            assertFalse(consumer.evidenceGate().consumedEmails(proofs[i].emailNullifier));
        }
    }

    function test_RealActorsCurrentBBCAuthenticatedASupportCannotSettleWithoutOriginalSources() public {
        Certificate memory c = certificates[0];
        assertTrue(registry.isValidSignature(c.digest, c.s, c.Raddr, c.nonSigners, c.refBlock));
        uint256 gasBefore = gasleft();
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        console2.log("actual Peace SDK certificate transport caller gas delta", gasBefore - gasleft());
        gasBefore = gasleft();
        recordObservation(0);
        console2.log("current BBC DKIM authenticated observation caller gas delta", gasBefore - gasleft());
        assertEq(consumer.observationCount(), 1);
        (bool recorded, bool a, bool b,) = consumer.observations(LayaRequest.key(requests[0]));
        assertTrue(recorded);
        assertTrue(a);
        assertFalse(b);
        assertEq(consumer.stateTransitionCount(), 1);
        assertFalse(consumer.originalRuleSourceAdmissionEstablished());
        assertFalse(consumer.evidenceGate().originalRuleSourceAdmissionEstablished());
        bytes memory finalizeCall = abi.encodeCall(consumer.finalize, ());
        gasBefore = gasleft();
        (bool settled, bytes memory reason) = address(consumer).call(finalizeCall);
        console2.log("actual Peace finalize SourceAdmissionMissing rejection caller gas delta", gasBefore - gasleft());
        assertFalse(settled);
        assertEq(bytes4(reason), PeaceBBCSchnorrConsumer.SourceAdmissionMissing.selector);
        assertNoConsumption();
    }

    function test_NoReceiptCannotRecordGenuineEmailOrFinalize() public {
        vm.expectRevert(PeaceBBCSchnorrConsumer.MissingReceipt.selector);
        recordObservation(0);
        vm.expectRevert(PeaceBBCSchnorrConsumer.IncompleteObservations.selector);
        consumer.finalize();
        assertNoConsumption();
    }

    function test_DirectReceiptInjectionRejected() public {
        vm.expectRevert(PeaceBBCSchnorrConsumer.NotCertifiedTransition.selector);
        consumer.acceptCertifiedReceipt(receipts[0]);
        assertNoConsumption();
    }

    function test_RealSignatureTamperRejectedWithoutTransition() public {
        Certificate memory c = certificates[0];
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s ^ 1, c.Raddr, c.nonSigners
        );
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function test_RealSignatureCannotAuthenticateChangedScorePayload() public {
        Certificate memory c = certificates[0];
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.bPpm = 1000000;
        bytes memory payload = consumer.receiptPayload(changed);
        bytes32 digest = consumer.receiptDigest(0, changed);
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(
            digest, c.refBlock, payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function rejectChangedReceipt(PeaceBBCSchnorrConsumer.Receipt memory changed) private {
        Certificate memory c = certificates[0];
        bytes memory payload = consumer.receiptPayload(changed);
        bytes32 digest = consumer.receiptDigest(0, changed);
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(
            digest, c.refBlock, payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        assertEq(consumer.stateTransitionCount(), 0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_OriginalCertificateRejectsModifiedExecutionRoot() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.executionRoot = bytes32(uint256(changed.executionRoot) ^ 1);
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongMarket() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.marketId = 5371179;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongChain() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.chainId = 31338;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongRequest() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.requestKey = bytes32(uint256(changed.requestKey) ^ 1);
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongInput() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.inputHash = bytes32(uint256(changed.inputHash) ^ 1);
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongTokenCommitment() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.tokenIdsHash = bytes32(uint256(changed.tokenIdsHash) ^ 1);
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
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        vm.expectRevert(PeaceBBCSchnorrConsumer.AlreadyRecorded.selector);
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
        consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, ns);
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function test_StaleReferenceBlockRejectedByActualSDK() public {
        vm.roll(410); // ref109 + staleMeasure300 < current410
        Certificate memory c = certificates[0];
        vm.expectRevert(GasKillerSDK.StaleBlockNumber.selector);
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        assertEq(consumer.stateTransitionCount(), 0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_FutureAndEqualReferenceBlocksRejectedByActualSDK() public {
        Certificate memory c = certificates[0];
        vm.roll(109); // equal reference block
        vm.expectRevert(GasKillerSDK.FutureBlockNumber.selector);
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        vm.roll(108); // future reference block
        vm.expectRevert(GasKillerSDK.FutureBlockNumber.selector);
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
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

    function test_ExpiredBBCDKIMRejectsEvenPreviouslyTransportedReceipt() public {
        transport(0);
        vm.warp(expiresAt + 1);
        vm.expectRevert(PeaceBBCAlertEvidenceGate.SignatureOutsideValidity.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_CrossChainReceiptRejectedByTypedCallback() public {
        vm.chainId(31338);
        Certificate memory c = certificates[0];
        vm.expectRevert(
            abi.encodeWithSelector(
                StateChangeHandlerLib.RevertingContext.selector,
                uint256(0),
                address(consumer),
                abi.encodeWithSelector(PeaceBBCSchnorrConsumer.BadReceiptContext.selector),
                abi.encodeCall(consumer.acceptCertifiedReceipt, (receipts[0]))
            )
        );
        consumer.verifyAndUpdate(
            c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction, c.s, c.Raddr, c.nonSigners
        );
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function test_OriginalCertificateRejectsChemistryProtocolDomain() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.contextDomain = keccak256("CHEMISTRY_SCHNORR_OBSERVATION_V1");
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsOldReceiptVersion() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.version = 1;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongConsumer() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.consumer = address(0xBAD);
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongModelProfileOrRequestRuntime() public {
        PeaceBBCSchnorrConsumer.Receipt memory changed = receipts[0];
        changed.modelPinsHash = bytes32(uint256(changed.modelPinsHash) ^ 1);
        rejectChangedReceipt(changed);
        changed = receipts[0];
        changed.profileHash = bytes32(uint256(changed.profileHash) ^ 1);
        rejectChangedReceipt(changed);
        transport(0);
        requests[0].model.runtime = bytes32(uint256(requests[0].model.runtime) ^ 1);
        vm.expectRevert(PeaceBBCSchnorrConsumer.MissingReceipt.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_BBCBeforeSignedTimeRejectsEvenTransportedReceipt() public {
        transport(0);
        vm.warp(signedAt - 1);
        vm.expectRevert(PeaceBBCAlertEvidenceGate.SignatureOutsideValidity.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }

    function test_SingleBBCSourcePolicyCannotBeOverriddenByCaller() public {
        transport(0);
        recordObservation(0);
        vm.prank(address(0xBEEF));
        vm.expectRevert(PeaceBBCSchnorrConsumer.SourceAdmissionMissing.selector);
        consumer.finalize();
        assertFalse(consumer.originalRuleSourceAdmissionEstablished());
        assertNoConsumption();
    }

    function test_RegistrySnapshotMutationFailsClosedBeforeObservation() public {
        transport(0);
        vm.roll(111);
        registry.deregisterOperator(registry.pointAddress(operators[2].x, operators[2].y));
        vm.expectRevert(PeaceBBCSchnorrConsumer.BadRegistry.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }
}
