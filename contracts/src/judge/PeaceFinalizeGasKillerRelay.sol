// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {GasKillerSDK} from "../../lib/chemistry-schnorr-sdk/src/GasKillerSDK.sol";
import {SchnorrStakeRegistry} from "../../lib/chemistry-schnorr-sdk/src/SchnorrStakeRegistry.sol";
import {StateUpdateType} from "../../lib/chemistry-schnorr-sdk/src/StateChangeHandlerLib.sol";
import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMRegistry} from "../dkim/DKIMRegistry.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {PeaceFourReportSchnorrConsumer} from "./PeaceFourReportSchnorrConsumer.sol";
import {PeaceFourReportEvidenceGate} from "./PeaceFourReportEvidenceGate.sol";
import {PeaceFinalizePacketCache} from "./PeaceFinalizePacketCache.sol";

/// @notice Faithful local comparison: certification never skips original finalization.
/// @dev Both paths load identical calldata and CALL the unchanged full RSA/MIME/policy/
/// time/replay checks and separate gate writes. Cache is transport, not compute saving.
/// Inherited SDK retains the authorized-quorum arbitrary-STORE trust boundary.
contract PeaceFinalizeGasKillerRelay is GasKillerSDK {
    bytes32 public constant DOMAIN_VERSION = keccak256("PEACE_FAITHFUL_EVM_FINALIZE_RELAY_V1");
    uint256 public constant MARKET_ID = 5371292;

    struct ExecutionReceipt {
        uint32 version;
        uint256 chainId;
        address relay;
        address consumer;
        bytes32 contextDomain;
        bytes32 packetHash;
        bytes32 codeContextHash;
        bytes32 preStateHash;
        bytes32 outcomeHash;
        uint64 anchorBlockNumber;
        bytes32 anchorBlockHash;
        uint64 executionTimestamp;
        uint64 notAfter;
        uint256 nonce;
    }
    PeaceFourReportSchnorrConsumer public immutable consumer;
    PeaceFourReportEvidenceGate public immutable evidenceGate;
    PeaceFinalizePacketCache public immutable packetCache;
    SchnorrStakeRegistry public immutable realRegistry;
    DKIMVerifier public immutable verifier;
    DKIMRegistry public immutable dkimRegistry;
    uint256 public immutable contextChainId;
    uint64 public immutable lastValidTimestamp;
    bytes32 public immutable dependencyCodeHash;
    bytes32[4] public emailNullifiers;
    uint256 public nonce;
    error BadConfiguration();
    error NotCertifiedTransition();
    error WrongContext();
    error ChangedCode();
    error WrongPreState();
    error WrongOutcome();
    error BadAnchor();
    error OutsideValidity();
    event FullFinalizeExecuted(bytes32 indexed packetHash, bytes32 indexed outcomeHash, bool certified);

    constructor(
        PeaceFourReportSchnorrConsumer consumer_,
        PeaceFinalizePacketCache cache_,
        SchnorrStakeRegistry registry_,
        address avs
    ) {
        if (
            address(consumer_).code.length == 0 || address(cache_).code.length == 0 || !cache_.isSealed()
                || address(registry_).code.length == 0 || address(consumer_.realRegistry()) != address(registry_)
                || registry_.thresholdNum() != 2 || registry_.thresholdDen() != 3 || registry_.totalWeight() == 0
        ) revert BadConfiguration();
        consumer = consumer_;
        packetCache = cache_;
        realRegistry = registry_;
        evidenceGate = consumer_.evidenceGate();
        verifier = evidenceGate.verifier();
        dkimRegistry = verifier.registry();
        contextChainId = block.chainid;
        bytes memory packet = cache_.read();
        bytes4 selector;
        if (packet.length < 4) revert BadConfiguration();
        assembly ("memory-safe") { selector := mload(add(packet, 32)) }
        if (selector != consumer_.finalize.selector) revert BadConfiguration();
        bytes memory arguments = new bytes(packet.length - 4);
        for (uint256 i; i < arguments.length; ++i) {
            arguments[i] = packet[i + 4];
        }
        (EmailProof[] memory proofs, bytes[] memory inputs, uint32[][] memory ids) =
            abi.decode(arguments, (EmailProof[], bytes[], uint32[][]));
        if (proofs.length != 4 || inputs.length != 4 || ids.length != 4) revert BadConfiguration();
        uint256 minExpiry = type(uint64).max;
        for (uint256 i; i < 4; ++i) {
            emailNullifiers[i] = proofs[i].emailNullifier;
            uint256 expiry = evidenceGate.candidatePin(uint8(i)).expiresAt;
            if (expiry < minExpiry) minExpiry = expiry;
        }
        lastValidTimestamp = uint64(minExpiry);
        _setAvsAddress(avs);
        _setSchnorrRegistry(address(registry_));
        dependencyCodeHash = _dependencyCodeHash();
    }

    function _dependencyCodeHash() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                address(consumer),
                address(consumer).codehash,
                address(evidenceGate),
                address(evidenceGate).codehash,
                address(packetCache),
                address(packetCache).codehash,
                packetCache.manifestHash(),
                address(realRegistry),
                address(realRegistry).codehash,
                address(verifier),
                address(verifier).codehash,
                address(dkimRegistry),
                address(dkimRegistry).codehash
            )
        );
    }

    function codeContextHash() public view returns (bytes32) {
        return keccak256(abi.encode(dependencyCodeHash, address(this).codehash));
    }

    function contextDomain() public view returns (bytes32) {
        return keccak256(
            abi.encode(
                DOMAIN_VERSION,
                contextChainId,
                address(this),
                address(consumer),
                MARKET_ID,
                packetCache.packetHash(),
                codeContextHash()
            )
        );
    }

    function _registrySnapshot() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                realRegistry.aggX(),
                realRegistry.aggY(),
                realRegistry.totalWeight(),
                realRegistry.effectiveBlock(),
                realRegistry.thresholdNum(),
                realRegistry.thresholdDen()
            )
        );
    }

    /// @notice Original consumer/gate state vector, excluding relay nonce/SDK counter.
    function outcomeCommitment() public view returns (bytes32) {
        bytes32[4] memory reports;
        for (uint256 i; i < 4; ++i) {
            bytes32 key = consumer.requestKeys(i);
            (bool recorded, bool a, bool b, bytes32 receiptHash) = consumer.observations(key);
            reports[i] = keccak256(
                abi.encode(
                    key,
                    recorded,
                    a,
                    b,
                    receiptHash,
                    keccak256(abi.encode(consumer.receiptOf(key))),
                    evidenceGate.consumedRequests(key),
                    emailNullifiers[i],
                    evidenceGate.consumedEmails(emailNullifiers[i])
                )
            );
        }
        (bytes memory modulus, bytes memory exponent, bool valid) =
            dkimRegistry.keyData("google.com", evidenceGate.googleKeyHash());
        return keccak256(
            abi.encode(
                contextDomain(),
                consumer.decision(),
                consumer.observationCount(),
                consumer.supportingSourceMask(),
                consumer.anyBSupport(),
                evidenceGate.consumedSourceMask(),
                reports,
                _registrySnapshot(),
                consumer.registrySnapshotHash(),
                keccak256(modulus),
                keccak256(exponent),
                valid
            )
        );
    }

    function stateCommitment() public view returns (bytes32) {
        return keccak256(abi.encode(outcomeCommitment(), nonce));
    }

    function _execute(bool certified) private returns (bytes32 outcomeHash) {
        if (block.chainid != contextChainId) revert WrongContext();
        if (_dependencyCodeHash() != dependencyCodeHash) revert ChangedCode();
        bytes memory packet = packetCache.read();
        (bool success, bytes memory returned) = address(consumer).call(packet);
        if (!success) {
            assembly ("memory-safe") { revert(add(returned, 32), mload(returned)) }
        }
        if (
            returned.length != 0 || consumer.decision() != PeaceFourReportSchnorrConsumer.Decision.Yes
                || evidenceGate.consumedSourceMask() != 15
        ) revert WrongOutcome();
        for (uint256 i; i < 4; ++i) {
            if (
                !evidenceGate.consumedRequests(consumer.requestKeys(i))
                    || !evidenceGate.consumedEmails(emailNullifiers[i])
            ) revert WrongOutcome();
        }
        ++nonce;
        outcomeHash = outcomeCommitment();
        emit FullFinalizeExecuted(packetCache.packetHash(), outcomeHash, certified);
    }

    function directExecute() external returns (bytes32 outcomeHash) {
        if (inTransition()) revert NotCertifiedTransition();
        return _execute(false);
    }

    function receiptPayload(ExecutionReceipt memory receipt) public view returns (bytes memory) {
        StateUpdateType[] memory types = new StateUpdateType[](1);
        types[0] = StateUpdateType.CALL;
        bytes[] memory args = new bytes[](1);
        args[0] = abi.encode(address(this), uint256(0), abi.encodeCall(this.acceptCertifiedExecution, (receipt)));
        return abi.encode(types, args);
    }

    function receiptDigest(uint256 transitionIndex, ExecutionReceipt memory receipt) public view returns (bytes32) {
        return sha256(
            abi.encode(transitionIndex, address(this), this.acceptCertifiedExecution.selector, receiptPayload(receipt))
        );
    }

    function acceptCertifiedExecution(ExecutionReceipt calldata receipt) external {
        if (msg.sender != address(this) || !inTransition()) revert NotCertifiedTransition();
        if (
            receipt.version != 1 || receipt.chainId != contextChainId || block.chainid != contextChainId
                || receipt.relay != address(this) || receipt.consumer != address(consumer)
                || receipt.contextDomain != contextDomain() || receipt.packetHash != packetCache.packetHash()
                || receipt.codeContextHash != codeContextHash() || receipt.nonce != nonce
        ) revert WrongContext();
        // This signed execution anchor is separate from the SDK's unsigned stake-reference selector.
        if (
            receipt.anchorBlockNumber >= block.number || block.number - receipt.anchorBlockNumber > 256
                || receipt.anchorBlockHash == 0 || blockhash(receipt.anchorBlockNumber) != receipt.anchorBlockHash
        ) revert BadAnchor();
        if (
            receipt.notAfter != lastValidTimestamp || block.timestamp < receipt.executionTimestamp
                || block.timestamp > receipt.notAfter
        ) revert OutsideValidity();
        if (stateCommitment() != receipt.preStateHash) revert WrongPreState();
        bytes32 actual = _execute(true); // Full original authentication runs again at settlement.
        if (actual != receipt.outcomeHash) revert WrongOutcome();
    }
}
