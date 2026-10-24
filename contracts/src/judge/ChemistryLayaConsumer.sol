// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {IBLSSignatureChecker} from "@eigenlayer-middleware/interfaces/IBLSSignatureChecker.sol";
import {LayaRequest} from "./LayaRequest.sol";
import {ChemistryAlertEvidenceGate} from "./ChemistryAlertEvidenceGate.sol";
import {ChemistryLayaResultInbox} from "./ChemistryLayaResultInbox.sol";

/// @notice Local, no-funds Chemistry decision consumer. No production market changed.
/// @dev Two B-only independent sources and an explicitly admitted exhaustive winner
/// set are required for No. Abstention/conflict cannot consume evidence or settle.
/// This constructor configuration is human source admission, not proof of truth.
contract ChemistryLayaConsumer {
    enum Decision {
        Unresolved,
        No
    }

    struct Observation {
        bool recorded;
        bool supportsA;
        bool supportsB;
        bytes32 resultKey;
    }

    ChemistryAlertEvidenceGate public immutable evidenceGate;
    ChemistryLayaResultInbox public immutable resultInbox;
    bool public immutable exhaustiveSourceAdmission;
    mapping(bytes32 => Observation) public observations;
    Decision public decision;
    uint8 public observationCount;
    bool public anyASupport;
    error ObservationAlreadyRecorded();
    event Observed(bytes32 indexed requestKey, bool supportsA, bool supportsB, uint32 aPpm, uint32 bPpm);
    event LocalNoDecision(uint256 indexed marketId, uint8 sourceMask);

    constructor(
        DKIMVerifier verifier,
        bytes32 googleKeyHash,
        address avs,
        IBLSSignatureChecker checker,
        bytes memory expectedQuorums,
        LayaRequest.Request[] memory requests,
        bool admittedExhaustiveSourceSet
    ) {
        // Only local consumer identity is rebound; evidence/model policy stays frozen.
        for (uint256 i; i < requests.length; ++i) {
            requests[i].market = address(this);
        }
        evidenceGate = new ChemistryAlertEvidenceGate(
            verifier,
            address(this),
            googleKeyHash,
            0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835,
            requests[0].rulesHash,
            requests[0].sourcePolicyHash,
            requests
        );
        resultInbox = new ChemistryLayaResultInbox(avs, checker, expectedQuorums, address(this), requests);
        exhaustiveSourceAdmission = admittedExhaustiveSourceSet;
    }

    function reviewEvidence(
        LayaRequest.Request calldata request,
        EmailProof calldata proof,
        bytes calldata exactInput,
        uint32[] calldata tokenIds
    ) external view returns (bytes32, uint8) {
        return evidenceGate.verifyEvidence(evidenceGate.requestDomain(), request, proof, exactInput, tokenIds);
    }

    /// @notice No caller-provided scores. Absent real quorum certification fails closed.
    function recordAuthenticatedObservation(
        LayaRequest.Request calldata request,
        EmailProof calldata proof,
        bytes calldata exactInput,
        uint32[] calldata tokenIds
    ) external {
        bytes32 key = LayaRequest.key(request);
        if (observations[key].recorded) revert ObservationAlreadyRecorded();
        LayaRequest.Result memory result = resultInbox.resultOf(key);
        evidenceGate.verifyEvidence(evidenceGate.requestDomain(), request, proof, exactInput, tokenIds);
        LayaRequest.SupportFlags memory flags = LayaRequest.supportFlags(request, result);
        observations[key] = Observation(true, flags.a, flags.b, LayaRequest.resultKey(request, result));
        ++observationCount;
        anyASupport = anyASupport || flags.a;
        emit Observed(key, flags.a, flags.b, result.aPpm, result.bPpm);
        if (exhaustiveSourceAdmission && flags.b && !flags.a) {
            // A later Reuters variant cannot add another source or cause a duplicate
            // consumption failure; its distinct authenticated scores remain recorded.
            uint8 bit = uint8(1 << request.sourceIndex);
            if (evidenceGate.consumedSourceMask() & bit == 0) {
                evidenceGate.consumeEvidence(evidenceGate.requestDomain(), request, proof, exactInput, tokenIds);
            }
        }
        // Evaluate every preselected version before deciding. A conflicting later
        // Reuters version must not be hidden by settling after just the first two.
        if (
            exhaustiveSourceAdmission && observationCount == 3 && !anyASupport && evidenceGate.consumedSourceMask() == 3
                && decision == Decision.Unresolved
        ) {
            decision = Decision.No;
            emit LocalNoDecision(5371179, 3);
        }
    }
}
