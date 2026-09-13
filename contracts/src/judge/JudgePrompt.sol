// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title JudgePrompt
/// @notice The single source of truth for what the on-chain judge is asked. Both sides use
/// it: the market, to compute the verdict key for a DKIM-signed email in an ordinary
/// transaction, and `LLMJudge.fulfil` (inside the Gas Killer simulation), to check that the
/// prompt the operator committee actually ran is this exact text.
///
/// `userText` is the chat-template user turn (the scaffold `<|im_start|>user\n … <|im_end|>
/// …<think>\n\n</think>\n\n` is pinned as token ids in the judge, not as text). The subject
/// goes in LAST so a per-market prefix can later be warmed once (prefix resume).
///
/// Subject extraction reads the `subject:` line out of the RSA-signed, relaxed-canonicalized
/// header bytes and decodes RFC 2047 encoded-words (B/Q, utf-8 / us-ascii / iso-8859-1) —
/// newspapers B-encode their subjects — so the judge sees the human headline, and it is the
/// signed bytes that define it, not a submitter-supplied string.
library JudgePrompt {
    // Prompt template — the full-rules prompt that scored 97.7 % on the 480-headline eval
    // (docs/GASKILLER-LLM-SETTLEMENT.md §2). `criteria` carries the market's resolution rules.
    string internal constant P0 = "You are the resolver of a prediction market.\nMarket question: ";
    string internal constant P1 = "\nResolution rules: ";
    string internal constant P2 = "\n\nA newspaper has sent a breaking-news alert email. Its subject line is:\n\"";
    string internal constant P3 = "\"\n\nJudging ONLY this subject line and the rules: does this email establish that "
        "the market resolves YES? Answer with exactly one word, YES or NO.";

    uint256 internal constant MAX_SUBJECT_BYTES = 400;
    uint256 internal constant MAX_CRITERIA_BYTES = 1200;

    /// @notice The user-turn text for (question, criteria, subject) = prefixText ++ tailText.
    function userText(string memory question, string memory criteria, bytes memory subject)
        internal
        pure
        returns (bytes memory)
    {
        return bytes.concat(prefixText(question, criteria), tailText(subject));
    }

    /// @notice Per-market constant part (everything up to and including the opening quote of
    /// the subject). This is the part a warmed prefix covers.
    function prefixText(string memory question, string memory criteria) internal pure returns (bytes memory) {
        return bytes.concat(bytes(P0), bytes(question), bytes(P1), bytes(criteria), bytes(P2));
    }

    /// @notice Per-email part: the subject and the closing instruction.
    function tailText(bytes memory subject) internal pure returns (bytes memory) {
        return bytes.concat(subject, bytes(P3));
    }

    /// @notice Verdicts are keyed by the hash of the exact user text.
    function promptKey(string memory question, string memory criteria, bytes memory subject)
        internal
        pure
        returns (bytes32)
    {
        return keccak256(userText(question, criteria, subject));
    }

    /// @notice Split a user text into (prefix, tail) at the FIRST occurrence of `P2`: the
    /// canonical tokenization is piecewise (prefix ids ++ tail ids) so a warmed prefix is a
    /// true prefix of every full prompt. Question/criteria may not contain a newline
    /// (enforced at market creation, see `isSafeMarketText`), so the first `P2` is the real
    /// split. Returns found=false when P2 is absent.
    function splitUserText(bytes memory text) internal pure returns (uint256 split, bool found) {
        bytes memory p2 = bytes(P2);
        if (text.length < p2.length) return (0, false);
        for (uint256 i = 0; i + p2.length <= text.length; ++i) {
            bool m = true;
            for (uint256 k = 0; k < p2.length; ++k) {
                if (text[i + k] != p2[k]) {
                    m = false;
                    break;
                }
            }
            if (m) return (i + p2.length, true);
        }
        return (0, false);
    }

    /// @notice Market question/criteria admissibility: non-empty, bounded, no newline/CR (so
    /// the template's line structure and the prefix split are unambiguous), no '<'.
    function isSafeMarketText(bytes memory s, uint256 maxLen) internal pure returns (bool) {
        if (s.length == 0 || s.length > maxLen) return false;
        for (uint256 i = 0; i < s.length; ++i) {
            uint8 c = uint8(s[i]);
            if (c < 0x20 || c == 0x3c || c == 0x7f) return false;
        }
        return true;
    }

    /// @notice A subject is admissible when it cannot smuggle chat-control text into the
    /// prompt: no '<' (every Qwen control token — `<|im_start|>`, `<think>`, `<tool_call>`… —
    /// starts with it), no C0 control bytes, no NUL, bounded length, non-empty.
    function isSafeSubject(bytes memory s) internal pure returns (bool) {
        if (s.length == 0 || s.length > MAX_SUBJECT_BYTES) return false;
        for (uint256 i = 0; i < s.length; ++i) {
            uint8 c = uint8(s[i]);
            if (c < 0x20 || c == 0x3c || c == 0x7f) return false;
        }
        return true;
    }

    // ------------------------------------------------------------------
    // Subject extraction from the signed header
    // ------------------------------------------------------------------

    /// @notice Find the `subject:` header field in relaxed-canonicalized header bytes, decode
    /// RFC 2047 encoded-words, collapse runs of whitespace to one space and trim.
    /// @return subject The decoded, whitespace-normalised subject bytes
    /// @return ok False when there is no subject line or an encoded-word uses an unsupported
    ///         charset/encoding (callers treat that email as not judgeable).
    function subjectFromHeader(bytes memory header) internal pure returns (bytes memory subject, bool ok) {
        (uint256 start, uint256 end, bool found) = _findSubjectValue(header);
        if (!found) return ("", false);
        bytes memory raw = new bytes(end - start);
        assembly ("memory-safe") {
            mcopy(add(raw, 0x20), add(add(header, 0x20), start), mload(raw))
        }
        (bytes memory decoded, bool dok) = decodeRfc2047(raw);
        if (!dok) return ("", false);
        return (_normalizeWs(decoded), true);
    }

    /// @dev Locate the value span of the first `subject:` field (name matched case-insensitively,
    /// at buffer start or after CRLF/LF); value runs to the next CRLF/LF or end of buffer.
    function _findSubjectValue(bytes memory h) private pure returns (uint256 start, uint256 end, bool found) {
        bytes8 needle = "subject:";
        uint256 n = h.length;
        for (uint256 i = 0; i + 8 <= n; ++i) {
            if (i != 0 && h[i - 1] != "\n") continue;
            bool m = true;
            for (uint256 k = 0; k < 8; ++k) {
                uint8 c = uint8(h[i + k]);
                if (c >= 0x41 && c <= 0x5a) c += 0x20; // ASCII lower
                if (bytes1(c) != needle[k]) {
                    m = false;
                    break;
                }
            }
            if (!m) continue;
            start = i + 8;
            while (start < n && (h[start] == " " || h[start] == "\t")) start++;
            end = start;
            while (end < n && h[end] != "\r" && h[end] != "\n") end++;
            return (start, end, true);
        }
        return (0, 0, false);
    }

    /// @notice Decode RFC 2047 encoded-words in `s` (`=?charset?B|Q?text?=`). Whitespace between
    /// two adjacent encoded-words is dropped (RFC 2047 §6.2); other text is copied through.
    function decodeRfc2047(bytes memory s) internal pure returns (bytes memory out, bool ok) {
        out = new bytes(s.length * 2 + 2); // latin1 → utf-8 can double
        uint256 w = 0;
        uint256 i = 0;
        bool lastWasEncoded = false;
        uint256 pendingWsStart = 0; // whitespace run start since the last encoded-word, if any
        bool pendingWs = false;
        while (i < s.length) {
            if (s[i] == "=" && i + 1 < s.length && s[i + 1] == "?") {
                (bytes memory piece, uint256 next, bool pok) = _decodeEncodedWord(s, i);
                if (pok) {
                    // drop the whitespace between two encoded words
                    if (pendingWs && lastWasEncoded) w = pendingWsStart;
                    for (uint256 k = 0; k < piece.length; ++k) {
                        out[w++] = piece[k];
                    }
                    i = next;
                    lastWasEncoded = true;
                    pendingWs = false;
                    continue;
                }
                if (next == type(uint256).max) return ("", false); // malformed/unsupported
            }
            if (s[i] == " " || s[i] == "\t") {
                if (!pendingWs) {
                    pendingWs = true;
                    pendingWsStart = w;
                }
            } else {
                pendingWs = false;
                lastWasEncoded = false;
            }
            out[w++] = s[i];
            i++;
        }
        assembly ("memory-safe") {
            mstore(out, w)
        }
        return (out, true);
    }

    /// @dev Parse one encoded-word starting at `i` (s[i]=='=' && s[i+1]=='?'). Returns
    /// (decodedBytes, indexAfter, true) on success; (,,false) with next=i when it is not an
    /// encoded-word at all; (,,false) with next=max when it is one but unsupported.
    function _decodeEncodedWord(bytes memory s, uint256 i)
        private
        pure
        returns (bytes memory piece, uint256 next, bool ok)
    {
        uint256 n = s.length;
        uint256 p = i + 2;
        uint256 csStart = p;
        while (p < n && s[p] != "?") p++;
        if (p + 2 >= n) return ("", i, false);
        bytes memory cs = _slice(s, csStart, p);
        bytes1 enc = s[p + 1];
        if (s[p + 2] != "?") return ("", i, false);
        uint256 textStart = p + 3;
        uint256 q = textStart;
        while (q + 1 < n && !(s[q] == "?" && s[q + 1] == "=")) q++;
        if (q + 1 >= n) return ("", i, false);
        bytes memory text = _slice(s, textStart, q);
        next = q + 2;

        // strip optional RFC 2231 language tag: charset*lang
        for (uint256 k = 0; k < cs.length; ++k) {
            if (cs[k] == "*") {
                cs = _slice(cs, 0, k);
                break;
            }
        }
        bytes memory raw;
        if (enc == "B" || enc == "b") raw = _base64Decode(text);
        else if (enc == "Q" || enc == "q") raw = _qDecode(text);
        else return ("", type(uint256).max, false);
        if (raw.length == 0 && text.length != 0) return ("", type(uint256).max, false);

        bytes memory lcs = _lower(cs);
        if (_eqBytes(lcs, "utf-8") || _eqBytes(lcs, "utf8") || _eqBytes(lcs, "us-ascii") || _eqBytes(lcs, "ascii")) {
            return (raw, next, true);
        }
        if (_eqBytes(lcs, "iso-8859-1") || _eqBytes(lcs, "latin1") || _eqBytes(lcs, "windows-1252")) {
            return (_latin1ToUtf8(raw), next, true);
        }
        return ("", type(uint256).max, false);
    }

    function _base64Decode(bytes memory data) private pure returns (bytes memory) {
        uint256 n = data.length;
        uint256 outLen = 0;
        bytes memory out = new bytes((n / 4 + 1) * 3);
        uint256 acc = 0;
        uint256 bits = 0;
        for (uint256 i = 0; i < n; ++i) {
            uint8 c = uint8(data[i]);
            uint256 v;
            if (c >= 0x41 && c <= 0x5a) v = c - 0x41;
            else if (c >= 0x61 && c <= 0x7a) v = c - 0x61 + 26;
            else if (c >= 0x30 && c <= 0x39) v = c - 0x30 + 52;
            else if (c == 0x2b) v = 62;
            else if (c == 0x2f) v = 63;
            else if (c == 0x3d) break; // '=' padding
            else return ""; // invalid char
            acc = (acc << 6) | v;
            bits += 6;
            if (bits >= 8) {
                bits -= 8;
                out[outLen++] = bytes1(uint8((acc >> bits) & 0xff));
            }
        }
        assembly ("memory-safe") {
            mstore(out, outLen)
        }
        return out;
    }

    function _qDecode(bytes memory data) private pure returns (bytes memory) {
        bytes memory out = new bytes(data.length);
        uint256 w = 0;
        for (uint256 i = 0; i < data.length; ++i) {
            bytes1 c = data[i];
            if (c == "_") {
                out[w++] = " ";
            } else if (c == "=" && i + 2 < data.length + 0 && i + 2 <= data.length - 1) {
                (uint8 hi, bool okh) = _hexVal(uint8(data[i + 1]));
                (uint8 lo, bool okl) = _hexVal(uint8(data[i + 2]));
                if (!okh || !okl) return "";
                out[w++] = bytes1(uint8(hi * 16 + lo));
                i += 2;
            } else {
                out[w++] = c;
            }
        }
        assembly ("memory-safe") {
            mstore(out, w)
        }
        return out;
    }

    function _hexVal(uint8 c) private pure returns (uint8, bool) {
        if (c >= 0x30 && c <= 0x39) return (c - 0x30, true);
        if (c >= 0x41 && c <= 0x46) return (c - 0x41 + 10, true);
        if (c >= 0x61 && c <= 0x66) return (c - 0x61 + 10, true);
        return (0, false);
    }

    function _latin1ToUtf8(bytes memory s) private pure returns (bytes memory out) {
        out = new bytes(s.length * 2);
        uint256 w = 0;
        for (uint256 i = 0; i < s.length; ++i) {
            uint8 c = uint8(s[i]);
            if (c < 0x80) {
                out[w++] = bytes1(c);
            } else {
                out[w++] = bytes1(uint8(0xc0 | (c >> 6)));
                out[w++] = bytes1(uint8(0x80 | (c & 0x3f)));
            }
        }
        assembly ("memory-safe") {
            mstore(out, w)
        }
    }

    /// @dev Collapse runs of SP/HT to one SP and trim both ends.
    function _normalizeWs(bytes memory s) private pure returns (bytes memory out) {
        out = new bytes(s.length);
        uint256 w = 0;
        bool inWs = true; // leading whitespace is dropped
        for (uint256 i = 0; i < s.length; ++i) {
            bytes1 c = s[i];
            if (c == " " || c == "\t") {
                if (!inWs) {
                    out[w++] = " ";
                    inWs = true;
                }
            } else {
                out[w++] = c;
                inWs = false;
            }
        }
        if (w > 0 && out[w - 1] == " ") w--;
        assembly ("memory-safe") {
            mstore(out, w)
        }
    }

    function _slice(bytes memory s, uint256 a, uint256 b) private pure returns (bytes memory out) {
        out = new bytes(b - a);
        assembly ("memory-safe") {
            mcopy(add(out, 0x20), add(add(s, 0x20), a), sub(b, a))
        }
    }

    function _lower(bytes memory s) private pure returns (bytes memory out) {
        out = new bytes(s.length);
        for (uint256 i = 0; i < s.length; ++i) {
            uint8 c = uint8(s[i]);
            out[i] = bytes1((c >= 0x41 && c <= 0x5a) ? c + 0x20 : c);
        }
    }

    function _eqBytes(bytes memory a, bytes memory b) private pure returns (bool) {
        return a.length == b.length && keccak256(a) == keccak256(b);
    }
}
