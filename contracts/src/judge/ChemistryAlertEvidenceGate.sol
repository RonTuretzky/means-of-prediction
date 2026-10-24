// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {HeaderParser} from "../lib/HeaderParser.sol";
import {BodyParser} from "../lib/BodyParser.sol";
import {LayaRequest} from "./LayaRequest.sol";

/// @notice Frozen Chemistry evidence authentication, not an inference or verdict oracle.
/// @dev Trusted research configuration admits exactly three preselected requests: early
/// Reuters, AP, later Reuters. Source identity/extraction/input semantics are frozen by
/// that configuration, not dynamically inferred from arbitrary caller excerpts. Google
/// DKIM authenticates alert bytes, not publisher authorship or truth. The consumer must
/// authenticate model execution separately and consume only admitted settlement support.
/// No production market, Qwen ABI, parser cap, or original source rule is modified.
contract ChemistryAlertEvidenceGate {
    uint256 public constant MARKET_ID = 5371179;
    bytes32 public constant DOMAIN_VERSION = keccak256("CHEMISTRY_ALERT_EVIDENCE_GATE_V1");
    bytes32 public constant ORIGINAL_RULES_SHA256 = 0xef16b628bacdaa608c9eb199e068d077f296f02849ee0e52173f57191eb9a4ad;
    bytes32 public constant PROFILE_SHA256 = 0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 public constant WEIGHTS_SHA256 = 0x5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169;
    bytes32 public constant FROZEN_RULES_HASH = 0x524db508ccd38b526e22ab660df7f225e5ab2ab37ec7580226ccfff382656478;
    bytes32 public constant FROZEN_SOURCE_POLICY_HASH =
        0x078a7261fd4c3cf83448317cd568a7b7694f84ac67a19ca7e3162034800b69c3;
    bytes32 public constant FROZEN_MODEL_PINS_HASH = 0xf28716c11d301227998ad94c010196df6285d47dd6f56915bf0da59f4edab878;
    bytes32 public constant FROZEN_PARSER_POLICY_HASH =
        0xd31bd5f78c2145769fccf8447693162d86841c9167f624684874244bf2ab45d7;
    bytes32 public constant FROZEN_GOOGLE_KEY_HASH = 0xf970943fe89bae0dde33dcef7dba4398d6cc1ac5c04a3a7e4160b4d4ea82b0fa;
    string public constant GOOGLE_DOMAIN = "google.com";
    string public constant GOOGLE_SENDER = "googlealerts-noreply@google.com";
    string public constant GOOGLE_SELECTOR = "20251104";

    struct Admission {
        bool allowed;
        uint8 sourceGroup; // 0 Reuters; 1 AP. Syndications are not additional origins.
        uint8 queryVariant; // 0 early economics query; 1 AP direct; 2 Reuters direct.
    }

    DKIMVerifier public immutable verifier;
    address public immutable authorizedConsumer;
    bytes32 public immutable googleKeyHash;
    bytes32 public immutable rulesHash;
    bytes32 public immutable sourcePolicyHash;
    bytes32 public immutable modelPinsHash;
    mapping(bytes32 => Admission) public frozenRequestKeys;
    mapping(bytes32 => bool) public consumedRequests;
    mapping(bytes32 => bool) public consumedEmails;
    uint8 public consumedSourceMask;

    error NotConsumer();
    error WrongDomain();
    error WrongFrozenRequest();
    error WrongGoogleIdentity();
    error BadHeaderPolicy();
    error SignatureOutsideValidity();
    error BadRSA();
    error AlreadyConsumed();
    error DuplicateSource();
    error BadConfiguration();

    event EvidenceConsumed(
        bytes32 indexed receipt,
        bytes32 indexed requestKey,
        bytes32 indexed emailNullifier,
        uint8 sourceGroup,
        uint8 queryVariant
    );

    /// @dev The whole request is frozen, not just nonzero model/policy hashes. The
    /// original-rule SHA above and the richer question/A/B/rules bundle hash below have
    /// different meanings. Both are explicit; do not relabel one as the other.
    constructor(
        DKIMVerifier verifier_,
        address consumer_,
        bytes32 keyHash_,
        bytes32 profile_,
        bytes32 rulesHash_,
        bytes32 sourcePolicyHash_,
        LayaRequest.Request[] memory frozen
    ) {
        if (
            address(verifier_) == address(0) || consumer_ == address(0) || keyHash_ != FROZEN_GOOGLE_KEY_HASH
                || profile_ != PROFILE_SHA256 || rulesHash_ != FROZEN_RULES_HASH
                || sourcePolicyHash_ != FROZEN_SOURCE_POLICY_HASH || frozen.length != 3
        ) {
            revert BadConfiguration();
        }
        verifier = verifier_;
        authorizedConsumer = consumer_;
        googleKeyHash = keyHash_;
        rulesHash = rulesHash_;
        sourcePolicyHash = sourcePolicyHash_;
        bytes32 pins = keccak256(abi.encode(frozen[0].model));
        if (pins != FROZEN_MODEL_PINS_HASH) revert BadConfiguration();
        modelPinsHash = pins;
        for (uint256 i; i < frozen.length; ++i) {
            LayaRequest.Request memory r = frozen[i];
            LayaRequest.validate(r, block.timestamp, block.chainid, consumer_);
            uint8 group = i == 1 ? 1 : 0;
            if (
                r.rulesHash != rulesHash_ || r.sourcePolicyHash != sourcePolicyHash_ || r.sourceIndex != group
                    || r.model.weights != WEIGHTS_SHA256 || keccak256(abi.encode(r.model)) != pins
                    || r.parserPolicyHash != FROZEN_PARSER_POLICY_HASH
            ) {
                revert BadConfiguration();
            }
            bytes32 key = LayaRequest.key(r);
            if (frozenRequestKeys[key].allowed) revert BadConfiguration();
            // i is bounded by the fixed three-element constructor admission list.
            frozenRequestKeys[key] = Admission({allowed: true, sourceGroup: group, queryVariant: uint8(i)});
        }
    }

    function requestDomain() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_VERSION, block.chainid, address(this), authorizedConsumer, MARKET_ID));
    }

    /// @notice Verification remains available for abstaining score receipts and consumed
    /// evidence alike. It does not accumulate sources or accept a caller's model scores.
    function verifyEvidence(
        bytes32 domain,
        LayaRequest.Request calldata request,
        EmailProof calldata proof,
        bytes calldata exactInput,
        uint32[] calldata tokenIds
    ) public view returns (bytes32 requestKey, uint8 sourceGroup) {
        if (domain != requestDomain()) revert WrongDomain();
        LayaRequest.validate(request, block.timestamp, block.chainid, authorizedConsumer);
        requestKey = LayaRequest.key(request);
        Admission memory admitted = frozenRequestKeys[requestKey];
        if (!admitted.allowed) revert WrongFrozenRequest();
        validateHeaderPolicy(proof);
        // Derive header-only P0 from THIS full proof. No independently supplied subject
        // proof can substitute a different signed header for the MIME body proof.
        EmailProof memory headerOnly = proof;
        headerOnly.canonicalBody = "";
        headerOnly.bodyExcerpt = "";
        headerOnly.bodyOffset = 0;
        headerOnly.bodyLength = 0;
        if (!verifier.verify(headerOnly)) revert BadRSA();
        LayaRequest.validateEvidence(request, proof);
        // Commitment equality only, not onchain extraction/tokenizer semantic validation.
        LayaRequest.validateInput(request, exactInput, tokenIds);
        return (requestKey, admitted.sourceGroup);
    }

    /// @dev Consumer calls only after its separately authenticated result admits support.
    /// Later certificate/consumer failure in the same transaction rolls these writes back.
    function consumeEvidence(
        bytes32 domain,
        LayaRequest.Request calldata request,
        EmailProof calldata proof,
        bytes calldata exactInput,
        uint32[] calldata tokenIds
    ) external returns (bytes32 receipt, uint8 sourceGroup) {
        if (msg.sender != authorizedConsumer) revert NotConsumer();
        bytes32 key;
        (key, sourceGroup) = verifyEvidence(domain, request, proof, exactInput, tokenIds);
        if (consumedRequests[key] || consumedEmails[proof.emailNullifier]) revert AlreadyConsumed();
        uint8 bit = sourceGroup == 0 ? 1 : 2; // Constructor permits only Reuters/AP.
        if (consumedSourceMask & bit != 0) revert DuplicateSource();
        Admission memory admitted = frozenRequestKeys[key];
        receipt = keccak256(abi.encode(requestDomain(), key, proof.emailNullifier, sourceGroup, admitted.queryVariant));
        consumedRequests[key] = true;
        consumedEmails[proof.emailNullifier] = true;
        consumedSourceMask |= bit;
        emit EvidenceConsumed(receipt, key, proof.emailNullifier, sourceGroup, admitted.queryVariant);
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
