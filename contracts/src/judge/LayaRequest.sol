// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {GoogleAlertBodyParser} from "../lib/GoogleAlertBodyParser.sol";

/// @notice Request/result binding SCAFFOLD, not a Laya runtime or an authenticated oracle.
/// These pure checks authenticate neither RSA signatures nor model execution. A future
/// consumer must derive policy/pins from its own configuration, verify DKIM, reconstruct
/// the model input and canonical tokens, and authenticate execution BEFORE storing a result.
/// There is deliberately no verdict setter, certificate verifier, or settlement entry point.
library LayaRequest {
    uint32 internal constant VERSION = 1;
    uint32 internal constant PARSER_VERSION = 2;
    uint32 internal constant SCALE = 1_000_000;
    // Alert tables count independent A/B support, never a larger-score winner.
    uint8 internal constant ALERT_STUDENT_BASE_SUPPORT_V1 = 3;
    uint32 internal constant ALERT_THRESHOLD_PPM = 550_000;
    bytes32 internal constant REQUEST_DOMAIN = keccak256("LAYA_REQUEST_SCAFFOLD_V1");
    bytes32 internal constant RESULT_DOMAIN = keccak256("LAYA_RESULT_SCAFFOLD_V1");

    struct ModelPins {
        bytes32 weights;
        bytes32 tokenizer;
        bytes32 schema;
        bytes32 arithmetic;
        bytes32 preprocessing;
        bytes32 calibration;
        bytes32 runtime;
        uint32 maxTokens;
    }

    struct Request {
        uint32 version;
        uint256 chainId;
        address market;
        // Hash exact question, A/B predicates, date window and resolution rules.
        bytes32 rulesHash;
        // Hash the entire ordered admissible-source policy, including K and host rules.
        bytes32 sourcePolicyHash;
        uint32 sourceIndex;
        bytes32 emailHash; // keccak256(abi.encode(EmailProof)), including signed metadata
        bytes32 emailNullifier;
        bytes32 canonicalBodySha256;
        uint32 parserVersion;
        bytes32 parserPolicyHash; // pin extraction/cropping semantics, not just MIME decoding
        uint32 bodyOffset;
        uint32 bodyLength;
        bytes32 decodedBytesHash;
        bytes32 inputBytesHash; // exact serialized model input, including rule text
        bytes32 tokenIdsHash; // keccak256(abi.encode(uint32[])), not packed encoding
        uint32 tokenCount;
        ModelPins model;
        uint32 thresholdPpm;
        uint8 decisionPolicy; // a versioned named profile; consumer must pin it
        uint64 expiresAt;
        uint256 nonce; // consumer must persist/consume this; hashing alone does not prevent replay
    }

    struct Result {
        uint32 version;
        bytes32 requestKey;
        bytes32 executionRoot;
        // Independent A/B probabilities, NOT confidence/normalized entropy; no sum-to-one rule.
        uint32 aPpm;
        uint32 bPpm;
    }

    struct SupportFlags {
        bool a;
        bool b;
    }

    error BadVersion();
    error WrongContext();
    error MissingCommitment();
    error BadRange();
    error UnsupportedDecisionPolicy();
    error PolicyThresholdMismatch();
    error Expired();
    error EvidenceMismatch();
    error InputMismatch();
    error RequestMismatch();

    /// @dev Hashes do not imply validity or authentication; validate separately.
    function key(Request memory r) internal pure returns (bytes32) {
        return keccak256(abi.encode(REQUEST_DOMAIN, r));
    }

    /// @param now_ Supplied explicitly for pure checks; a consumer MUST use block.timestamp.
    /// @param chainId_ Consumer MUST use block.chainid, not a submitter-supplied value.
    /// @param market_ Consumer MUST use its own address, not a submitter-supplied value.
    function validate(Request memory r, uint256 now_, uint256 chainId_, address market_) internal pure {
        if (r.version != VERSION || r.parserVersion != PARSER_VERSION) revert BadVersion();
        if (r.chainId == 0 || r.chainId != chainId_ || r.market == address(0) || r.market != market_) {
            revert WrongContext();
        }
        if (
            r.rulesHash == 0 || r.sourcePolicyHash == 0 || r.emailHash == 0 || r.emailNullifier == 0
                || r.canonicalBodySha256 == 0 || r.parserPolicyHash == 0 || r.decodedBytesHash == 0
                || r.inputBytesHash == 0 || r.tokenIdsHash == 0 || r.model.weights == 0 || r.model.tokenizer == 0
                || r.model.schema == 0 || r.model.arithmetic == 0 || r.model.preprocessing == 0
                || r.model.calibration == 0 || r.model.runtime == 0
        ) {
            revert MissingCommitment();
        }
        if (
            r.thresholdPpm == 0 || r.thresholdPpm > SCALE || r.bodyLength == 0 || r.bodyLength > 4096
                || r.bodyOffset > 196608 || r.bodyLength > 196608 - r.bodyOffset || r.tokenCount == 0
                || r.tokenCount > r.model.maxTokens
        ) revert BadRange();
        validatePolicy(r);
        if (now_ > r.expiresAt) revert Expired();
    }

    /// @notice Match full email material and body profile; DOES NOT verify the RSA signature.
    /// Even a synthetically self-consistent email can pass this check. Use IDKIMVerifier too.
    function validateEvidence(Request memory r, EmailProof calldata p) internal pure {
        if (r.version != VERSION || r.parserVersion != PARSER_VERSION) revert BadVersion();
        if (
            r.emailHash != keccak256(abi.encode(p)) || r.emailNullifier != p.emailNullifier
                || p.emailNullifier != keccak256(p.signature) || r.canonicalBodySha256 != sha256(p.canonicalBody)
                || r.bodyOffset != p.bodyOffset || r.bodyLength != p.bodyLength
                || r.decodedBytesHash != keccak256(bytes(p.bodyExcerpt))
                || !GoogleAlertBodyParser.verify(p.header, p.canonicalBody, p.bodyOffset, p.bodyLength, p.bodyExcerpt)
        ) {
            revert EvidenceMismatch();
        }
    }

    /// @notice Commitment equality only. Does NOT prove serialization or canonical tokenization.
    function validateInput(Request memory r, bytes memory input, uint32[] memory ids) internal pure {
        if (
            r.inputBytesHash != keccak256(input) || r.tokenIdsHash != keccak256(abi.encode(ids))
                || r.tokenCount != ids.length
        ) revert InputMismatch();
    }

    /// @notice Independent threshold flags only, not an exclusive verdict or authenticated result.
    /// Both true remains both true, even on exact ties. Missing A/B scores are unsupported.
    function supportFlags(Request memory r, Result memory result) internal pure returns (SupportFlags memory flags) {
        validateResult(r, result);
        flags.a = result.aPpm >= r.thresholdPpm;
        flags.b = result.bPpm >= r.thresholdPpm;
    }

    function validateResult(Request memory r, Result memory result) private pure {
        if (r.version != VERSION || r.parserVersion != PARSER_VERSION || result.version != VERSION) {
            revert BadVersion();
        }
        if (result.requestKey != key(r)) revert RequestMismatch();
        if (result.executionRoot == 0) revert MissingCommitment();
        if (result.aPpm > SCALE || result.bPpm > SCALE || r.thresholdPpm == 0 || r.thresholdPpm > SCALE) {
            revert BadRange();
        }
        validatePolicy(r);
    }

    function validatePolicy(Request memory r) private pure {
        if (r.decisionPolicy != ALERT_STUDENT_BASE_SUPPORT_V1) revert UnsupportedDecisionPolicy();
        if (r.thresholdPpm != ALERT_THRESHOLD_PPM) revert PolicyThresholdMismatch();
    }

    /// @notice A result commitment is NOT an execution certificate.
    function resultKey(Request memory r, Result memory result) internal pure returns (bytes32) {
        return keccak256(abi.encode(RESULT_DOMAIN, result, supportFlags(r, result)));
    }
}
