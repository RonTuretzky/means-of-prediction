// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {HeaderParser} from "../lib/HeaderParser.sol";
import {BodyParser} from "../lib/BodyParser.sol";
import {LayaRequest} from "./LayaRequest.sol";

/// @notice One frozen BBC Google Alert observation, not original-market source consensus.
/// @dev Google RSA authenticates the relay's signed bytes, not BBC authorship/truth.
/// This gate does not authenticate model execution, implement tokenization or settle a
/// market. A consumer must authenticate its result separately. The original rule permits
/// first official announcement or credible-reporting consensus; this one-publisher
/// observation establishes neither. Old Nobel and Chemistry artifacts remain separate.
contract PeaceBBCAlertEvidenceGate {
    uint256 public constant MARKET_ID = 5371292;
    bytes32 public constant DOMAIN_VERSION = keccak256("PEACE_BBC_ALERT_OBSERVATION_V1");
    bytes32 public constant ORIGINAL_RULES_SHA256 =
        0xf1ba951f9767de4eae4f2562b22bc4ad43db741fe3d30cecc5112a93eafece6d;
    bytes32 public constant PROFILE_SHA256 =
        0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 public constant WEIGHTS_SHA256 =
        0x5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169;
    bytes32 public constant RAW_MESSAGE_SHA256 =
        0x8d6693baaf144f1366db221b970639e5f6028218f5dce91b492c17a4b49dc167;
    bytes32 public constant CANONICAL_HEADER_SHA256 =
        0x21d51e434d69f0e402759041b46d92fc792cf4953425243169ee8bae3645fa43;
    bytes32 public constant CANONICAL_BODY_SHA256 =
        0xef09cd6700414ff97c243c6c7b564b457c19db3efdc26a0e84033bd033e939b4;
    uint256 public constant CANONICAL_BODY_BYTES = 20461;
    uint32 public constant BODY_OFFSET = 8078;
    uint32 public constant ENCODED_WINDOW_BYTES = 1265;
    uint256 public constant GOOGLE_SIGNED_AT = 1792292308;
    uint256 public constant GOOGLE_EXPIRES_AT = 1792897108;
    // Exact new Peace freeze and source policy; never reuse Chemistry request pins.
    bytes32 public constant FROZEN_RULES_HASH =
        0x462459c8c26ce29e120e38fdf3f702eb9529ff5c78771149ba248c1d74d0830e;
    bytes32 public constant FROZEN_SOURCE_POLICY_HASH =
        0xc2ef2530c40fccf7d0ea05380b084df8975d4e86a7452606f0ca0956142bdf94;
    bytes32 public constant FROZEN_MODEL_PINS_HASH =
        0xb5d1d4e25d6eac84cfc3cc6e8b5f80ad015e1267ebc8ac7fc51db48f5b833c3d;
    bytes32 public constant FROZEN_PARSER_POLICY_HASH =
        0xccec8f85d8bca9d872c45f8e104e361f5f65b64b37b35251950fcd3142beaa4c;
    bytes32 public constant FROZEN_GOOGLE_KEY_HASH =
        0xf970943fe89bae0dde33dcef7dba4398d6cc1ac5c04a3a7e4160b4d4ea82b0fa;
    string public constant GOOGLE_DOMAIN = "google.com";
    string public constant GOOGLE_SENDER = "googlealerts-noreply@google.com";
    string public constant GOOGLE_SELECTOR = "20251104";

    struct Admission { bool allowed; uint8 sourceGroup; uint8 queryVariant; }
    DKIMVerifier public immutable verifier;
    address public immutable authorizedConsumer;
    bytes32 public immutable googleKeyHash;
    bytes32 public immutable frozenRequestKey;
    mapping(bytes32 => Admission) public frozenRequestKeys;
    mapping(bytes32 => bool) public consumedRequests;
    mapping(bytes32 => bool) public consumedEmails;
    uint8 public consumedSourceMask; // BBC observation bit only; not a consensus counter.

    error NotConsumer();
    error WrongDomain();
    error WrongFrozenRequest();
    error WrongFrozenCandidate();
    error WrongGoogleIdentity();
    error BadHeaderPolicy();
    error SignatureOutsideValidity();
    error BadRSA();
    error AlreadyConsumed();
    error BadConfiguration();

    event ObservationConsumed(bytes32 indexed receipt, bytes32 indexed requestKey, bytes32 indexed emailNullifier);

    constructor(DKIMVerifier verifier_, address consumer_, bytes32 keyHash_, bytes32 profile_,
        LayaRequest.Request memory frozen)
    {
        if (address(verifier_) == address(0) || consumer_ == address(0) || keyHash_ != FROZEN_GOOGLE_KEY_HASH
            || profile_ != PROFILE_SHA256 || FROZEN_RULES_HASH == 0 || FROZEN_SOURCE_POLICY_HASH == 0
            || FROZEN_MODEL_PINS_HASH == 0 || FROZEN_PARSER_POLICY_HASH == 0) revert BadConfiguration();
        LayaRequest.validate(frozen, block.timestamp, block.chainid, consumer_);
        if (frozen.rulesHash != FROZEN_RULES_HASH || frozen.sourcePolicyHash != FROZEN_SOURCE_POLICY_HASH
            || frozen.sourceIndex != 0 || frozen.model.weights != WEIGHTS_SHA256
            || keccak256(abi.encode(frozen.model)) != FROZEN_MODEL_PINS_HASH
            || frozen.parserPolicyHash != FROZEN_PARSER_POLICY_HASH
            || frozen.canonicalBodySha256 != CANONICAL_BODY_SHA256 || frozen.bodyOffset != BODY_OFFSET
            || frozen.bodyLength != ENCODED_WINDOW_BYTES) revert BadConfiguration();
        verifier = verifier_;
        authorizedConsumer = consumer_;
        googleKeyHash = keyHash_;
        bytes32 key = LayaRequest.key(frozen);
        frozenRequestKey = key;
        frozenRequestKeys[key] = Admission({allowed: true, sourceGroup: 0, queryVariant: 0});
    }

    function requestDomain() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_VERSION, block.chainid, address(this), authorizedConsumer, MARKET_ID));
    }

    /// @notice Explicit source boundary: one BBC observation is not the original rule's
    /// official first announcement or a reporting consensus, regardless of model scores.
    function originalRuleSourceAdmissionEstablished() external pure returns (bool) { return false; }

    function verifyEvidence(bytes32 domain, LayaRequest.Request calldata request, EmailProof calldata proof,
        bytes calldata exactInput, uint32[] calldata tokenIds)
        public view returns (bytes32 requestKey, uint8 sourceGroup)
    {
        if (domain != requestDomain()) revert WrongDomain();
        LayaRequest.validate(request, block.timestamp, block.chainid, authorizedConsumer);
        requestKey = LayaRequest.key(request);
        if (requestKey != frozenRequestKey) revert WrongFrozenRequest();
        validateHeaderPolicy(proof);
        // Authenticate THIS exact header internally; a separately supplied subject-only
        // proof cannot be substituted for the header committing to the complete MIME body.
        EmailProof memory headerOnly = proof;
        headerOnly.canonicalBody = "";
        headerOnly.bodyExcerpt = "";
        headerOnly.bodyOffset = 0;
        headerOnly.bodyLength = 0;
        if (!verifier.verify(headerOnly)) revert BadRSA();
        LayaRequest.validateEvidence(request, proof);
        if (sha256(proof.header) != CANONICAL_HEADER_SHA256
            || proof.canonicalBody.length != CANONICAL_BODY_BYTES) revert WrongFrozenCandidate();
        // Equality to frozen commitments, not onchain extraction/serialization/tokenization.
        LayaRequest.validateInput(request, exactInput, tokenIds);
        return (requestKey, 0);
    }

    /// @dev Receipt consumption is only a replay-protected observation. It establishes
    /// no original-rule source admission. Later consumer failures roll back these writes.
    function consumeEvidence(bytes32 domain, LayaRequest.Request calldata request, EmailProof calldata proof,
        bytes calldata exactInput, uint32[] calldata tokenIds)
        external returns (bytes32 receipt, uint8 sourceGroup)
    {
        if (msg.sender != authorizedConsumer) revert NotConsumer();
        bytes32 key;
        (key, sourceGroup) = verifyEvidence(domain, request, proof, exactInput, tokenIds);
        if (consumedRequests[key] || consumedEmails[proof.emailNullifier]) revert AlreadyConsumed();
        receipt = keccak256(abi.encode(requestDomain(), key, proof.emailNullifier));
        consumedRequests[key] = true;
        consumedEmails[proof.emailNullifier] = true;
        consumedSourceMask = 1;
        emit ObservationConsumed(receipt, key, proof.emailNullifier);
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
        bytes[7] memory required =
            [bytes("from"), bytes("subject"), bytes("date"), bytes("content-type"), bytes("to"), bytes("message-id"), bytes("mime-version")];
        for (uint256 i; i < required.length; ++i) {
            (, bool unique) = HeaderParser.fieldUnique(header, required[i]);
            if (!unique || !listed(names, required[i])) revert BadHeaderPolicy();
        }
        (bytes memory t, bool hasT) = BodyParser.tag(sig, "t");
        (bytes memory x, bool hasX) = BodyParser.tag(sig, "x");
        (uint256 signedAt, bool tOk) = decimal(t);
        (uint256 expiresAt, bool xOk) = decimal(x);
        if (!hasT || !hasX || !tOk || !xOk || expiresAt <= signedAt
            || signedAt != GOOGLE_SIGNED_AT || expiresAt != GOOGLE_EXPIRES_AT) revert BadHeaderPolicy();
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
