// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof, IDKIMVerifier} from "./IDKIMVerifier.sol";
import {DKIMRegistry} from "./DKIMRegistry.sol";
import {RSAVerify} from "./RSAVerify.sol";
import {BodyParser} from "../lib/BodyParser.sol";
import {HeaderParser} from "../lib/HeaderParser.sol";

/// @notice RSA-SHA256 DKIM verification with exact signed header fields and optional
/// full-body bh= authentication plus a bounded, decoded body-source window.
/// Body profile v1 retains HTML markup and permits only substring market rules.
contract DKIMVerifier is IDKIMVerifier {
    DKIMRegistry public immutable registry;

    constructor(DKIMRegistry _registry) {
        registry = _registry;
    }

    function bodyParsingVersion() external pure returns (uint256) { return 1; }

    function verify(EmailProof calldata p) external view returns (bool) {
        if (p.header.length > 32768) return false;
        (bytes memory modulus, bytes memory exponent, bool valid) = registry.keyData(p.domainName, p.publicKeyHash);
        if (!valid) return false;
        // publicKeyHash commits to the exact modulus, so the registry can't be tricked
        // into pairing a hash with a different key.
        if (keccak256(modulus) != p.publicKeyHash) return false;

        // (2) real RSA-SHA256 signature check over the canonicalized header
        if (!RSAVerify.pkcs1Sha256(sha256(p.header), p.signature, exponent, modulus)) return false;

        // (3) bind the extracted fields to the authenticated header.
        //
        // Every field of an EmailProof must be derivable from the RSA-verified bytes.
        // Anything the signature does not cover is attacker-chosen, so it is either
        // bound here or refused outright.
        if (p.emailNullifier != keccak256(p.signature)) return false;

        bytes memory header = p.header;

        // Subject must equal the signed `subject:` field EXACTLY. A substring test would
        // let a correction ("Correction: our alert 'Fed cuts rates' was sent in error")
        // settle a market as the very alert it retracts.
        (bytes memory signedSubject, bool okSubject) = HeaderParser.fieldUnique(header, "subject");
        if (!okSubject || keccak256(signedSubject) != keccak256(bytes(p.subject))) return false;

        // From: the claimed address must appear inside the signed `from:` field — scoped to
        // that field, never to the whole header block.
        (bytes memory signedFrom, bool okFrom) = HeaderParser.fieldUnique(header, "from");
        if (!okFrom || !mailboxEquals(signedFrom, bytes(p.fromAddress))) return false;

        // Timestamp must equal the signed `date:` header. Unbound, it is a free parameter,
        // and a market's acceptance window degrades from "did this happen during the
        // window" to "did this ever happen, in any email the submitter can find".
        (bytes memory signedDate, bool uniqueDate) = HeaderParser.fieldUnique(header, "date");
        (uint256 signedTs, bool okDate) = HeaderParser.parseRfc2822Date(signedDate);
        if (!uniqueDate) return false;
        if (!okDate || signedTs != p.timestamp) return false;

        // Bind signing identity too: a shared RSA key must not relabel another domain's mail.
        (bytes memory sig, bool hasSig) = HeaderParser.fieldUnique(header, "dkim-signature");
        (bytes memory domain, bool hasDomain) = BodyParser.tag(sig, "d");
        (bytes memory algo, bool hasAlgo) = BodyParser.tag(sig, "a");
        if (!hasSig || !hasDomain || !hasAlgo || !BodyParser.same(algo, "rsa-sha256")
            || keccak256(domain) != keccak256(bytes(p.domainName))) return false;
        if (p.canonicalBody.length == 0) {
            if (bytes(p.bodyExcerpt).length != 0 || p.bodyOffset != 0 || p.bodyLength != 0) return false;
        } else if (!BodyParser.verify(header, p.canonicalBody, p.bodyOffset, p.bodyLength, p.bodyExcerpt)) return false;

        return true;
    }

    /// @dev One exact mailbox, optionally inside one angle-address. Display names
    /// cannot stand in for the sender, and multi-address/ambiguous forms fail closed.
    function mailboxEquals(bytes memory from, bytes memory claimed) internal pure returns (bool) {
        if (claimed.length == 0) return false;
        uint256 start;
        uint256 end = from.length;
        bool angle;
        bool closed;
        for (uint256 i; i < from.length; ++i) {
            if (from[i] == "<") { if (angle) return false; angle = true; start = i + 1; }
            if (from[i] == ">") { if (!angle || closed) return false; closed = true; end = i; }
        }
        if (angle != closed) return false;
        if (closed) for (uint256 i = end + 1; i < from.length; ++i) if (from[i] != " " && from[i] != "\t") return false;
        if (end < start || end - start != claimed.length) return false;
        uint256 at;
        for (uint256 i; i < claimed.length; ++i) {
            if (from[start + i] != claimed[i] || claimed[i] <= 0x20 || claimed[i] == "," || claimed[i] == '"') return false;
            if (claimed[i] == "@") ++at;
        }
        return at == 1;
    }
}
