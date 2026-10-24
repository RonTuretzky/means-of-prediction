// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {GasKillerSDK} from "../../lib/chemistry-schnorr-sdk/src/GasKillerSDK.sol";
import {SchnorrStakeRegistry} from "../../lib/chemistry-schnorr-sdk/src/SchnorrStakeRegistry.sol";
import {QuorumSignature} from "../../lib/chemistry-schnorr-sdk/src/interface/ISchnorrApprovalRegistry.sol";
import {StateUpdateType} from "../../lib/chemistry-schnorr-sdk/src/StateChangeHandlerLib.sol";
import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {LayaRequest} from "./LayaRequest.sol";
import {ChemistryAlertEvidenceGate} from "./ChemistryAlertEvidenceGate.sol";

/// @notice No-funds local replay through the actual Schnorr SDK and registry.
/// @dev Public TEST committee, not production registration or live AVS. Operators
/// run the complete pinned CPU model before signing; this is not an EVM model
/// execution proof. Google authenticates relay bytes, not publisher truth. Expired
/// original DKIM signatures only pass at the explicit LOCAL HISTORICAL REPLAY clock.
/// The inherited SDK permits arbitrary quorum-signed STORE patches, including to
/// observations/decision. This is an authorized quorum trust boundary: the second
/// signature check protects this typed observation entrypoint, not the contract
/// against a malicious authorized quorum signing arbitrary storage writes.
contract ChemistrySchnorrConsumer is GasKillerSDK {
    uint256 public constant MARKET_ID = 5371179;
    bytes32 public constant PROFILE_HASH = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;

    struct Receipt {
        uint32 version;
        uint256 chainId;
        address consumer;
        uint256 marketId;
        bytes32 requestKey;
        bytes32 inputHash;
        bytes32 tokenIdsHash;
        bytes32 modelPinsHash;
        bytes32 profileHash;
        bytes32 executionRoot;
        uint32 qPpm;
        uint32 aPpm;
        uint32 bPpm;
        uint64 expiresAt;
        uint256 nonce;
    }

    struct Observation {
        bool recorded;
        bool a;
        bool b;
        bytes32 receiptHash;
    }
    enum Decision {
        Unresolved,
        No
    }

    SchnorrStakeRegistry public immutable realRegistry;
    bytes32 public immutable registryCodeHash;
    bytes32 public immutable registrySnapshotHash;
    uint256 public immutable contextChainId;
    ChemistryAlertEvidenceGate public immutable evidenceGate;
    bool public immutable exhaustiveSourceAdmission;
    bytes32[3] public requestKeys;
    mapping(bytes32 => LayaRequest.Request) private admittedRequests;
    mapping(bytes32 => Receipt) private receipts;
    mapping(bytes32 => Observation) public observations;
    uint8 public observationCount;
    uint8 public supportingSourceMask;
    bool public anyASupport;
    Decision public decision;

    error BadRegistry();
    error BadReceiptContext();
    error NotCertifiedTransition();
    error MissingReceipt();
    error InvalidExecutionCertificate();
    error AlreadyRecorded();
    error IncompleteObservations();
    error ConflictingSupport();
    error InsufficientSupport();
    error SourceAdmissionMissing();
    error BadEvidenceArray();

    event ReceiptTransported(bytes32 indexed requestKey, bytes32 indexed executionRoot, uint32 aPpm, uint32 bPpm);
    event ObservationRecorded(bytes32 indexed requestKey, bool a, bool b);
    event LocalNoDecision(uint256 indexed marketId);

    constructor(
        DKIMVerifier verifier,
        bytes32 googleKeyHash,
        SchnorrStakeRegistry registry,
        address avs,
        LayaRequest.Request[] memory requests,
        bool admittedSourceSet
    ) {
        if (
            address(registry).code.length == 0 || registry.totalWeight() == 0 || registry.thresholdNum() != 2
                || registry.thresholdDen() != 3 || requests.length != 3
        ) revert BadRegistry();
        realRegistry = registry;
        registryCodeHash = address(registry).codehash;
        registrySnapshotHash = snapshot(registry);
        contextChainId = block.chainid;
        _setAvsAddress(avs);
        _setSchnorrRegistry(address(registry));
        exhaustiveSourceAdmission = admittedSourceSet;
        for (uint256 i; i < 3; ++i) {
            requests[i].market = address(this);
        }
        evidenceGate = new ChemistryAlertEvidenceGate(
            verifier,
            address(this),
            googleKeyHash,
            PROFILE_HASH,
            requests[0].rulesHash,
            requests[0].sourcePolicyHash,
            requests
        );
        for (uint256 i; i < 3; ++i) {
            bytes32 key = LayaRequest.key(requests[i]);
            requestKeys[i] = key;
            admittedRequests[key] = requests[i];
        }
    }

    function snapshot(SchnorrStakeRegistry registry) private view returns (bytes32) {
        return keccak256(
            abi.encode(
                registry.aggX(),
                registry.aggY(),
                registry.totalWeight(),
                registry.effectiveBlock(),
                registry.thresholdNum(),
                registry.thresholdDen()
            )
        );
    }

    function validateRegistry() private view {
        if (address(realRegistry).codehash != registryCodeHash || snapshot(realRegistry) != registrySnapshotHash) {
            revert BadRegistry();
        }
    }

    function validateReceipt(Receipt memory receipt) private view returns (LayaRequest.Request memory request) {
        request = admittedRequests[receipt.requestKey];
        if (
            request.version == 0 || receipt.version != 1 || receipt.chainId != contextChainId
                || block.chainid != contextChainId || receipt.consumer != address(this) || receipt.marketId != MARKET_ID
                || receipt.inputHash != request.inputBytesHash || receipt.tokenIdsHash != request.tokenIdsHash
                || receipt.modelPinsHash != keccak256(abi.encode(request.model)) || receipt.profileHash != PROFILE_HASH
                || receipt.executionRoot == 0 || receipt.qPpm > 1_000_000 || receipt.aPpm > 1_000_000
                || receipt.bPpm > 1_000_000 || receipt.expiresAt != request.expiresAt || receipt.nonce != request.nonce
        ) {
            revert BadReceiptContext();
        }
        LayaRequest.validate(request, block.timestamp, block.chainid, address(this));
    }

    /// @notice Canonical signed SDK update: exactly one typed zero-value self-CALL.
    function receiptPayload(Receipt memory receipt) public view returns (bytes memory) {
        StateUpdateType[] memory types = new StateUpdateType[](1);
        types[0] = StateUpdateType.CALL;
        bytes[] memory args = new bytes[](1);
        args[0] = abi.encode(address(this), uint256(0), abi.encodeCall(this.acceptCertifiedReceipt, (receipt)));
        return abi.encode(types, args);
    }

    function receiptDigest(uint256 transitionIndex, Receipt memory receipt) public view returns (bytes32) {
        return sha256(
            abi.encode(transitionIndex, address(this), this.acceptCertifiedReceipt.selector, receiptPayload(receipt))
        );
    }

    /// @dev A second immutable-registry signature check precedes the typed
    /// observation function. This does not restrict arbitrary SDK STORE patches.
    function acceptCertifiedReceipt(Receipt calldata receipt) external {
        if (msg.sender != address(this) || !inTransition()) revert NotCertifiedTransition();
        validateRegistry();
        validateReceipt(receipt);
        if (receipts[receipt.requestKey].version != 0) revert AlreadyRecorded();
        receipts[receipt.requestKey] = receipt;
        emit ReceiptTransported(receipt.requestKey, receipt.executionRoot, receipt.aPpm, receipt.bPpm);
    }

    function receiptOf(bytes32 key) external view returns (Receipt memory) {
        if (inTransition()) revert NotCertifiedTransition();
        return receipts[key];
    }

    function recordAuthenticatedObservation(
        LayaRequest.Request calldata request,
        EmailProof calldata proof,
        bytes calldata exactInput,
        uint32[] calldata tokenIds,
        uint256 transitionIndex,
        QuorumSignature calldata sig
    ) external {
        if (inTransition()) revert NotCertifiedTransition();
        bytes32 key = LayaRequest.key(request);
        if (observations[key].recorded) revert AlreadyRecorded();
        Receipt memory receipt = receipts[key];
        if (receipt.version == 0) revert MissingReceipt();
        validateRegistry();
        validateReceipt(receipt);
        if (
            sig.refBlock > type(uint32).max || sig.refBlock >= block.number || sig.refBlock + 300 < block.number
                || !realRegistry.isValidSignature(
                    receiptDigest(transitionIndex, receipt), sig.s, sig.Raddr, sig.nonSigners, sig.refBlock
                )
        ) revert InvalidExecutionCertificate();
        evidenceGate.verifyEvidence(evidenceGate.requestDomain(), request, proof, exactInput, tokenIds);
        LayaRequest.Result memory result = LayaRequest.Result(1, key, receipt.executionRoot, receipt.aPpm, receipt.bPpm);
        LayaRequest.SupportFlags memory flags = LayaRequest.supportFlags(request, result);
        observations[key] = Observation(true, flags.a, flags.b, keccak256(abi.encode(receipt)));
        ++observationCount;
        anyASupport = anyASupport || flags.a;
        if (flags.b && !flags.a) supportingSourceMask |= uint8(1 << request.sourceIndex);
        emit ObservationRecorded(key, flags.a, flags.b);
    }

    /// @notice Actual three abstentions reject here before consuming any email.
    function finalize(EmailProof[] calldata proofs, bytes[] calldata inputs, uint32[][] calldata ids) external {
        if (inTransition()) revert NotCertifiedTransition();
        if (observationCount != 3) revert IncompleteObservations();
        if (anyASupport) revert ConflictingSupport();
        if (supportingSourceMask != 3) revert InsufficientSupport();
        if (!exhaustiveSourceAdmission) revert SourceAdmissionMissing();
        if (proofs.length != 3 || inputs.length != 3 || ids.length != 3) revert BadEvidenceArray();
        if (decision != Decision.Unresolved) revert AlreadyRecorded();
        for (uint256 i; i < 3; ++i) {
            LayaRequest.Request memory request = admittedRequests[requestKeys[i]];
            Observation memory observed = observations[requestKeys[i]];
            uint8 bit = uint8(1 << request.sourceIndex);
            if (observed.b && !observed.a && evidenceGate.consumedSourceMask() & bit == 0) {
                evidenceGate.consumeEvidence(evidenceGate.requestDomain(), request, proofs[i], inputs[i], ids[i]);
            }
        }
        if (evidenceGate.consumedSourceMask() != 3) revert InsufficientSupport();
        decision = Decision.No;
        emit LocalNoDecision(MARKET_ID);
    }
}
