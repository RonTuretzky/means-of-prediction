// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {HeaderParser} from "../lib/HeaderParser.sol";
import {BodyParser} from "../lib/BodyParser.sol";
import {LayaRequest} from "./LayaRequest.sol";

/// @notice Isolated, single frozen-request retrospective research evidence receipt.
/// @dev The deploying researcher configures the exact trusted request and Google key.
/// No verdict, model execution certificate, settlement, canonical tokenization, or claim
/// that BBC alone satisfies the original market's credible-reporting consensus rule.
/// A local historical block timestamp is a retrospective test, not current admissibility.
contract NobelAlertEvidenceGate {
    bytes32 public constant DOMAIN_VERSION = keccak256("NOBEL_ALERT_EVIDENCE_RECEIPT_V1");
    bytes32 public constant PROFILE_SHA256 = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 public constant WEIGHTS_SHA256 = 0x5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169;
    string public constant GOOGLE_DOMAIN = "google.com";
    string public constant GOOGLE_SENDER = "googlealerts-noreply@google.com";
    string public constant GOOGLE_SELECTOR = "20251104";

    DKIMVerifier public immutable verifier;
    bytes32 public immutable googleKeyHash;
    address public immutable market;
    bytes32 public immutable frozenRequestKey;
    mapping(bytes32 => bool) public consumedRequests;
    mapping(bytes32 => bool) public consumedEmails;

    error WrongDomain();
    error WrongFrozenRequest();
    error WrongGoogleIdentity();
    error BadHeaderPolicy();
    error SignatureOutsideValidity();
    error BadRSA();
    error AlreadyConsumed();

    event RetrospectiveEvidenceReceived(
        bytes32 indexed receipt, bytes32 indexed requestKey, bytes32 indexed emailNullifier
    );

    /// @dev Constructor arguments are trusted research configuration, not submitter inputs.
    /// The entire request pins rules, demo source policy, market, profile components,
    /// parser/extraction, input, IDs, evidence, expiry, source index and nonce exactly.
    constructor(DKIMVerifier verifier_, bytes32 keyHash_, bytes32 profile_, LayaRequest.Request memory frozen) {
        require(address(verifier_) != address(0) && keyHash_ != 0, "missing verifier/key");
        require(profile_ == PROFILE_SHA256 && frozen.model.weights == WEIGHTS_SHA256, "wrong frozen model");
        LayaRequest.validate(frozen, block.timestamp, block.chainid, frozen.market);
        verifier = verifier_;
        googleKeyHash = keyHash_;
        market = frozen.market;
        frozenRequestKey = LayaRequest.key(frozen);
    }

    function requestDomain() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_VERSION, block.chainid, address(this)));
    }

    function receiveEvidence(
        bytes32 domain,
        LayaRequest.Request calldata request,
        EmailProof calldata proof,
        bytes calldata exactInput,
        uint32[] calldata tokenIds
    ) external returns (bytes32 receipt) {
        if (domain != requestDomain()) revert WrongDomain();
        LayaRequest.validate(request, block.timestamp, block.chainid, market);
        bytes32 requestKey = LayaRequest.key(request);
        if (requestKey != frozenRequestKey) revert WrongFrozenRequest();
        if (consumedRequests[requestKey] || consumedEmails[proof.emailNullifier]) revert AlreadyConsumed();
        validateHeaderPolicy(proof);

        // The existing verifier supports single-part body v1. Derive its header-only
        // proof INTERNALLY from this exact full proof, then authenticate the original
        // complete body with Google MIME v2 through LayaRequest. No second header or
        // independently supplied subject proof can be substituted at this boundary.
        EmailProof memory headerOnly = proof;
        headerOnly.canonicalBody = "";
        headerOnly.bodyExcerpt = "";
        headerOnly.bodyOffset = 0;
        headerOnly.bodyLength = 0;
        if (!verifier.verify(headerOnly)) revert BadRSA();
        LayaRequest.validateEvidence(request, proof);
        // Equality with frozen commitments only; this does not validate tokenizer or
        // serialization semantics and does not authenticate any inference result.
        LayaRequest.validateInput(request, exactInput, tokenIds);

        receipt = keccak256(abi.encode(requestDomain(), requestKey, proof.emailNullifier));
        consumedRequests[requestKey] = true;
        consumedEmails[proof.emailNullifier] = true;
        emit RetrospectiveEvidenceReceived(receipt, requestKey, proof.emailNullifier);
    }

    function validateHeaderPolicy(EmailProof calldata proof) internal view {
        if (
            keccak256(bytes(proof.domainName)) != keccak256(bytes(GOOGLE_DOMAIN))
                || keccak256(bytes(proof.fromAddress)) != keccak256(bytes(GOOGLE_SENDER))
                || proof.publicKeyHash != googleKeyHash
        ) revert WrongGoogleIdentity();
        bytes memory header = proof.header;
        (bytes memory sig, bool present) = HeaderParser.fieldUnique(header, "dkim-signature");
        if (!present) revert BadHeaderPolicy();
        (bytes memory selector, bool hasSelector) = BodyParser.tag(sig, "s");
        (bytes memory version, bool hasVersion) = BodyParser.tag(sig, "v");
        (bytes memory signatureValue, bool hasSignatureValue) = BodyParser.tag(sig, "b");
        if (
            !hasSelector || !BodyParser.same(selector, GOOGLE_SELECTOR) || !hasVersion || !BodyParser.same(version, "1")
                || !hasSignatureValue || signatureValue.length != 0
        ) revert BadHeaderPolicy();
        (bytes memory names, bool hasNames) = BodyParser.tag(sig, "h");
        if (!hasNames) revert BadHeaderPolicy();
        bytes[7] memory required = [
            bytes("from"),
            bytes("subject"),
            bytes("date"),
            bytes("content-type"),
            bytes("to"),
            bytes("message-id"),
            bytes("mime-version")
        ];
        for (uint256 i; i < required.length; ++i) {
            (, bool unique) = HeaderParser.fieldUnique(header, required[i]);
            if (!unique || !listed(names, required[i])) revert BadHeaderPolicy();
        }
        (bytes memory t, bool hasT) = BodyParser.tag(sig, "t");
        (bytes memory x, bool hasX) = BodyParser.tag(sig, "x");
        (uint256 signedAt, bool tOk) = decimal(t);
        (uint256 expiresAt, bool xOk) = decimal(x);
        if (!hasT || !hasX || !tOk || !xOk || expiresAt <= signedAt) revert BadHeaderPolicy();
        if (signedAt > block.timestamp || expiresAt < block.timestamp || proof.timestamp > block.timestamp) {
            revert SignatureOutsideValidity();
        }
    }

    /// @dev h= may oversign absent instances; actual required fields remain singleton.
    function listed(bytes memory names, bytes memory required) private pure returns (bool found) {
        uint256 start;
        for (uint256 i; i <= names.length; ++i) {
            if (i < names.length && names[i] != ":") continue;
            uint256 a = start;
            uint256 end = i;
            while (a < end && (names[a] == " " || names[a] == "\t")) ++a;
            while (end > a && (names[end - 1] == " " || names[end - 1] == "\t")) --end;
            if (a == end) revert BadHeaderPolicy();
            bool equal = end - a == required.length;
            for (uint256 j = a; j < end; ++j) {
                bytes1 c = names[j];
                if (c >= "A" && c <= "Z") c = bytes1(uint8(c) + 32);
                if (!((c >= "a" && c <= "z") || (c >= "0" && c <= "9") || c == "-")) revert BadHeaderPolicy();
                if (equal && c != required[j - a]) equal = false;
            }
            if (equal) found = true;
            start = i + 1;
        }
    }

    function decimal(bytes memory text) private pure returns (uint256 value, bool ok) {
        if (text.length == 0 || text.length > 20) return (0, false);
        for (uint256 i; i < text.length; ++i) {
            if (text[i] < "0" || text[i] > "9") return (0, false);
            value = value * 10 + uint8(text[i]) - 48;
        }
        return (value, true);
    }
}
