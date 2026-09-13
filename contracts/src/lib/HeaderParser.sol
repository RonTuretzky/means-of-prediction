// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title HeaderParser
/// @notice Structural parsing of the RSA-authenticated DKIM header block: exact field
/// extraction anchored at line starts, and a strict RFC 2822 `Date:` parser.
///
/// ## Why this exists
///
/// `DKIMVerifier.verify()` proves that `header` was signed by the sending domain's real
/// key, and then binds the claimed fields with a naive substring search over the whole
/// block. Substring containment is not field extraction, and the gap is exploitable:
///
///  * Any substring of ANY signed header is accepted as "the subject", so an analysis
///    piece titled "why the Fed cuts rates so slowly" satisfies a market whose condition
///    is the headline "Fed cuts rates".
///  * `EmailProof.timestamp` is a caller-supplied number that is never compared against
///    the signed `date:` header, so a genuine but old email settles a market whose
///    acceptance window it should miss.
///
/// Both are closed by parsing instead of searching: take the field's WHOLE value, and
/// derive the timestamp from the signed `date:` value rather than trusting the caller.
///
/// ## Input format
///
/// The bytes are relaxed-canonicalized signed headers (RFC 6376 section 3.4.2): field
/// names lowercased, no space after the colon, values unfolded onto one line with runs
/// of whitespace collapsed, lines separated by CRLF, and NO trailing CRLF after the
/// final line (which is the `dkim-signature:` field itself). Example:
///
///     from:The New York Times <nytdirect(at)nytimes.com>CRLF
///     subject:Breaking News: Fed cuts rates by 50 basis points CRLF
///     date:Wed, 12 Aug 2026 14:03:11 -0400 CRLF
///     to:subscriber(at)example.com CRLF
///     dkim-signature:v=1; a=rsa-sha256; c=relaxed/relaxed; d=nytimes.com; ... b=
///
/// (`(at)` stands in for the at-sign, which solc's natspec parser would read as a tag.)
///
/// ## Discipline
///
/// Every function is `internal pure`, total, and fail-closed: no reverts on malformed or
/// adversarial input, no guessing, no partial results. Failure is reported as
/// `found == false` / `ok == false`, never as a plausible-looking wrong answer. All
/// indexing is bounds-checked before use, and no arithmetic can overflow or underflow
/// (the only subtraction on parsed values is guarded).
library HeaderParser {
    /// @dev Minimum year accepted by `parseRfc2822Date`. Earlier dates are not
    /// representable as an unsigned Unix timestamp, so they are rejected rather than
    /// clamped to zero.
    uint256 internal constant MIN_YEAR = 1970;
    /// @dev Maximum year accepted by `parseRfc2822Date` (RFC 2822 years are 4 digits).
    uint256 internal constant MAX_YEAR = 9999;

    uint256 private constant SECONDS_PER_DAY = 86400;
    /// @dev Days from 0000-03-01 (the civil-calendar epoch used below) to 1970-01-01.
    uint256 private constant DAYS_TO_UNIX_EPOCH = 719468;
    /// @dev Days in a 400-year Gregorian era.
    uint256 private constant DAYS_PER_ERA = 146097;
    uint256 private constant NOT_FOUND = type(uint256).max;

    // ---------------------------------------------------------------------------
    // Field extraction
    // ---------------------------------------------------------------------------

    /// @notice Extract the exact value of a header field.
    /// @dev The name is matched ONLY at a line start — offset 0, or immediately after a
    /// CRLF — and the colon must follow the name immediately. That anchoring is the
    /// whole security property: a returned value is always a complete field value, never
    /// an arbitrary substring of the header block, and text that merely *looks* like a
    /// field (`... subject:evil` sitting inside another field's value) can never be
    /// mistaken for one.
    ///
    /// The value runs from just after the colon to the next CRLF, or to the end of the
    /// header block if this is the final line (which carries no trailing CRLF). It is
    /// returned verbatim: no trimming, no case folding, no decoding.
    ///
    /// Fail-closed rules:
    ///  * an empty name, or a name containing `:`/CR/LF, can never name a real field and
    ///    returns `found == false` without scanning;
    ///  * a value containing a bare CR or LF is rejected, so a stray line terminator can
    ///    never make this parser and some other parser disagree about where a field ends;
    ///  * only the FIRST match is returned — see `fieldUnique` when a duplicated field
    ///    must itself be treated as an error.
    ///
    /// The name must be supplied lowercase, matching relaxed canonicalization. This is a
    /// byte-exact comparison, so a header that was not relaxed-canonicalized (e.g. the
    /// `c=simple` form, which preserves `Subject:` capitalisation) simply reports the
    /// field as absent instead of being parsed under different rules.
    /// @param header The RSA-authenticated canonicalized header block.
    /// @param lowercaseName The field name to extract, lowercase and without the colon.
    /// @return value The field's exact value bytes (empty when not found).
    /// @return found True iff the field was located at a line start.
    function field(bytes memory header, bytes memory lowercaseName)
        internal
        pure
        returns (bytes memory value, bool found)
    {
        (uint256 start, uint256 end,, bool hit) = locate(header, lowercaseName, 0);
        if (!hit) return ("", false);
        value = slice(header, start, end);
        if (containsLineBreakChar(value)) return ("", false);
        return (value, true);
    }

    /// @notice Like `field`, but reports the field as absent if it appears at more than
    /// one line start.
    /// @dev RFC 5322 permits exactly one `from:`, `subject:` and `date:` per message. A
    /// duplicate is either a malformed message or a deliberate attempt to make two
    /// parsers pick different occurrences, and there is no principled way to choose
    /// between them — so this refuses to choose.
    function fieldUnique(bytes memory header, bytes memory lowercaseName)
        internal
        pure
        returns (bytes memory value, bool found)
    {
        (uint256 start, uint256 end, uint256 line, bool hit) = locate(header, lowercaseName, 0);
        if (!hit) return ("", false);
        uint256 nextLine = nextLineStart(header, line);
        if (nextLine != NOT_FOUND) {
            (,,, bool dup) = locate(header, lowercaseName, nextLine);
            if (dup) return ("", false);
        }
        value = slice(header, start, end);
        if (containsLineBreakChar(value)) return ("", false);
        return (value, true);
    }

    /// @notice Parse the signed `date:` field into a Unix timestamp.
    /// @dev The composition that closes the timestamp gap: the returned instant comes
    /// from bytes covered by the RSA signature, so callers can gate an acceptance window
    /// on it instead of on an attacker-chosen number.
    function signedDate(bytes memory header) internal pure returns (uint256 unixTs, bool ok) {
        (bytes memory value, bool found) = field(header, bytes("date"));
        if (!found) return (0, false);
        return parseRfc2822Date(value);
    }

    // ---------------------------------------------------------------------------
    // Date parsing
    // ---------------------------------------------------------------------------

    /// @notice Parse an RFC 2822 / RFC 5322 date-time into a Unix timestamp.
    /// @dev Accepted grammar (surrounding spaces/tabs are ignored):
    ///
    ///     [ DDD "," ] 1*2DIGIT SP mon SP 4DIGIT SP HH ":" MM [ ":" SS ] SP zone
    ///
    /// with `DDD` one of Mon..Sun, `mon` one of Jan..Dec (both case-insensitive), and
    /// `zone` either `+HHMM` / `-HHMM` or the literal `GMT` / `UTC` / `UT` (all +0000).
    /// Components are separated by one or more spaces or tabs. Seconds are optional
    /// because RFC 5322 makes them optional; when absent they are zero.
    ///
    /// Everything else is rejected rather than guessed at: 2-digit obsolete years,
    /// alphabetic military/US zone abbreviations (`EST`, `PDT`, ...) whose meaning is
    /// ambiguous per RFC 5322 section 4.3, trailing comments such as `(EDT)`, impossible
    /// calendar dates (`31 Apr`, `29 Feb 2023`), leap seconds, and any trailing bytes.
    /// The day-of-week is checked for syntactic validity but deliberately NOT checked for
    /// consistency with the date, since senders get it wrong and it carries no
    /// information.
    ///
    /// Years before 1970 are rejected (not representable as an unsigned timestamp), as is
    /// any date whose UTC instant would fall before the epoch after the zone offset is
    /// applied. The date-to-days conversion is the days-from-civil algorithm, exact for
    /// all Gregorian leap rules (divisible by 4, except centuries, except multiples of
    /// 400).
    /// @param value The raw `date:` field value.
    /// @return unixTs Seconds since 1970-01-01T00:00:00Z (zero when `ok` is false).
    /// @return ok True iff the whole input parsed as a valid instant.
    function parseRfc2822Date(bytes memory value) internal pure returns (uint256 unixTs, bool ok) {
        uint256 len = value.length;
        uint256 i = skipWsp(value, 0);

        // Optional "Wed, " day-of-week.
        if (i < len && isAlpha(value[i])) {
            if (i + 3 >= len) return (0, false);
            if (!isDayName(value[i], value[i + 1], value[i + 2])) return (0, false);
            if (value[i + 3] != ",") return (0, false);
            i = i + 4;
            (i, ok) = skipRequiredWsp(value, i);
            if (!ok) return (0, false);
        }

        uint256 day;
        (day, i, ok) = readUint(value, i, 1, 2);
        if (!ok) return (0, false);
        (i, ok) = skipRequiredWsp(value, i);
        if (!ok) return (0, false);

        uint256 month;
        if (i + 3 > len) return (0, false);
        (month, ok) = monthFromName(value[i], value[i + 1], value[i + 2]);
        if (!ok) return (0, false);
        i = i + 3;
        (i, ok) = skipRequiredWsp(value, i);
        if (!ok) return (0, false);

        uint256 year;
        (year, i, ok) = readUint(value, i, 4, 4);
        if (!ok) return (0, false);
        if (year < MIN_YEAR || year > MAX_YEAR) return (0, false);
        if (day == 0 || day > daysInMonth(year, month)) return (0, false);
        (i, ok) = skipRequiredWsp(value, i);
        if (!ok) return (0, false);

        uint256 hour;
        uint256 minute;
        uint256 second;
        (hour, i, ok) = readUint(value, i, 2, 2);
        if (!ok || hour > 23) return (0, false);
        if (i >= len || value[i] != ":") return (0, false);
        (minute, i, ok) = readUint(value, i + 1, 2, 2);
        if (!ok || minute > 59) return (0, false);
        if (i < len && value[i] == ":") {
            (second, i, ok) = readUint(value, i + 1, 2, 2);
            // Leap seconds (`60`) have no Unix representation; reject rather than fudge.
            if (!ok || second > 59) return (0, false);
        }
        (i, ok) = skipRequiredWsp(value, i);
        if (!ok) return (0, false);

        // Zone: +HHMM / -HHMM, or GMT / UTC / UT.
        bool negativeZone;
        uint256 zoneOffset;
        if (i < len && (value[i] == "+" || value[i] == "-")) {
            negativeZone = value[i] == "-";
            uint256 zh;
            uint256 zm;
            (zh, i, ok) = readUint(value, i + 1, 2, 2);
            if (!ok || zh > 23) return (0, false);
            (zm, i, ok) = readUint(value, i, 2, 2);
            if (!ok || zm > 59) return (0, false);
            zoneOffset = zh * 3600 + zm * 60;
        } else if (matchesAscii(value, i, "GMT") || matchesAscii(value, i, "UTC")) {
            i = i + 3;
        } else if (matchesAscii(value, i, "UT")) {
            i = i + 2;
        } else {
            return (0, false);
        }

        // Nothing but trailing whitespace may follow.
        if (skipWsp(value, i) != len) return (0, false);

        uint256 dayCount;
        (dayCount, ok) = daysFromCivil(year, month, day);
        if (!ok) return (0, false);
        uint256 local = dayCount * SECONDS_PER_DAY + hour * 3600 + minute * 60 + second;

        if (negativeZone) return (local + zoneOffset, true);
        if (local < zoneOffset) return (0, false); // pre-epoch once shifted to UTC
        return (local - zoneOffset, true);
    }

    // ---------------------------------------------------------------------------
    // Internals: header scanning
    // ---------------------------------------------------------------------------

    /// @dev Find `lowercaseName` at a line start at or after `fromLine`.
    /// @return start Index of the first value byte.
    /// @return end Index one past the last value byte.
    /// @return matchedLine Index of the matching line's first byte.
    /// @return found Whether a match was located.
    function locate(bytes memory header, bytes memory lowercaseName, uint256 fromLine)
        private
        pure
        returns (uint256 start, uint256 end, uint256 matchedLine, bool found)
    {
        uint256 n = lowercaseName.length;
        uint256 len = header.length;
        if (n == 0 || len == 0 || fromLine >= len) return (0, 0, 0, false);
        // A field name cannot contain the colon terminator or a line break, so such a
        // "name" is unmatchable by construction.
        for (uint256 k = 0; k < n; ++k) {
            bytes1 c = lowercaseName[k];
            if (c == ":" || c == "\r" || c == "\n") return (0, 0, 0, false);
        }

        uint256 line = fromLine;
        while (true) {
            // The colon must sit immediately after the name, still inside the block.
            if (line + n < len && header[line + n] == ":") {
                bool hit = true;
                for (uint256 k = 0; k < n; ++k) {
                    if (header[line + k] != lowercaseName[k]) {
                        hit = false;
                        break;
                    }
                }
                if (hit) {
                    uint256 vStart = line + n + 1;
                    return (vStart, lineEnd(header, vStart), line, true);
                }
            }
            uint256 next = nextLineStart(header, line);
            if (next == NOT_FOUND) return (0, 0, 0, false);
            line = next;
        }
    }

    /// @dev Index just past the next CRLF at or after `pos`, or NOT_FOUND if the header
    /// has no further line break (i.e. `pos` is on the final, CRLF-less line).
    function nextLineStart(bytes memory header, uint256 pos) private pure returns (uint256) {
        uint256 len = header.length;
        for (uint256 i = pos; i + 1 < len; ++i) {
            if (header[i] == "\r" && header[i + 1] == "\n") return i + 2;
        }
        return NOT_FOUND;
    }

    /// @dev Index of the CRLF ending the line that starts at/contains `pos`, or the
    /// header length when this is the final line (which has no trailing CRLF).
    function lineEnd(bytes memory header, uint256 pos) private pure returns (uint256) {
        uint256 len = header.length;
        for (uint256 i = pos; i + 1 < len; ++i) {
            if (header[i] == "\r" && header[i + 1] == "\n") return i;
        }
        return len;
    }

    function slice(bytes memory data, uint256 start, uint256 end) private pure returns (bytes memory out) {
        if (end <= start) return "";
        out = new bytes(end - start);
        for (uint256 i = 0; i < out.length; ++i) {
            out[i] = data[start + i];
        }
    }

    function containsLineBreakChar(bytes memory data) private pure returns (bool) {
        for (uint256 i = 0; i < data.length; ++i) {
            if (data[i] == "\r" || data[i] == "\n") return true;
        }
        return false;
    }

    // ---------------------------------------------------------------------------
    // Internals: lexing
    // ---------------------------------------------------------------------------

    function isDigit(bytes1 c) private pure returns (bool) {
        return c >= 0x30 && c <= 0x39;
    }

    function isAlpha(bytes1 c) private pure returns (bool) {
        return (c >= 0x41 && c <= 0x5a) || (c >= 0x61 && c <= 0x7a);
    }

    function lower(bytes1 c) private pure returns (bytes1) {
        return (c >= 0x41 && c <= 0x5a) ? bytes1(uint8(c) + 32) : c;
    }

    function skipWsp(bytes memory data, uint256 i) private pure returns (uint256) {
        while (i < data.length && (data[i] == 0x20 || data[i] == 0x09)) {
            ++i;
        }
        return i;
    }

    /// @dev Consume at least one space/tab; RFC 2822 requires folding whitespace between
    /// date components, and requiring it keeps token boundaries unambiguous.
    function skipRequiredWsp(bytes memory data, uint256 i) private pure returns (uint256, bool) {
        uint256 j = skipWsp(data, i);
        return (j, j > i);
    }

    /// @dev Read an unsigned decimal of between `minDigits` and `maxDigits` digits.
    /// Stops at `maxDigits`; a longer digit run therefore leaves a digit in front of the
    /// next expected separator and fails the caller's check, so `12345` never silently
    /// parses as `1234`.
    function readUint(bytes memory data, uint256 i, uint256 minDigits, uint256 maxDigits)
        private
        pure
        returns (uint256 result, uint256 next, bool ok)
    {
        uint256 len = data.length;
        uint256 digits;
        while (i < len && digits < maxDigits && isDigit(data[i])) {
            result = result * 10 + uint8(data[i]) - 0x30;
            ++i;
            ++digits;
        }
        if (digits < minDigits) return (0, i, false);
        return (result, i, true);
    }

    /// @dev Case-insensitive ASCII literal match at `i`.
    function matchesAscii(bytes memory data, uint256 i, string memory literal) private pure returns (bool) {
        bytes memory lit = bytes(literal);
        if (i + lit.length > data.length) return false;
        for (uint256 k = 0; k < lit.length; ++k) {
            if (lower(data[i + k]) != lower(lit[k])) return false;
        }
        return true;
    }

    /// @dev Syntactic check only: RFC 2822 lets the sender state a weekday, but it is
    /// redundant with the date and senders get it wrong, so it is never checked for
    /// consistency — only that it is one of the seven names.
    function isDayName(bytes1 a, bytes1 b, bytes1 c) private pure returns (bool) {
        return tripletIndex("montuewedthufrisatsun", a, b, c) != NOT_FOUND;
    }

    /// @return The 1-based month number, and whether the name was one of Jan..Dec.
    function monthFromName(bytes1 a, bytes1 b, bytes1 c) private pure returns (uint256, bool) {
        uint256 index = tripletIndex("janfebmaraprmayjunjulaugsepoctnovdec", a, b, c);
        if (index == NOT_FOUND) return (0, false);
        return (index + 1, true);
    }

    /// @dev Position of the lowercased triple `a b c` among `table`'s 3-byte entries.
    /// Only 3-aligned positions are considered, so an entry can never be matched across
    /// a boundary. NOT_FOUND when absent.
    function tripletIndex(bytes memory table, bytes1 a, bytes1 b, bytes1 c) private pure returns (uint256) {
        bytes1 la = lower(a);
        bytes1 lb = lower(b);
        bytes1 lc = lower(c);
        for (uint256 i = 0; i * 3 + 2 < table.length; ++i) {
            if (table[i * 3] == la && table[i * 3 + 1] == lb && table[i * 3 + 2] == lc) return i;
        }
        return NOT_FOUND;
    }

    // ---------------------------------------------------------------------------
    // Internals: calendar
    // ---------------------------------------------------------------------------

    function isLeapYear(uint256 y) private pure returns (bool) {
        return (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    }

    function daysInMonth(uint256 y, uint256 m) private pure returns (uint256) {
        if (m == 2) return isLeapYear(y) ? 29 : 28;
        if (m == 4 || m == 6 || m == 9 || m == 11) return 30;
        return 31;
    }

    /// @dev Days from 1970-01-01 to y-m-d (Howard Hinnant's days-from-civil). Shifting
    /// the year to start in March puts the leap day last, so era arithmetic handles all
    /// three Gregorian leap rules without a special case. Caller must have validated
    /// `1 <= m <= 12` and `d` against `daysInMonth`; `ok` is false only if the date
    /// precedes the Unix epoch, which the unsigned arithmetic below cannot represent.
    function daysFromCivil(uint256 y, uint256 m, uint256 d) private pure returns (uint256, bool) {
        unchecked {
            if (y < MIN_YEAR || y > MAX_YEAR) return (0, false);
            // Redundant given the caller's checks, but it keeps the `unchecked` block
            // free of any underflow even if this is ever reached by another path.
            if (m == 0 || m > 12 || d == 0 || d > 31) return (0, false);
            uint256 shifted = m <= 2 ? y - 1 : y; // January/February belong to the prior year
            uint256 era = shifted / 400;
            uint256 yearOfEra = shifted - era * 400; // [0, 399]
            uint256 monthIndex = m > 2 ? m - 3 : m + 9; // March = 0 ... February = 11
            uint256 dayOfYear = (153 * monthIndex + 2) / 5 + d - 1; // [0, 365]
            uint256 dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear; // [0, 146096]
            uint256 total = era * DAYS_PER_ERA + dayOfEra;
            if (total < DAYS_TO_UNIX_EPOCH) return (0, false);
            return (total - DAYS_TO_UNIX_EPOCH, true);
        }
    }
}
