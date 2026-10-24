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
import {ChemistryAlertEvidenceGate} from "../src/judge/ChemistryAlertEvidenceGate.sol";
import {ChemistrySchnorrConsumer} from "../src/judge/ChemistrySchnorrConsumer.sol";

/// @notice Actual actor-produced signatures through actual SDK/registry, not mocked
/// positive authentication. Original expired mail passes only in LOCAL HISTORICAL
/// REPLAY. No network, production operator registration, deployment or settlement.
contract ChemistrySchnorrConsumerTest is Test {
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
        0xbc47726e94ee47e5e1aa021c382dcf58e340124c068743e453b359b7645a3cc5;
    address constant TEST_DEPLOYER = address(0xC0FFEE);
    address constant EXPECTED_CONSUMER = 0x705d7dB00e7E0294f090F38DC2775F46Ec861B6e;
    SchnorrStakeRegistry registry;
    ChemistrySchnorrConsumer consumer;
    OperatorPoP[] operators;
    ChemistrySchnorrConsumer.Receipt[] receipts;
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
        string memory gatePath = vm.envOr("LAYA_CHEMISTRY_GATE_FIXTURE", string(""));
        string memory actorPath = vm.envOr("LAYA_CHEMISTRY_SCHNORR_FIXTURE", string(""));
        if (bytes(gatePath).length == 0 || bytes(actorPath).length == 0) {
            vm.skip(true, "Actual actor signature and genuine evidence fixtures required; no positive claim");
            return;
        }
        bytes memory gateRaw = fileBytes(gatePath);
        assertEq(sha256(gateRaw), 0x3397f4b408d083efcb885fb627d990bac0b498cc837a6b1b086f48e3fc084327);
        string memory gateFixture = string(gateRaw);
        bytes memory exponent;
        bytes memory modulus;
        (proofs, exponent, modulus, inputs, ids, requests) = abi.decode(vm.parseJsonBytes(gateFixture, ".abiHex"),
            (EmailProof[], bytes, bytes, bytes[], uint32[][], LayaRequest.Request[]));
        bytes memory actorRaw = fileBytes(actorPath);
        assertEq(sha256(actorRaw), ACTOR_FIXTURE_SHA256, "Actual actor artifact must be immutably pinned");
        (operators, receipts, certificates) = abi.decode(vm.parseJsonBytes(string(actorRaw), ".abiHex"),
            (OperatorPoP[], ChemistrySchnorrConsumer.Receipt[], Certificate[]));
        assertEq(operators.length, 3);
        assertEq(receipts.length, 3);
        assertEq(certificates.length, 3);
        vm.chainId(31337);
        vm.warp(vm.parseJsonUint(gateFixture, ".validationTimeUnix"));
        currentClock = vm.parseJsonUint(gateFixture, ".currentTimeUnix");
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
        vm.setNonce(TEST_DEPLOYER, 1);
        vm.prank(TEST_DEPLOYER);
        consumer = new ChemistrySchnorrConsumer(verifier, proofs[0].publicKeyHash, registry,
            address(0xA55), requests, false);
        assertEq(address(consumer), EXPECTED_CONSUMER);
        for (uint256 i; i < 3; ++i) {
            requests[i].market = address(consumer);
            assertEq(receipts[i].requestKey, LayaRequest.key(requests[i]));
            assertEq(receipts[i].consumer, address(consumer));
            assertEq(receipts[i].modelPinsHash, keccak256(abi.encode(requests[i].model)));
            assertEq(certificates[i].transitionIndex, i);
            assertEq(certificates[i].refBlock, 109);
            assertEq(certificates[i].targetFunction, consumer.acceptCertifiedReceipt.selector);
            assertEq(certificates[i].digest, consumer.receiptDigest(i, receipts[i]));
            assertEq(certificates[i].payload, consumer.receiptPayload(receipts[i]));
            assertEq(certificates[i].nonSigners.length, 0, "Actual fixture is all three public TEST operators");
            // These are the actual independently recomputed results, not positive
            // settlement branch fixtures. All three versions must remain abstentions.
            assertLt(receipts[i].aPpm, 550000);
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
        assertEq(uint256(consumer.decision()), uint256(ChemistrySchnorrConsumer.Decision.Unresolved));
        assertEq(consumer.evidenceGate().consumedSourceMask(), 0);
        for (uint256 i; i < 3; ++i) {
            assertFalse(consumer.evidenceGate().consumedRequests(LayaRequest.key(requests[i])));
            assertFalse(consumer.evidenceGate().consumedEmails(proofs[i].emailNullifier));
        }
    }

    function test_RealActorsAllThreeAuthenticatedAbstentionsRejectSettlement() public {
        for (uint256 i; i < 3; ++i) {
            Certificate memory c = certificates[i];
            assertTrue(registry.isValidSignature(c.digest, c.s, c.Raddr, c.nonSigners, c.refBlock));
            uint256 gasBefore = gasleft();
            consumer.verifyAndUpdate(c.digest, c.refBlock, c.payload, c.transitionIndex, c.targetFunction,
                c.s, c.Raddr, c.nonSigners);
            console2.log("actual SDK certificate transport caller gas delta", i, gasBefore - gasleft());
            gasBefore = gasleft();
            recordObservation(i);
            console2.log("DKIM authenticated observation caller gas delta", i, gasBefore - gasleft());
            assertEq(consumer.observationCount(), i + 1);
            (bool recorded, bool a, bool b,) = consumer.observations(LayaRequest.key(requests[i]));
            assertTrue(recorded);
            assertFalse(a);
            assertFalse(b);
        }
        assertEq(consumer.stateTransitionCount(), 3);
        assertEq(consumer.supportingSourceMask(), 0);
        assertFalse(consumer.anyASupport());
        bytes memory finalizeCall = abi.encodeCall(consumer.finalize, (proofs, inputs, ids));
        uint256 gasBeforeFinalize = gasleft();
        (bool settled, bytes memory reason) = address(consumer).call(finalizeCall);
        console2.log("actual finalize InsufficientSupport rejection caller gas delta", gasBeforeFinalize - gasleft());
        assertFalse(settled);
        assertEq(bytes4(reason), ChemistrySchnorrConsumer.InsufficientSupport.selector);
        assertNoConsumption();
    }

    function test_NoReceiptCannotRecordGenuineEmailOrFinalize() public {
        vm.expectRevert(ChemistrySchnorrConsumer.MissingReceipt.selector);
        recordObservation(0);
        vm.expectRevert(ChemistrySchnorrConsumer.IncompleteObservations.selector);
        consumer.finalize(proofs, inputs, ids);
        assertNoConsumption();
    }

    function test_DirectReceiptInjectionRejected() public {
        vm.expectRevert(ChemistrySchnorrConsumer.NotCertifiedTransition.selector);
        consumer.acceptCertifiedReceipt(receipts[0]);
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
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
        changed.bPpm = 1000000;
        bytes memory payload = consumer.receiptPayload(changed);
        bytes32 digest = consumer.receiptDigest(0, changed);
        vm.expectRevert(GasKillerSDK.InvalidQuorumSignature.selector);
        consumer.verifyAndUpdate(digest, c.refBlock, payload, c.transitionIndex, c.targetFunction,
            c.s, c.Raddr, c.nonSigners);
        assertEq(consumer.stateTransitionCount(), 0);
        assertNoConsumption();
    }

    function rejectChangedReceipt(ChemistrySchnorrConsumer.Receipt memory changed) private {
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
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
        changed.executionRoot = bytes32(uint256(changed.executionRoot) ^ 1);
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongMarket() public {
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
        changed.marketId = 5371178;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongChain() public {
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
        changed.chainId = 31338;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongRequest() public {
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
        changed.requestKey = receipts[1].requestKey;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongInput() public {
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
        changed.inputHash = receipts[1].inputHash;
        rejectChangedReceipt(changed);
    }

    function test_OriginalCertificateRejectsWrongTokenCommitment() public {
        ChemistrySchnorrConsumer.Receipt memory changed = receipts[0];
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
        vm.expectRevert(ChemistrySchnorrConsumer.AlreadyRecorded.selector);
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

    function test_ExpiredOriginalDKIMFailsAtActualCurrentClock() public {
        transport(0);
        vm.warp(currentClock);
        vm.expectRevert(ChemistryAlertEvidenceGate.SignatureOutsideValidity.selector);
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
            abi.encodeWithSelector(ChemistrySchnorrConsumer.BadReceiptContext.selector),
            abi.encodeCall(consumer.acceptCertifiedReceipt, (receipts[0]))
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
        vm.expectRevert(ChemistrySchnorrConsumer.BadRegistry.selector);
        recordObservation(0);
        assertEq(consumer.observationCount(), 0);
        assertNoConsumption();
    }
}
