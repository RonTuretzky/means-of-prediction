// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {HeaderParser} from "./HeaderParser.sol";

/// @notice Version 1 body-source profile: single-part UTF-8/ASCII text/plain or text/html.
/// Authenticates the COMPLETE canonical body against DKIM bh=, refuses l= truncation,
/// and decodes a bounded byte window. HTML is retained as source, never rendered/stripped.
/// Unsigned Content-Transfer-Encoding is ignored: this profile explicitly uses quoted-
/// printable in that case (the NYT format). Signed 7bit/8bit uses identity decoding.
/// This is an existential substring witness, NOT a whole-body or semantic verdict.
library BodyParser {
    uint256 internal constant MAX_BODY = 196608;
    uint256 internal constant MAX_WINDOW = 4096;

    function tag(bytes memory value, bytes memory name) internal pure returns (bytes memory result, bool found) {
        uint256 start;
        for (uint256 end; end <= value.length; ++end) {
            if (end < value.length && value[end] != ";") continue;
            uint256 a = start;
            uint256 b = end;
            while (a < b && (value[a] == " " || value[a] == "\t")) ++a;
            while (b > a && (value[b - 1] == " " || value[b - 1] == "\t")) --b;
            uint256 eq = a;
            while (eq < b && value[eq] != "=") ++eq;
            uint256 keyEnd = eq;
            while (keyEnd > a && (value[keyEnd - 1] == " " || value[keyEnd - 1] == "\t")) --keyEnd;
            if (eq < b && keyEnd - a == name.length) {
                bool equal = true;
                for (uint256 j; j < name.length; ++j) if (value[a + j] != name[j]) equal = false;
                if (equal) {
                    if (found) return ("", false);
                    found = true;
                    a = eq + 1;
                    while (a < b && (value[a] == " " || value[a] == "\t")) ++a;
                    result = new bytes(b - a);
                    for (uint256 j; j < result.length; ++j) result[j] = value[a + j];
                }
            }
            start = end + 1;
        }
    }

    function same(bytes memory value, string memory expected) internal pure returns (bool) {
        return keccak256(value) == keccak256(bytes(expected));
    }

    /// @dev bh= is exactly one canonical SHA-256 base64 value; whitespace is allowed by DKIM.
    function bodyHash(bytes memory value) internal pure returns (bytes32 hash, bool ok) {
        bytes memory b = new bytes(44);
        uint256 n;
        for (uint256 i; i < value.length; ++i) {
            if (value[i] == " " || value[i] == "\t") continue;
            if (n == 44) return (0, false);
            b[n++] = value[i];
        }
        if (n != 44 || b[43] != "=") return (0, false);
        uint256 acc;
        for (uint256 i; i < 43; ++i) {
            uint256 c = uint8(b[i]);
            uint256 v;
            if (c >= 65 && c <= 90) v = c - 65;
            else if (c >= 97 && c <= 122) v = c - 71;
            else if (c >= 48 && c <= 57) v = c + 4;
            else if (c == 43) v = 62;
            else if (c == 47) v = 63;
            else return (0, false);
            if (i == 42) {
                if (v & 3 != 0) return (0, false);
                acc = (acc << 4) | (v >> 2);
            } else acc = (acc << 6) | v;
        }
        return (bytes32(acc), true);
    }

    function mimeProfile(bytes memory header) internal pure returns (uint256 encoding, bool ok) {
        (bytes memory ct, bool present) = HeaderParser.fieldUnique(header, "content-type");
        if (!present) return (0, false);
        // Case-insensitive media type; only utf-8/us-ascii charset is supported.
        for (uint256 i; i < ct.length; ++i) if (ct[i] >= "A" && ct[i] <= "Z") ct[i] = bytes1(uint8(ct[i]) + 32);
        uint256 end;
        while (end < ct.length && ct[end] != ";" && ct[end] != " ") ++end;
        bytes memory media = new bytes(end);
        for (uint256 i; i < end; ++i) media[i] = ct[i];
        if (!same(media, "text/plain") && !same(media, "text/html")) return (0, false);
        (bytes memory charset, bool hasCharset) = tag(ct, "charset");
        if (!hasCharset && hasTagKey(ct, "charset")) return (0, false);
        if (hasCharset && !same(charset, "utf-8") && !same(charset, "\"utf-8\"")
            && !same(charset, "us-ascii") && !same(charset, "\"us-ascii\"")) return (0, false);
        (bytes memory cte, bool signedEncoding) = HeaderParser.fieldUnique(header, "content-transfer-encoding");
        if (!signedEncoding) {
            // Distinguish an absent field from ambiguous duplicate signed fields.
            (, bool exists) = HeaderParser.field(header, "content-transfer-encoding");
            return (1, !exists);
        }
        for (uint256 i; i < cte.length; ++i) if (cte[i] >= "A" && cte[i] <= "Z") cte[i] = bytes1(uint8(cte[i]) + 32);
        if (same(cte, "quoted-printable")) return (1, true);
        if (same(cte, "7bit") || same(cte, "8bit")) return (0, true);
        return (0, false);
    }

    function decode(bytes calldata body, uint256 start, uint256 length, uint256 encoding)
        internal pure returns (bytes memory out, bool ok)
    {
        if (length == 0 || length > MAX_WINDOW || start > body.length || length > body.length - start) return ("", false);
        uint256 end = start + length;
        // Never start in a quoted-printable escape or a soft line break.
        if (encoding == 1 && ((start > 0 && body[start - 1] == "=")
            || (start > 1 && body[start - 2] == "="))) return ("", false);
        out = new bytes(length);
        uint256 n;
        for (uint256 i = start; i < end; ++i) {
            bytes1 c = body[i];
            if (encoding == 1 && c == "=") {
                if (i + 2 >= end) return ("", false);
                if (body[i + 1] == "\r" && body[i + 2] == "\n") { i += 2; continue; }
                (uint8 high, bool a) = hexNibble(body[i + 1]);
                (uint8 low, bool b) = hexNibble(body[i + 2]);
                if (!a || !b) return ("", false);
                c = bytes1(high * 16 + low);
                i += 2;
            }
            out[n++] = c;
        }
        assembly ("memory-safe") { mstore(out, n) }
        return (out, true);
    }

    function hexNibble(bytes1 c) private pure returns (uint8, bool) {
        if (c >= "0" && c <= "9") return (uint8(c) - 48, true);
        if (c >= "A" && c <= "F") return (uint8(c) - 55, true);
        if (c >= "a" && c <= "f") return (uint8(c) - 87, true);
        return (0, false);
    }

    function verify(bytes memory header, bytes calldata body, uint256 start, uint256 length, string calldata excerpt)
        internal pure returns (bool)
    {
        if (body.length == 0 || body.length > MAX_BODY) return false;
        (bytes memory sig, bool hasSig) = HeaderParser.fieldUnique(header, "dkim-signature");
        if (!hasSig) return false;
        (bytes memory canon, bool hasCanon) = tag(sig, "c");
        if (!hasCanon || (!same(canon, "relaxed/relaxed") && !same(canon, "relaxed/simple"))) return false;
        // A duplicate l= must not turn into an apparently absent l=. Look for its key
        // independently by prefixing every parsed segment, including empty values.
        if (hasTagKey(sig, "l")) return false;
        (bytes memory bh, bool hasBh) = tag(sig, "bh");
        if (!hasBh) return false;
        (bytes32 expected, bool hashOk) = bodyHash(bh);
        if (!hashOk || sha256(body) != expected) return false;
        (uint256 encoding, bool mimeOk) = mimeProfile(header);
        if (!mimeOk) return false;
        (bytes memory decoded, bool decodedOk) = decode(body, start, length, encoding);
        return decodedOk && keccak256(decoded) == keccak256(bytes(excerpt));
    }

    function hasTagKey(bytes memory value, bytes memory name) internal pure returns (bool) {
        // Appending a sentinel disambiguates duplicates: tag() fails if any matching
        // key already existed, even an empty value or a duplicate in the original.
        (, bool unique) = tag(bytes.concat(value, ";", name, "=sentinel"), name);
        return !unique;
    }

    /// @dev Body windows are existential substring witnesses. Anchors would let a
    /// cropped window masquerade as an entire body. Escaped literals/classes are fine.
    function substringPattern(string memory pattern) internal pure returns (bool) {
        bytes memory p = bytes(pattern);
        bool escaped;
        bool inClass;
        for (uint256 i; i < p.length; ++i) {
            if (escaped) { escaped = false; continue; }
            if (p[i] == "\\") { escaped = true; continue; }
            if (p[i] == "[") inClass = true;
            else if (p[i] == "]") inClass = false;
            else if (!inClass && (p[i] == "^" || p[i] == "$")) return false;
        }
        return true;
    }
}
