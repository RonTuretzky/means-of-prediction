// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {PeaceFinalizeGasKillerRelay} from "../src/judge/PeaceFinalizeGasKillerRelay.sol";
import {PeaceFinalizePacketCache} from "../src/judge/PeaceFinalizePacketCache.sol";
import {PeaceFourReportSchnorrConsumer} from "../src/judge/PeaceFourReportSchnorrConsumer.sol";
import {PeaceFourReportEvidenceGate} from "../src/judge/PeaceFourReportEvidenceGate.sol";
import {SchnorrStakeRegistry} from "../lib/chemistry-schnorr-sdk/src/SchnorrStakeRegistry.sol";
import {DKIMRegistry} from "../src/dkim/DKIMRegistry.sol";

/// @notice Same-anchor local fork. Certified calldata is the actual three-actor
/// transaction already accepted on the matched branch, not a forged signature.
contract PeaceFinalizeGasKillerEquivalenceTest is Test {
    address constant CONSUMER = 0xBE48387535e1dE07361eF51B57aaa5758c445D79;
    address constant CACHE = 0x1e0971684da0C0925F2AD73605D61700eD1F1362;
    address constant RELAY = 0x8AEe7622d63609c68a94d1C16398a45446da6332;
    bytes32 constant PACKET_HASH = 0x3dee100be9742fd6f65d80b2a7a1471ab3c0ce768977f97754618d90e402849f;
    bytes32 constant ANCHOR_HASH = 0xe02bc89880aa8b1ae6b1be33b4b34d3b63496d70078a58d7c6d38f1e637ebea4;
    bytes32 constant PRESTATE_HASH = 0xee476a68e7b5601f52626f2453a5ebe15f9ecd1b9b9a1cac20a3bc0248547207;
    bytes32 constant CONTEXT_DOMAIN = 0x643040ecaadb082dfb77410d60d8b3277ba8e44dffed9f0b57f2fd690b59aa7f;
    bytes32 constant ACTOR_FIXTURE_SHA256 = 0x4b4e3b5bd3b8cc0a224d9e55440c4995a2ad9e651bae48b69afe1947c31263b3;
    bytes32 constant MATCHED_TRANSACTION_SHA256 = 0x2b4ad32194b5dd53ec56cec4a62ad87217d8aaa56941cd876f2deb5cd8d3f10d;
    bytes32 constant CERTIFIED_CALLDATA_SHA256 = 0x1a87cbb2f10cda1f4592ea70f019a7b048b16d92527110c62046a9aa415f21c1;
    uint64 constant INCLUSION_TIME = 1792546544;
    uint64 constant NOT_AFTER = 1792599289;

    PeaceFourReportSchnorrConsumer consumer;
    PeaceFourReportEvidenceGate gate;
    PeaceFinalizePacketCache cache;
    PeaceFinalizeGasKillerRelay relay;
    SchnorrStakeRegistry registry;
    DKIMRegistry keys;
    bytes certifiedCalldata;

    function _fileBytes(string memory path) private returns (bytes memory) {
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys; print('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        return vm.ffi(command);
    }

    function setUp() public {
        // Required env vars fail the gated command when missing; no skipped pass.
        bytes memory actor = _fileBytes(vm.envString("LAYA_PEACE_RELAY_ACTOR_FIXTURE"));
        assertEq(sha256(actor), ACTOR_FIXTURE_SHA256, "actual actor artifact pin");
        string memory fixture = string(actor);
        assertEq(vm.parseJsonBytes32(fixture, ".certificate.digest"),
            0xc259b8318d6f4766703dab491b5841864b63131a5548ea71ff8a913c1156f3f8);
        assertEq(vm.parseJsonUint(fixture, ".receipt.anchorBlockNumber"), 129);
        assertEq(vm.parseJsonUint(fixture, ".receipt.executionTimestamp"), 1792546129);
        assertEq(vm.parseJsonBytes32(fixture, ".receipt.preStateHash"), PRESTATE_HASH);
        bytes memory txRaw = _fileBytes(vm.envString("LAYA_PEACE_RELAY_CERTIFIED_TRANSACTION"));
        assertEq(sha256(txRaw), MATCHED_TRANSACTION_SHA256, "accepted transaction pin");
        certifiedCalldata = vm.parseJsonBytes(string(txRaw), ".data");
        assertEq(certifiedCalldata.length, 1156);
        assertEq(sha256(certifiedCalldata), CERTIFIED_CALLDATA_SHA256);
        assertEq(bytes4(certifiedCalldata), bytes4(0x82b35a01));

        vm.createSelectFork("http://127.0.0.1:19545", 129);
        vm.roll(130);
        vm.warp(INCLUSION_TIME);
        assertEq(blockhash(129), ANCHOR_HASH, "wrong fork anchor");
        consumer = PeaceFourReportSchnorrConsumer(CONSUMER);
        cache = PeaceFinalizePacketCache(CACHE);
        relay = PeaceFinalizeGasKillerRelay(RELAY);
        gate = consumer.evidenceGate();
        registry = relay.realRegistry();
        keys = relay.dkimRegistry();
        assertEq(cache.packetHash(), PACKET_HASH);
        assertEq(cache.packetLength(), 215556);
        assertTrue(cache.isSealed());
        assertEq(keccak256(cache.read()), PACKET_HASH);
        assertEq(relay.contextDomain(), CONTEXT_DOMAIN);
        assertEq(relay.stateCommitment(), PRESTATE_HASH);
        _assertUnconsumed();
    }

    function _certified() private returns (bool ok) { (ok,) = RELAY.call(certifiedCalldata); }
    function _direct() private returns (bool ok) { (ok,) = RELAY.call(abi.encodeCall(relay.directExecute, ())); }
    function _assertUnconsumed() private view {
        assertEq(uint256(consumer.decision()), uint256(PeaceFourReportSchnorrConsumer.Decision.Unresolved));
        assertEq(gate.consumedSourceMask(), 0);
        assertEq(relay.nonce(), 0);
        assertEq(relay.stateTransitionCount(), 0);
        for (uint256 i; i < 4; ++i) {
            assertFalse(gate.consumedRequests(consumer.requestKeys(i)));
            assertFalse(gate.consumedEmails(relay.emailNullifiers(i)));
        }
    }
    function _assertRejectedByBoth() private {
        assertFalse(_direct(), "cached direct must reject");
        _assertUnconsumed();
        assertFalse(_certified(), "genuine signed certificate must reject");
        _assertUnconsumed();
    }

    function test_MatchedPositiveAndReplayAreAtomic() public {
        uint256 snap = vm.snapshotState();
        assertTrue(_direct(), "full cached direct positive");
        bytes32 directOutcome = relay.outcomeCommitment();
        assertEq(uint256(consumer.decision()), uint256(PeaceFourReportSchnorrConsumer.Decision.Yes));
        assertEq(gate.consumedSourceMask(), 15);
        assertEq(relay.nonce(), 1);
        assertFalse(_direct(), "direct replay");
        assertTrue(vm.revertToState(snap));
        assertTrue(_certified(), "genuine actor certificate positive");
        assertEq(relay.outcomeCommitment(), directOutcome);
        assertEq(relay.outcomeCommitment(),
            0x1d471043b19975aab91a1716396ac07850fb22a94c679cb2e5fd109e74de4b55);
        assertEq(uint256(consumer.decision()), uint256(PeaceFourReportSchnorrConsumer.Decision.Yes));
        assertEq(gate.consumedSourceMask(), 15);
        assertEq(relay.nonce(), 1);
        assertEq(relay.stateTransitionCount(), 1);
        assertFalse(_certified(), "SDK certificate replay");
        assertFalse(_direct(), "direct replay after certification");
        assertEq(relay.nonce(), 1);
        assertEq(relay.stateTransitionCount(), 1);
    }
    function test_ExpiredOriginalDKIMAndReceiptRejectBoth() public { vm.warp(NOT_AFTER + 1); _assertRejectedByBoth(); }
    function test_RevokedGoogleKeyRejectsBoth() public {
        address registrar = keys.registrar();
        bytes32 keyHash = gate.googleKeyHash();
        vm.prank(registrar); keys.revokeKey("google.com", keyHash); _assertRejectedByBoth();
    }
    function test_OperatorRegistryDriftRejectsBoth() public {
        address owner = registry.owner();
        address firstOperator = vm.addr(101);
        vm.prank(owner); registry.deregisterOperator(firstOperator); _assertRejectedByBoth();
    }
    function test_CorruptedCachedShardRejectsBoth() public { vm.etch(cache.shards(0), hex"00"); _assertRejectedByBoth(); }
    function test_WrongChainRejectsBoth() public { vm.chainId(block.chainid + 1); _assertRejectedByBoth(); }
    function test_ChangedVerifierCodeRejectsBoth() public {
        vm.etch(address(relay.verifier()), hex"00");
        _assertRejectedByBoth();
    }
    function test_AlteredCertificateBytesRejectWithoutConsumption() public {
        bytes memory altered = certifiedCalldata;
        altered[4] = bytes1(uint8(altered[4]) ^ 1); // first signed digest byte
        (bool ok,) = RELAY.call(altered);
        assertFalse(ok, "mutated certificate calldata cannot settle");
        _assertUnconsumed();
    }
    function test_ExpiredSignedAnchorRejectsCertificateButDirectStillValid() public {
        vm.roll(387); // signed anchor 129 is now 258 blocks old
        assertFalse(_certified(), "typed anchor must remain in blockhash window");
        _assertUnconsumed();
        assertTrue(_direct(), "original DKIM proof remains valid at the same clock");
        assertEq(gate.consumedSourceMask(), 15);
    }
}
