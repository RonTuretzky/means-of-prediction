// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "../dkim/IDKIMVerifier.sol";
import {DKIMVerifier} from "../dkim/DKIMVerifier.sol";
import {HeaderParser} from "../lib/HeaderParser.sol";
import {BodyParser} from "../lib/BodyParser.sol";
import {LayaRequest} from "./LayaRequest.sol";

/// @notice Authenticating the exact reviewed BBC/CNN/ABC/RFI packet, not any-N consensus.
/// @dev Case-specific credible-reporting fallback from unchanged rules. The frozen
/// qualitative source review is trusted configuration, not an onchain truth detector.
/// Google RSA authenticates relay bytes, not publisher signatures. This gate performs
/// no model inference or result authentication; its fixed consumer must verify actual
/// certificates and require A-only support for every named report before consuming.
/// All complete proofs are reverified at one block clock and consumed atomically.
contract PeaceFourReportEvidenceGate {
    uint256 public constant MARKET_ID = 5371292;
    bytes32 public constant DOMAIN_VERSION = keccak256("PEACE_EXACT_FOUR_REPORT_EVIDENCE_V1");
    bytes32 public constant SOURCE_POLICY_FILE_SHA256 =
        0x464871658b2543c7cfd2fac61ecaf84ec32e437a06265dd12e648ea2750ea3a2;
    bytes32 public constant ORIGINAL_RULES_SHA256 =
        0xf1ba951f9767de4eae4f2562b22bc4ad43db741fe3d30cecc5112a93eafece6d;
    bytes32 public constant PROFILE_SHA256 =
        0x8570a1c2237024cc17a383ed73de6578d8215b800f3a1ef2a30eeeab88b28835;
    bytes32 public constant WEIGHTS_SHA256 =
        0x5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169;
    // Exact new four-report freeze; old BBC-only requests/certificates are separate.
    bytes32 public constant FROZEN_RULES_HASH =
        0x819cc5bb6cc35bd96d4a98709c39f0ef2a781c5932663267f16d5a2a05b0c67d;
    bytes32 public constant FROZEN_SOURCE_POLICY_HASH =
        0x87396794242ef210309c9653ad74b9fcff1a0572152954fdcf7245c0f79809fb;
    bytes32 public constant FROZEN_MODEL_PINS_HASH =
        0x304e1a2a8885f59b01f953544d6615e19eba6bf6622e64b2ddf8275330da9be9;
    bytes32 public constant FROZEN_PARSER_POLICY_HASH =
        0x57b85f833d0d077b60932689f2a08aa3785b84f46c7b475492d820dc658486e8;
    bytes32 public constant FROZEN_GOOGLE_KEY_HASH =
        0xf970943fe89bae0dde33dcef7dba4398d6cc1ac5c04a3a7e4160b4d4ea82b0fa;
    string public constant GOOGLE_DOMAIN = "google.com";
    string public constant GOOGLE_SENDER = "googlealerts-noreply@google.com";
    string public constant GOOGLE_SELECTOR = "20251104";

    struct Admission { bool allowed; uint8 sourceGroup; uint8 queryVariant; }
    struct CandidatePin {
        bytes32 headerSHA256; bytes32 bodySHA256; uint256 bodyBytes;
        uint32 offset; uint32 encodedBytes; bytes32 decodedSHA256;
        uint256 signedAt; uint256 expiresAt;
    }
    DKIMVerifier public immutable verifier;
    address public immutable authorizedConsumer;
    bytes32 public immutable googleKeyHash;
    bytes32[4] public orderedRequestKeys;
    mapping(bytes32 => Admission) public frozenRequestKeys;
    mapping(bytes32 => bool) public consumedRequests;
    mapping(bytes32 => bool) public consumedEmails;
    uint8 public consumedSourceMask;

    error NotConsumer(); error WrongDomain(); error WrongFrozenRequest(); error WrongFrozenCandidate();
    error WrongGoogleIdentity(); error BadHeaderPolicy(); error SignatureOutsideValidity(); error BadRSA();
    error AlreadyConsumed(); error BadConfiguration(); error BadBundle();
    event ExactPacketConsumed(bytes32 indexed bundleReceipt, bytes32 indexed policyHash);

    constructor(DKIMVerifier verifier_, address consumer_, bytes32 keyHash_, bytes32 profile_,
        LayaRequest.Request[] memory frozen)
    {
        if (address(verifier_) == address(0) || consumer_ == address(0) || keyHash_ != FROZEN_GOOGLE_KEY_HASH
            || profile_ != PROFILE_SHA256 || frozen.length != 4 || FROZEN_RULES_HASH == 0
            || FROZEN_SOURCE_POLICY_HASH == 0 || FROZEN_MODEL_PINS_HASH == 0
            || FROZEN_PARSER_POLICY_HASH == 0) revert BadConfiguration();
        verifier = verifier_; authorizedConsumer = consumer_; googleKeyHash = keyHash_;
        for (uint256 i; i < 4; ++i) {
            CandidatePin memory pin = candidatePin(uint8(i));
            LayaRequest.Request memory r = frozen[i];
            LayaRequest.validate(r, block.timestamp, block.chainid, consumer_);
            if (pin.headerSHA256 == 0 || r.rulesHash != FROZEN_RULES_HASH
                || r.sourcePolicyHash != FROZEN_SOURCE_POLICY_HASH || r.sourceIndex != i
                || r.model.weights != WEIGHTS_SHA256 || keccak256(abi.encode(r.model)) != FROZEN_MODEL_PINS_HASH
                || r.parserPolicyHash != FROZEN_PARSER_POLICY_HASH || r.canonicalBodySha256 != pin.bodySHA256
                || r.bodyOffset != pin.offset || r.bodyLength != pin.encodedBytes) revert BadConfiguration();
            for (uint256 j; j < i; ++j) if (r.emailNullifier == frozen[j].emailNullifier) revert BadConfiguration();
            bytes32 key = LayaRequest.key(r);
            if (frozenRequestKeys[key].allowed) revert BadConfiguration();
            orderedRequestKeys[i] = key;
            frozenRequestKeys[key] = Admission({allowed: true, sourceGroup: uint8(i), queryVariant: uint8(i)});
        }
    }

    function requestDomain() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_VERSION, block.chainid, address(this), authorizedConsumer,
            MARKET_ID, FROZEN_SOURCE_POLICY_HASH));
    }

    function verifyEvidence(bytes32 domain, LayaRequest.Request calldata request, EmailProof calldata proof,
        bytes calldata exactInput, uint32[] calldata tokenIds)
        public view returns (bytes32 requestKey, uint8 sourceGroup)
    {
        if (domain != requestDomain()) revert WrongDomain();
        LayaRequest.validate(request, block.timestamp, block.chainid, authorizedConsumer);
        requestKey = LayaRequest.key(request);
        Admission memory admitted = frozenRequestKeys[requestKey];
        if (!admitted.allowed) revert WrongFrozenRequest();
        sourceGroup = admitted.sourceGroup;
        validateHeaderPolicy(proof, sourceGroup);
        // P0 is derived from this P, never independently supplied by the submitter.
        EmailProof memory headerOnly = proof;
        headerOnly.canonicalBody = ""; headerOnly.bodyExcerpt = "";
        headerOnly.bodyOffset = 0; headerOnly.bodyLength = 0;
        if (!verifier.verify(headerOnly)) revert BadRSA();
        LayaRequest.validateEvidence(request, proof);
        CandidatePin memory pin = candidatePin(sourceGroup);
        if (sha256(proof.header) != pin.headerSHA256 || proof.canonicalBody.length != pin.bodyBytes
            || sha256(bytes(proof.bodyExcerpt)) != pin.decodedSHA256) revert WrongFrozenCandidate();
        LayaRequest.validateInput(request, exactInput, tokenIds); // Commitment equality, not tokenizer semantics.
    }

    /// @notice Exact ordered packet, not a publisher count or a generic threshold.
    function verifyBundle(bytes32 domain, LayaRequest.Request[] calldata requests, EmailProof[] calldata proofs,
        bytes[] calldata exactInputs, uint32[][] calldata tokenIds) public view returns (bytes32 bundleReceipt)
    {
        if (requests.length != 4 || proofs.length != 4 || exactInputs.length != 4 || tokenIds.length != 4) revert BadBundle();
        bytes32[4] memory keys;
        for (uint256 i; i < 4; ++i) {
            (bytes32 key, uint8 group) = verifyEvidence(domain, requests[i], proofs[i], exactInputs[i], tokenIds[i]);
            if (group != i || key != orderedRequestKeys[i]) revert BadBundle();
            keys[i] = key;
        }
        bundleReceipt = keccak256(abi.encode(requestDomain(), FROZEN_SOURCE_POLICY_HASH, keys));
    }

    /// @dev No per-report consume entry point exists. All four full proofs are checked
    /// with block.timestamp before any write; every failure rolls back the entire packet.
    function consumeBundle(bytes32 domain, LayaRequest.Request[] calldata requests, EmailProof[] calldata proofs,
        bytes[] calldata exactInputs, uint32[][] calldata tokenIds) external returns (bytes32 bundleReceipt)
    {
        if (msg.sender != authorizedConsumer) revert NotConsumer();
        bundleReceipt = verifyBundle(domain, requests, proofs, exactInputs, tokenIds);
        if (consumedSourceMask != 0) revert AlreadyConsumed();
        for (uint256 i; i < 4; ++i) {
            bytes32 key = orderedRequestKeys[i];
            if (consumedRequests[key] || consumedEmails[proofs[i].emailNullifier]) revert AlreadyConsumed();
        }
        for (uint256 i; i < 4; ++i) {
            consumedRequests[orderedRequestKeys[i]] = true; consumedEmails[proofs[i].emailNullifier] = true;
        }
        consumedSourceMask = 15;
        emit ExactPacketConsumed(bundleReceipt, FROZEN_SOURCE_POLICY_HASH);
    }

    function candidatePin(uint8 source) public pure returns (CandidatePin memory) {
        if (source == 0) return CandidatePin(0x21d51e434d69f0e402759041b46d92fc792cf4953425243169ee8bae3645fa43,
            0xef09cd6700414ff97c243c6c7b564b457c19db3efdc26a0e84033bd033e939b4, 20461, 8078, 1265,
            0x149ade018f10f56547ccf07d73f795470b1d824d06408ef573db0ceb83b14d41, 1792292308, 1792897108);
        if (source == 1) return CandidatePin(0x4ede8aa00b73184e5f2e28707c30dd0d1d4165d3baaa648bc8cce07e60967a5d,
            0xa6d1580773e4766a47e28577ae00b5aa14386450cf60b6f7aa7e11cbc900b635, 44557, 11532, 3339,
            0x9686d3407b1fc1063f44b24ac907cb77c6b22fd57c968b3442a252409b0823e8, 1791994489, 1792599289);
        if (source == 2) return CandidatePin(0xb05c524521d9f8d2e17d4c4d105bc8056ca3772e9264683e8e872705ec8e8d01,
            0x55a8b2ae9f39b7d368365120ca120a7d9a2cdbab553b096c587305afcaaa375e, 28521, 9313, 1389,
            0x2c7fb893a70d09feba21f6ed03c086199cd3f6b1cc6b41b3693f8a3eda2ea6fb, 1792033004, 1792637804);
        if (source == 3) return CandidatePin(0xa4f71e941072fe5acfeace5006f0eda7a2cdd7d92e3cae26aadb6b15e7d5e5ce,
            0xd75a0fa361bc1d54083d04eb4df7a2f63709bb3cfe89d2c4f2ae8dad81d11c30, 39678, 15201, 1451,
            0xb9797f4ebccab0b8aaf959fe3aaec5c3057406b85373194b82d0354ec3878626, 1792001343, 1792606143);
        revert BadConfiguration();
    }

    function validateHeaderPolicy(EmailProof calldata proof, uint8 source) internal view {
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
            || signedAt != candidatePin(source).signedAt || expiresAt != candidatePin(source).expiresAt) revert BadHeaderPolicy();
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
