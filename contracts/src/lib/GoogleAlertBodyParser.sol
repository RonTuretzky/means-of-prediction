// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {HeaderParser} from "./HeaderParser.sol";
import {BodyParser} from "./BodyParser.sol";

/// @notice Fixed MIME source profile v2 for Google Alerts multipart/alternative mail.
/// @dev This pure component authenticates a full canonical body against bh= in a
/// separately RSA-authenticated relaxed header block. It DOES NOT verify RSA, establish
/// Google provenance, extract articles, tokenize model input, or produce a verdict.
/// Exactly plain/base64 then HTML/quoted-printable is supported, without preamble,
/// epilogue, nesting, folded part headers, or additional MIME parameters/headers.
/// Offsets refer to encoded bytes in the COMPLETE canonical body, not decoded HTML.
library GoogleAlertBodyParser {
    uint256 internal constant VERSION = 2;
    uint256 internal constant MAX_BODY = 196608;
    uint256 internal constant MAX_WINDOW = 4096;

    function verify(bytes memory header, bytes calldata body, uint256 start, uint256 length, string calldata excerpt)
        internal
        pure
        returns (bool)
    {
        if (body.length == 0 || body.length > MAX_BODY || !validHeader(header)) return false;
        (bytes memory sig, bool ok) = HeaderParser.fieldUnique(header, "dkim-signature");
        if (!ok || BodyParser.hasTagKey(sig, "l")) return false;
        (bytes memory canon, bool hasCanon) = BodyParser.tag(sig, "c");
        if (!hasCanon || (!BodyParser.same(canon, "relaxed/relaxed") && !BodyParser.same(canon, "relaxed/simple"))) {
            return false;
        }
        (bytes memory bh, bool hasBh) = BodyParser.tag(sig, "bh");
        (bytes32 expected, bool hashOk) = BodyParser.bodyHash(bh);
        if (!hasBh || !hashOk || sha256(body) != expected || !signedContentType(sig)) return false;
        (bytes memory ct, bool hasType) = HeaderParser.fieldUnique(header, "content-type");
        if (!hasType) return false;
        (bytes memory boundary, bool mimeOk) = contentType(ct, 0);
        if (!mimeOk) return false;
        (uint256 payloadStart, uint256 payloadEnd, bool partsOk) = htmlPayload(body, boundary);
        if (
            !partsOk || length == 0 || length > MAX_WINDOW || start < payloadStart || start > payloadEnd
                || length > payloadEnd - start
        ) return false;
        (bytes memory decoded, bool decodedOk) = BodyParser.decode(body, start, length, 1);
        return decodedOk && keccak256(decoded) == keccak256(bytes(excerpt));
    }

    /// @dev Reject noncanonical names, bare line breaks and folded/empty header lines,
    /// so fieldUnique cannot overlook differently capitalized duplicate fields.
    function validHeader(bytes memory header) private pure returns (bool) {
        if (header.length == 0 || header.length > 32768) return false;
        uint256 i;
        while (i < header.length) {
            uint256 nameStart = i;
            while (i < header.length && header[i] != ":") {
                if (!token(header[i]) || (header[i] >= "A" && header[i] <= "Z")) return false;
                ++i;
            }
            if (i == nameStart || i == header.length) return false;
            ++i;
            while (i < header.length && header[i] != "\r" && header[i] != "\n") ++i;
            if (i == header.length) return true;
            if (header[i] != "\r" || i + 1 >= header.length || header[i + 1] != "\n") return false;
            i += 2;
            if (i == header.length) return false;
        }
        return false;
    }

    function signedContentType(bytes memory sig) private pure returns (bool) {
        (bytes memory names, bool ok) = BodyParser.tag(sig, "h");
        if (!ok) return false;
        uint256 count;
        uint256 a;
        for (uint256 i; i <= names.length; ++i) {
            if (i < names.length && names[i] != ":") continue;
            bytes memory name = trimmed(names, a, i);
            if (name.length == 0) return false;
            for (uint256 j; j < name.length; ++j) {
                if (!token(name[j])) return false;
            }
            if (equalCI(name, "content-type")) ++count;
            a = i + 1;
        }
        // Repeated h= names oversign absent additional instances (real Google mail).
        // The canonical signed block must still contain exactly one actual field.
        return count > 0;
    }

    /// @dev kind 0: multipart boundary only; 1: plain charset/format/delsp;
    /// 2: HTML charset only. Keys and media types fold case; boundary bytes never do.
    function contentType(bytes memory ct, uint256 kind) private pure returns (bytes memory boundary, bool ok) {
        uint256 i;
        while (i < ct.length && ct[i] != ";") ++i;
        bytes memory media = trimmed(ct, 0, i);
        if (!equalCI(media, kind == 0 ? "multipart/alternative" : kind == 1 ? "text/plain" : "text/html")) {
            return ("", false);
        }
        uint256 seen;
        while (i < ct.length) {
            ++i;
            i = skipWsp(ct, i);
            uint256 a = i;
            while (i < ct.length && token(ct[i])) ++i;
            bytes memory key = trimmed(ct, a, i);
            i = skipWsp(ct, i);
            if (key.length == 0 || i == ct.length || ct[i] != "=") return ("", false);
            i = skipWsp(ct, i + 1);
            bool quoted = i < ct.length && ct[i] == '"';
            if (quoted) ++i;
            a = i;
            if (quoted) {
                while (i < ct.length && ct[i] != '"') {
                    // Quoted-pairs and control bytes are outside this fixed profile.
                    if (ct[i] == "\\" || ct[i] < 0x20 || ct[i] >= 0x7f) return ("", false);
                    ++i;
                }
                if (i == ct.length) return ("", false);
            } else {
                while (i < ct.length && token(ct[i])) ++i;
            }
            bytes memory value = copy(ct, a, i);
            if (value.length == 0) return ("", false);
            if (quoted) ++i;
            i = skipWsp(ct, i);
            if (i < ct.length && ct[i] != ";") return ("", false);
            uint256 flag;
            if (kind == 0 && equalCI(key, "boundary")) {
                flag = 1;
                if (value.length > 70 || value[value.length - 1] == " ") return ("", false);
                for (uint256 j; j < value.length; ++j) {
                    if (!boundaryChar(value[j])) return ("", false);
                }
                boundary = value;
            } else if (kind != 0 && equalCI(key, "charset")) {
                flag = 1;
                if (!equalCI(value, "utf-8") && !equalCI(value, "us-ascii")) return ("", false);
            } else if (kind == 1 && equalCI(key, "format") && equalCI(value, "flowed")) {
                flag = 2;
            } else if (kind == 1 && equalCI(key, "delsp") && equalCI(value, "yes")) {
                flag = 4;
            } else {
                return ("", false);
            }
            if (seen & flag != 0) return ("", false);
            seen |= flag;
        }
        return (boundary, seen & 1 != 0);
    }

    function htmlPayload(bytes calldata body, bytes memory boundary)
        private
        pure
        returns (uint256 start, uint256 end, bool ok)
    {
        bytes memory delimiter = bytes.concat("--", boundary);
        (uint256 e, bool lineOk) = lineEnd(body, 0);
        if (!lineOk || !matches(body, 0, e, delimiter)) return (0, 0, false);
        (uint256 plainStart, bool plainOk) = partHeaders(body, e + 2, 1);
        if (!plainOk) return (0, 0, false);
        (uint256 middle, uint256 afterMiddle, bool middleOk) = nextDelimiter(body, plainStart, delimiter, false);
        if (!middleOk || middle < plainStart + 2 || !base64Payload(body, plainStart, middle - 2)) return (0, 0, false);
        (start, ok) = partHeaders(body, afterMiddle, 2);
        if (!ok) return (0, 0, false);
        (uint256 closing, uint256 afterClosing, bool closingOk) = nextDelimiter(body, start, delimiter, true);
        if (!closingOk || closing < start + 2 || afterClosing != body.length) return (0, 0, false);
        end = closing - 2; // The delimiter's preceding CRLF is MIME framing, not HTML.
        return (start, end, quotedPrintable(body, start, end));
    }

    function partHeaders(bytes calldata body, uint256 pos, uint256 kind) private pure returns (uint256, bool) {
        uint256 first = pos;
        uint256 seen;
        while (pos < body.length) {
            (uint256 end, bool ok) = lineEnd(body, pos);
            if (!ok || end - first > 2048) return (0, false);
            if (end == pos) return (end + 2, seen == 3);
            uint256 colon = pos;
            while (colon < end && body[colon] != ":") {
                if (!token(body[colon])) return (0, false);
                ++colon;
            }
            if (colon == pos || colon == end) return (0, false);
            bytes memory name = body[pos:colon];
            bytes memory value = trimmed(body[colon + 1:end], 0, end - colon - 1);
            uint256 flag;
            if (equalCI(name, "content-type")) {
                (, bool ctOk) = contentType(value, kind);
                if (!ctOk) return (0, false);
                flag = 1;
            } else if (equalCI(name, "content-transfer-encoding")) {
                if (!equalCI(value, kind == 1 ? "base64" : "quoted-printable")) return (0, false);
                flag = 2;
            } else {
                return (0, false);
            }
            if (seen & flag != 0) return (0, false);
            seen |= flag;
            pos = end + 2;
        }
        return (0, false);
    }

    function nextDelimiter(bytes calldata body, uint256 pos, bytes memory delimiter, bool close)
        private
        pure
        returns (uint256, uint256, bool)
    {
        while (pos < body.length) {
            (uint256 end, bool ok) = lineEnd(body, pos);
            if (!ok) return (0, 0, false);
            if (end - pos >= delimiter.length && matches(body, pos, pos + delimiter.length, delimiter)) {
                if (close) {
                    if (end - pos != delimiter.length + 2 || body[end - 2] != "-" || body[end - 1] != "-") {
                        return (0, 0, false);
                    }
                } else if (end - pos != delimiter.length) {
                    return (0, 0, false);
                }
                return (pos, end + 2, true);
            }
            pos = end + 2;
        }
        return (0, 0, false);
    }

    function base64Payload(bytes calldata body, uint256 start, uint256 end) private pure returns (bool) {
        uint256 n;
        uint256 padding;
        uint256 lastValue;
        for (uint256 i = start; i < end; ++i) {
            bytes1 c = body[i];
            if (c == "\r" && i + 1 < end && body[i + 1] == "\n") {
                ++i;
                continue;
            }
            if (c == "=") {
                if (++padding > 2) return false;
            } else {
                if (padding != 0) return false;
                uint8 v = uint8(c);
                if (c >= "A" && c <= "Z") lastValue = v - 65;
                else if (c >= "a" && c <= "z") lastValue = v - 71;
                else if (c >= "0" && c <= "9") lastValue = v + 4;
                else if (c == "+") lastValue = 62;
                else if (c == "/") lastValue = 63;
                else return false;
            }
            ++n;
        }
        return n > 0 && n % 4 == 0 && (padding == 0 || (padding == 1 ? lastValue & 3 == 0 : lastValue & 15 == 0));
    }

    function quotedPrintable(bytes calldata body, uint256 start, uint256 end) private pure returns (bool) {
        for (uint256 i = start; i < end; ++i) {
            bytes1 c = body[i];
            if (c == "=") {
                if (i + 2 >= end) return false;
                if (body[i + 1] == "\r" && body[i + 2] == "\n") {
                    i += 2;
                    continue;
                }
                if (!isHex(body[i + 1]) || !isHex(body[i + 2])) return false;
                i += 2;
            } else if (c == "\r") {
                if (i + 1 >= end || body[++i] != "\n") return false;
            } else if ((c < 0x20 && c != "\t") || c > 0x7e) {
                return false;
            }
        }
        return true;
    }

    function lineEnd(bytes calldata body, uint256 pos) private pure returns (uint256, bool) {
        for (uint256 i = pos; i < body.length; ++i) {
            if (body[i] == "\n") return (0, false);
            if (body[i] == "\r") return (i, i + 1 < body.length && body[i + 1] == "\n");
        }
        return (0, false);
    }

    function matches(bytes calldata body, uint256 start, uint256 end, bytes memory expected)
        private
        pure
        returns (bool)
    {
        if (end < start || end - start != expected.length || end > body.length) return false;
        for (uint256 i; i < expected.length; ++i) {
            if (body[start + i] != expected[i]) return false;
        }
        return true;
    }

    function equalCI(bytes memory value, string memory expected) private pure returns (bool) {
        bytes memory e = bytes(expected);
        if (value.length != e.length) return false;
        for (uint256 i; i < value.length; ++i) {
            bytes1 c = value[i];
            if (c >= "A" && c <= "Z") c = bytes1(uint8(c) + 32);
            if (c != e[i]) return false;
        }
        return true;
    }

    function skipWsp(bytes memory b, uint256 i) private pure returns (uint256) {
        while (i < b.length && (b[i] == " " || b[i] == "\t")) ++i;
        return i;
    }

    function trimmed(bytes memory b, uint256 a, uint256 z) private pure returns (bytes memory) {
        while (a < z && (b[a] == " " || b[a] == "\t")) ++a;
        while (z > a && (b[z - 1] == " " || b[z - 1] == "\t")) --z;
        return copy(b, a, z);
    }

    function copy(bytes memory b, uint256 a, uint256 z) private pure returns (bytes memory out) {
        out = new bytes(z - a);
        for (uint256 i; i < out.length; ++i) {
            out[i] = b[a + i];
        }
    }

    function token(bytes1 c) private pure returns (bool) {
        if (c <= 0x20 || c >= 0x7f) return false;
        return c != "(" && c != ")" && c != "<" && c != ">" && c != "@" && c != "," && c != ";" && c != ":" && c != "\\"
            && c != '"' && c != "/" && c != "[" && c != "]" && c != "?" && c != "=";
    }

    function boundaryChar(bytes1 c) private pure returns (bool) {
        return (c >= "A" && c <= "Z") || (c >= "a" && c <= "z") || (c >= "0" && c <= "9") || c == "'" || c == "("
            || c == ")" || c == "+" || c == "_" || c == "," || c == "-" || c == "." || c == "/" || c == ":" || c == "="
            || c == "?" || c == " ";
    }

    function isHex(bytes1 c) private pure returns (bool) {
        return (c >= "0" && c <= "9") || (c >= "a" && c <= "f") || (c >= "A" && c <= "F");
    }
}
