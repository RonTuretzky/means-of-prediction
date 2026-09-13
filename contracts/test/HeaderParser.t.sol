// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {HeaderParser} from "../src/lib/HeaderParser.sol";

/// @notice Tests for HeaderParser: exact, line-anchored field extraction and strict
/// RFC 2822 date parsing over relaxed-canonicalized DKIM headers.
///
/// Every expected timestamp in `test_date_referenceTable` was computed independently
/// with Node (`new Date(...)`) and cross-checked with Python (`calendar.timegm`); none
/// of them were copied out of this implementation's own output. The two `_differential_`
/// tests go further and check ~680 generated dates against V8's calendar arithmetic via
/// ffi, so the leap-year rules are verified against a foreign implementation rather than
/// against hand-picked cases.
contract HeaderParserTest is Test {
    /// @dev A real relaxed/relaxed canonicalized header block (RFC 6376 section 3.4.2):
    /// lowercase field names, no space after the colon, CRLF between lines, and NO
    /// trailing CRLF after the final `dkim-signature:` line.
    ///
    /// Note the two natural traps it already contains: the subject value holds a colon
    /// ("Breaking News:"), and the dkim-signature value holds the literal text
    /// "h=from:subject:date:to" — i.e. every field name this library looks for appears
    /// inside some other field's value.
    bytes internal constant REAL_HEADER = "from:The New York Times <nytdirect@nytimes.com>\r\n"
        "subject:Breaking News: Fed cuts rates by 50 basis points in emergency move to steady markets\r\n"
        "date:Wed, 12 Aug 2026 14:03:11 -0400\r\n" "to:subscriber@example.com\r\n"
        "dkim-signature:v=1; a=rsa-sha256; c=relaxed/relaxed; d=nytimes.com; s=dev2026; t=1786557791;"
        " bh=ffyF3hCr9gh25sdwQOGAH3EK/n7/3pM0KV8EGC/JzYg=; h=from:subject:date:to; b=";

    string internal constant REAL_SUBJECT =
        "Breaking News: Fed cuts rates by 50 basis points in emergency move to steady markets";

    // ===========================================================================
    // Field extraction: the happy path
    // ===========================================================================

    function test_field_from() public pure {
        _assertField(REAL_HEADER, "from", "The New York Times <nytdirect@nytimes.com>");
    }

    function test_field_subject() public pure {
        // The whole value, including its internal colon — not a fragment of it.
        _assertField(REAL_HEADER, "subject", REAL_SUBJECT);
    }

    function test_field_date() public pure {
        _assertField(REAL_HEADER, "date", "Wed, 12 Aug 2026 14:03:11 -0400");
    }

    function test_field_to() public pure {
        _assertField(REAL_HEADER, "to", "subscriber@example.com");
    }

    /// @dev The final line carries no trailing CRLF, so the value must run to the end of
    /// the block. An off-by-one here would silently truncate the DKIM signature field.
    function test_field_dkimSignature_lastLineHasNoTrailingCrlf() public pure {
        (bytes memory value, bool found) = HeaderParser.field(REAL_HEADER, bytes("dkim-signature"));
        assertTrue(found, "dkim-signature not found");
        assertEq(
            string(value),
            "v=1; a=rsa-sha256; c=relaxed/relaxed; d=nytimes.com; s=dev2026; t=1786557791;"
            " bh=ffyF3hCr9gh25sdwQOGAH3EK/n7/3pM0KV8EGC/JzYg=; h=from:subject:date:to; b=",
            "dkim-signature value truncated or over-read"
        );
        // The value really does reach the last byte of the header.
        bytes memory header = REAL_HEADER;
        assertEq(uint8(value[value.length - 1]), uint8(header[header.length - 1]));
    }

    /// @dev Same header but WITH a trailing CRLF: the terminator must not be included.
    function test_field_lastLineWithTrailingCrlf() public pure {
        bytes memory header = bytes.concat(REAL_HEADER, "\r\n");
        (bytes memory value, bool found) = HeaderParser.field(header, bytes("dkim-signature"));
        assertTrue(found);
        assertEq(uint8(value[value.length - 1]), uint8(bytes1("=")), "trailing CRLF leaked into the value");
    }

    function test_field_singleLineHeader() public pure {
        _assertField("subject:only line, no CRLF anywhere", "subject", "only line, no CRLF anywhere");
    }

    function test_field_firstLineOfHeader() public pure {
        // Offset 0 counts as a line start.
        _assertField("from:a@b.com\r\nsubject:hi", "from", "a@b.com");
    }

    function test_field_emptyValueIsFoundNotMissing() public pure {
        _assertField("from:a@b.com\r\nsubject:\r\nto:c@d.com", "subject", "");
        _assertField("from:a@b.com\r\nsubject:", "subject", ""); // empty value on the last line
    }

    // ===========================================================================
    // Field extraction: the soundness property (BUG 2)
    // ===========================================================================

    /// @dev THE bug this library exists to close. `DKIMVerifier` binds the subject with
    /// a substring search over the whole header block, so an attacker only has to get
    /// the market's headline to appear *somewhere* in some signed field. Here the real
    /// subject is an analysis piece; the market condition "Fed cuts rates" is a substring
    /// of it, and today that settles the market YES. Field extraction returns the WHOLE
    /// value, so the caller matches against the real headline and the regex decides.
    function test_field_returnsWholeValueNotSubstring() public pure {
        bytes memory header = "from:The New York Times <nytdirect@nytimes.com>\r\n"
            "subject:Opinion: why the Fed cuts rates so slowly\r\n" "date:Wed, 12 Aug 2026 14:03:11 -0400";
        (bytes memory value, bool found) = HeaderParser.field(header, bytes("subject"));
        assertTrue(found);
        assertEq(string(value), "Opinion: why the Fed cuts rates so slowly");
        assertTrue(keccak256(value) != keccak256(bytes("Fed cuts rates")), "a substring is not the subject");
    }

    /// @dev An attacker-controlled value that contains the literal text "subject:evil".
    /// It is not at a line start, so it is not a field, and the real subject wins.
    function test_field_ignoresNameInjectedMidValue() public pure {
        bytes memory header = "from:Evil Corp <spoof@example.com> subject:evil headline\r\n"
            "subject:The real headline\r\n" "date:Wed, 12 Aug 2026 14:03:11 -0400";

        _assertField(header, "subject", "The real headline");
        // ...and the injected text is returned as what it actually is: part of `from`.
        _assertField(header, "from", "Evil Corp <spoof@example.com> subject:evil headline");
    }

    /// @dev The sharpest form: the ONLY occurrence of "subject:" sits inside another
    /// field's value. The correct answer is "no subject field", not "evil".
    function test_field_missingWhenOnlyOccurrenceIsMidValue() public pure {
        bytes memory header = "from:spoof@example.com subject:evil headline\r\n" "date:Wed, 12 Aug 2026 14:03:11 -0400";
        (bytes memory value, bool found) = HeaderParser.field(header, bytes("subject"));
        assertFalse(found, "mid-value text must not be mistaken for a field");
        assertEq(value.length, 0);
    }

    /// @dev The real header's dkim-signature value lists the signed field names
    /// ("h=from:subject:date:to"). Those are values, not fields.
    function test_field_ignoresNamesInsideTheDkimSignatureValue() public pure {
        // Every lookup still resolves to the genuine field earlier in the block.
        _assertField(REAL_HEADER, "subject", REAL_SUBJECT);
        _assertField(REAL_HEADER, "to", "subscriber@example.com");

        // With those genuine fields removed, the same text inside `h=` must not match.
        bytes memory header = "from:a@b.com\r\n" "dkim-signature:v=1; h=from:subject:date:to; b=xyz";
        (, bool found) = HeaderParser.field(header, bytes("subject"));
        assertFalse(found, "h= tag contents must not be readable as fields");
    }

    /// @dev A line whose name merely ENDS with the sought name ("xsubject:") must not
    /// match: the name has to start at the line start, not merely occur on the line.
    function test_field_rejectsNameSuffixAtLineStart() public pure {
        _assertField("xsubject:decoy\r\nsubject:real", "subject", "real");

        (, bool found) = HeaderParser.field("xsubject:decoy", bytes("subject"));
        assertFalse(found);
    }

    /// @dev A line whose name merely BEGINS with the sought name ("date-warning:") must
    /// not match: the colon has to follow the name immediately.
    function test_field_rejectsNamePrefixAtLineStart() public pure {
        bytes memory header = "date-warning:this is not the date\r\n" "subjectx:not the subject\r\n"
            "date:Wed, 12 Aug 2026 14:03:11 -0400\r\n" "subject:real";
        _assertField(header, "date", "Wed, 12 Aug 2026 14:03:11 -0400");
        _assertField(header, "subject", "real");
    }

    /// @dev Asking for a fragment of a real field name finds nothing.
    function test_field_rejectsPartialNameLookup() public pure {
        (, bool a) = HeaderParser.field(REAL_HEADER, bytes("ject"));
        (, bool b) = HeaderParser.field(REAL_HEADER, bytes("dkim"));
        (, bool c) = HeaderParser.field(REAL_HEADER, bytes("sub"));
        assertFalse(a);
        assertFalse(b);
        assertFalse(c);
    }

    function test_field_missingField() public pure {
        (bytes memory value, bool found) = HeaderParser.field(REAL_HEADER, bytes("reply-to"));
        assertFalse(found);
        assertEq(value.length, 0);
    }

    // ===========================================================================
    // Field extraction: degenerate and adversarial inputs (must never revert)
    // ===========================================================================

    function test_field_emptyHeaderOrEmptyName() public pure {
        (, bool a) = HeaderParser.field("", bytes("subject"));
        (, bool b) = HeaderParser.field(REAL_HEADER, bytes(""));
        (, bool c) = HeaderParser.field("", bytes(""));
        assertFalse(a);
        assertFalse(b);
        assertFalse(c);
    }

    /// @dev A "name" containing a colon or a line break can never be a field name.
    function test_field_rejectsUnmatchableNames() public pure {
        (, bool a) = HeaderParser.field(REAL_HEADER, bytes("subject:"));
        (, bool b) = HeaderParser.field(REAL_HEADER, bytes("from:The"));
        (, bool c) = HeaderParser.field(REAL_HEADER, bytes("\r\nsubject"));
        assertFalse(a);
        assertFalse(b);
        assertFalse(c);
    }

    /// @dev Byte-exact name matching: relaxed canonicalization lowercases names, so a
    /// capitalised name means these are not the bytes that were canonicalized. Fail
    /// closed rather than parse under different rules.
    function test_field_nameMatchIsCaseSensitive() public pure {
        (, bool found) = HeaderParser.field("Subject:Capitalised\r\nfrom:a@b.com", bytes("subject"));
        assertFalse(found);
    }

    /// @dev Headers that end mid-name, or consist only of terminators, must be handled.
    function test_field_truncatedHeaders() public pure {
        (, bool a) = HeaderParser.field("subject", bytes("subject")); // no colon at all
        (, bool b) = HeaderParser.field("from:a\r\n", bytes("subject")); // trailing CRLF, nothing after
        (, bool c) = HeaderParser.field("\r\n\r\n\r\n", bytes("subject"));
        (, bool d) = HeaderParser.field("\r", bytes("subject"));
        assertFalse(a);
        assertFalse(b);
        assertFalse(c);
        assertFalse(d);

        // A field on the line after a trailing CRLF is still reachable.
        _assertField("from:a\r\nsubject:tail", "subject", "tail");
    }

    /// @dev A bare CR or LF inside a value is rejected: it is the one byte sequence that
    /// could make this parser and another parser disagree about where the field ends.
    function test_field_rejectsValueWithBareLineBreak() public pure {
        bytes memory header = "subject:first\nsecond\r\nfrom:a@b.com";
        (, bool found) = HeaderParser.field(header, bytes("subject"));
        assertFalse(found, "value with a bare LF must be rejected");
        // The rest of the block still parses.
        _assertField(header, "from", "a@b.com");
    }

    function test_field_firstOccurrenceWins() public pure {
        _assertField("subject:first\r\nsubject:second", "subject", "first");
    }

    /// @dev `fieldUnique` refuses to choose between duplicated fields.
    function test_fieldUnique_rejectsDuplicates() public pure {
        (bytes memory a, bool foundA) = HeaderParser.fieldUnique("subject:first\r\nsubject:second", bytes("subject"));
        assertFalse(foundA, "duplicate subject must be rejected");
        assertEq(a.length, 0);

        // Duplicate on the very last (CRLF-less) line, too.
        (, bool foundB) = HeaderParser.fieldUnique("from:a\r\nsubject:x\r\nto:b\r\nsubject:y", bytes("subject"));
        assertFalse(foundB);
    }

    function test_fieldUnique_acceptsSingleOccurrence() public pure {
        (bytes memory value, bool found) = HeaderParser.fieldUnique(REAL_HEADER, bytes("subject"));
        assertTrue(found);
        assertEq(string(value), REAL_SUBJECT);

        // A duplicate of a DIFFERENT field does not affect this one.
        (, bool stillFound) = HeaderParser.fieldUnique("to:a\r\nsubject:x\r\nto:b", bytes("subject"));
        assertTrue(stillFound);
    }

    function testFuzz_field_neverReverts(bytes memory header, bytes memory name) public pure {
        (bytes memory value, bool found) = HeaderParser.field(header, name);
        if (found) {
            // A found value is always a whole line's worth of bytes: no terminators.
            for (uint256 i = 0; i < value.length; ++i) {
                assertTrue(value[i] != "\r" && value[i] != "\n");
            }
            assertTrue(value.length + name.length + 1 <= header.length);
        } else {
            assertEq(value.length, 0);
        }
    }

    /// @dev Property: whatever `field` returns, `name + ":" + value` must occur in the
    /// header at a line start. Fuzzed over a header shape that mixes real fields with
    /// attacker-controlled bytes.
    function testFuzz_field_valueIsAlwaysAWholeField(bytes memory injected) public pure {
        bytes memory header = bytes.concat("from:a@b.com ", injected, "\r\nsubject:the real one\r\nto:c@d.com");
        (bytes memory value, bool found) = HeaderParser.field(header, bytes("subject"));
        if (!found) return; // injected bytes may have made `from`'s value unparseable
        // The subject can only be the genuine one, or one the injection created at a
        // line start of its own (which requires the injection to contain a real CRLF).
        if (keccak256(value) != keccak256(bytes("the real one"))) {
            assertTrue(_contains(injected, bytes("\r\n")), "value changed without an injected line break");
        }
    }

    // ===========================================================================
    // Date parsing
    // ===========================================================================

    /// @dev Reference instants. Computed with Node `new Date(s).getTime()/1000` and
    /// independently re-derived with Python `calendar.timegm(...) - offset`.
    function test_date_referenceTable() public pure {
        _assertDate("Wed, 12 Aug 2026 14:03:11 -0400", 1786557791);
        _assertDate("Wed, 12 Aug 2026 23:33:11 +0530", 1786557791);
        _assertDate("Wed, 12 Aug 2026 18:03:11 +0000", 1786557791);
        _assertDate("12 Aug 2026 14:03:11 +0000", 1786543391);
        _assertDate("Sat, 2 Jan 2021 03:04:05 +0000", 1609556645);
        _assertDate("Thu, 1 Jan 1970 00:00:00 +0000", 0);
        _assertDate("Thu, 1 Jan 1970 00:00:00 -0100", 3600);
        _assertDate("Thu, 1 Jan 1970 12:00:00 +1200", 0);
        _assertDate("Thu, 29 Feb 2024 12:00:00 +0000", 1709208000);
        _assertDate("Tue, 29 Feb 2000 00:00:00 +0000", 951782400);
        _assertDate("Fri, 1 Mar 2024 00:00:00 +0000", 1709251200);
        _assertDate("Mon, 29 Feb 2016 06:07:08 +0100", 1456722428);
        _assertDate("Mon, 28 Feb 2022 23:59:59 +0000", 1646092799);
        _assertDate("Tue, 1 Mar 2022 00:00:00 +0000", 1646092800);
        _assertDate("Wed, 1 Jan 2100 00:00:00 +0000", 4102444800);
        _assertDate("Mon, 1 Mar 2100 00:00:00 +0000", 4107542400);
        _assertDate("Sun, 31 Dec 2023 23:59:59 -0500", 1704085199);
        _assertDate("Fri, 13 Sep 2024 07:08:09 -0700", 1726236489);
        _assertDate("Tue, 19 Jan 2038 03:14:07 +0000", 2147483647);
        _assertDate("Mon, 31 Dec 2029 23:59:59 -1200", 1893499199);
        _assertDate("Mon, 31 Dec 2029 23:59:59 +1400", 1893405599);
        _assertDate("Wed, 4 Jul 1979 09:30:00 -0230", 299937600);
        _assertDate("Sun, 30 Nov 2025 00:00:00 GMT", 1764460800);
        _assertDate("Sat, 15 Jun 2030 10:20:30 +0000", 1907749230);
        _assertDate("Thu, 31 Aug 2028 23:59:59 +0000", 1851379199);
        _assertDate("Wed, 1 Apr 2026 00:00:01 -0400", 1775016001);
        _assertDate("Sat, 31 Dec 9999 23:59:59 +0000", 253402300799);
    }

    /// @dev The same instant written in three zones must produce one timestamp. This is
    /// the property a market window depends on.
    function test_date_zonesAgreeOnTheInstant() public pure {
        uint256 expected = 1786557791; // 2026-08-12T18:03:11Z
        _assertDate("Wed, 12 Aug 2026 14:03:11 -0400", expected); // negative offset
        _assertDate("Wed, 12 Aug 2026 23:33:11 +0530", expected); // positive, half-hour
        _assertDate("Wed, 12 Aug 2026 18:03:11 +0000", expected); // zulu
        _assertDate("Wed, 12 Aug 2026 18:03:11 GMT", expected);
        _assertDate("Wed, 12 Aug 2026 18:03:11 UTC", expected);
        _assertDate("Wed, 12 Aug 2026 18:03:11 UT", expected);
        _assertDate("Wed, 12 Aug 2026 06:03:11 -1200", expected); // extreme west
        _assertDate("Thu, 13 Aug 2026 08:03:11 +1400", expected); // extreme east, next day
    }

    /// @dev A negative offset must move the instant LATER and a positive one EARLIER —
    /// a sign flip here would still produce plausible-looking timestamps.
    function test_date_offsetSignDirection() public pure {
        (uint256 utc,) = HeaderParser.parseRfc2822Date("12 Aug 2026 12:00:00 +0000");
        (uint256 west,) = HeaderParser.parseRfc2822Date("12 Aug 2026 12:00:00 -0500");
        (uint256 east,) = HeaderParser.parseRfc2822Date("12 Aug 2026 12:00:00 +0500");
        assertEq(west, utc + 5 hours, "negative zone must be behind UTC");
        assertEq(east, utc - 5 hours, "positive zone must be ahead of UTC");
    }

    function test_date_optionalDayOfWeek() public pure {
        uint256 expected = 1786543391;
        _assertDate("12 Aug 2026 14:03:11 +0000", expected);
        _assertDate("Wed, 12 Aug 2026 14:03:11 +0000", expected);
        // The weekday is checked for syntax, not for consistency with the date.
        _assertDate("Mon, 12 Aug 2026 14:03:11 +0000", expected);
        _assertDate("SUN, 12 Aug 2026 14:03:11 +0000", expected);
    }

    function test_date_oneOrTwoDigitDay() public pure {
        _assertDate("Sat, 2 Jan 2021 03:04:05 +0000", 1609556645);
        _assertDate("Sat, 02 Jan 2021 03:04:05 +0000", 1609556645);
        // Obsolete folding whitespace: more than one space between components.
        _assertDate("Sat,  2 Jan 2021 03:04:05 +0000", 1609556645);
        _assertDate("Sat, 2  Jan  2021  03:04:05  +0000", 1609556645);
    }

    /// @dev RFC 5322 makes seconds optional.
    function test_date_optionalSeconds() public pure {
        _assertDate("Wed, 12 Aug 2026 14:03 +0000", 1786543391 - 11);
        _assertDate("Wed, 12 Aug 2026 14:03:00 +0000", 1786543391 - 11);
    }

    function test_date_monthNamesAreCaseInsensitive() public pure {
        _assertDate("12 aug 2026 14:03:11 +0000", 1786543391);
        _assertDate("12 AUG 2026 14:03:11 +0000", 1786543391);
        _assertDate("12 AuG 2026 14:03:11 +0000", 1786543391);
    }

    function test_date_allTwelveMonths() public pure {
        // 1st of each month of 2024 at midnight UTC; day counts verified against Node.
        _assertDate("1 Jan 2024 00:00:00 +0000", 1704067200);
        _assertDate("1 Feb 2024 00:00:00 +0000", 1706745600);
        _assertDate("1 Mar 2024 00:00:00 +0000", 1709251200);
        _assertDate("1 Apr 2024 00:00:00 +0000", 1711929600);
        _assertDate("1 May 2024 00:00:00 +0000", 1714521600);
        _assertDate("1 Jun 2024 00:00:00 +0000", 1717200000);
        _assertDate("1 Jul 2024 00:00:00 +0000", 1719792000);
        _assertDate("1 Aug 2024 00:00:00 +0000", 1722470400);
        _assertDate("1 Sep 2024 00:00:00 +0000", 1725148800);
        _assertDate("1 Oct 2024 00:00:00 +0000", 1727740800);
        _assertDate("1 Nov 2024 00:00:00 +0000", 1730419200);
        _assertDate("1 Dec 2024 00:00:00 +0000", 1733011200);
    }

    // --- leap years -------------------------------------------------------------

    /// @dev All three Gregorian rules: /4 is a leap year, /100 is not, /400 is.
    function test_date_leapYearRules() public pure {
        _assertDate("29 Feb 2024 12:00:00 +0000", 1709208000); // divisible by 4
        _assertDate("29 Feb 2000 00:00:00 +0000", 951782400); // divisible by 400
        _assertDate("29 Feb 2016 06:07:08 +0100", 1456722428);
        _assertDateInvalid("29 Feb 2023 00:00:00 +0000"); // common year
        _assertDateInvalid("29 Feb 2100 00:00:00 +0000"); // divisible by 100, not 400
        _assertDateInvalid("29 Feb 1900 00:00:00 +0000"); // (also pre-1970, doubly invalid)
        _assertDateInvalid("30 Feb 2024 00:00:00 +0000");
    }

    /// @dev A century that is not a leap year must not shift subsequent dates by a day:
    /// if 2100 were treated as leap, 1 Mar 2100 would come out 86400 too high.
    function test_date_nonLeapCenturyDoesNotShiftLaterDates() public pure {
        _assertDate("28 Feb 2100 00:00:00 +0000", 4107456000);
        _assertDate("1 Mar 2100 00:00:00 +0000", 4107542400);
        (uint256 feb28,) = HeaderParser.parseRfc2822Date("28 Feb 2100 00:00:00 +0000");
        (uint256 mar1,) = HeaderParser.parseRfc2822Date("1 Mar 2100 00:00:00 +0000");
        assertEq(mar1 - feb28, 1 days, "2100 is not a leap year");

        // ...whereas 2024 does have a 29 February.
        (uint256 feb28_24,) = HeaderParser.parseRfc2822Date("28 Feb 2024 00:00:00 +0000");
        (uint256 mar1_24,) = HeaderParser.parseRfc2822Date("1 Mar 2024 00:00:00 +0000");
        assertEq(mar1_24 - feb28_24, 2 days, "2024 is a leap year");
    }

    function test_date_monthLengths() public pure {
        _assertDate("31 Jan 2025 00:00:00 +0000", 1738281600);
        _assertDateInvalid("31 Apr 2025 00:00:00 +0000");
        _assertDateInvalid("31 Jun 2025 00:00:00 +0000");
        _assertDateInvalid("31 Sep 2025 00:00:00 +0000");
        _assertDateInvalid("31 Nov 2025 00:00:00 +0000");
        _assertDate("30 Apr 2025 00:00:00 +0000", 1745971200);
        _assertDate("30 Nov 2025 00:00:00 +0000", 1764460800);
        _assertDateInvalid("32 Jan 2025 00:00:00 +0000");
        _assertDateInvalid("0 Jan 2025 00:00:00 +0000");
        _assertDateInvalid("00 Jan 2025 00:00:00 +0000");
    }

    // --- range ------------------------------------------------------------------

    function test_date_epochBoundary() public pure {
        _assertDate("1 Jan 1970 00:00:00 +0000", 0);
        _assertDate("1 Jan 1970 00:00:01 +0000", 1);
        _assertDate("1 Jan 1970 05:00:00 +0500", 0);
        // Anything that lands before the epoch once shifted to UTC is out of range.
        _assertDateInvalid("1 Jan 1970 00:00:00 +0001");
        _assertDateInvalid("1 Jan 1970 04:59:59 +0500");
        _assertDateInvalid("31 Dec 1969 23:59:59 +0000");
        _assertDateInvalid("1 Jan 1969 00:00:00 +0000");
    }

    function test_date_yearRange() public pure {
        _assertDate("31 Dec 9999 23:59:59 +0000", 253402300799);
        _assertDateInvalid("1 Jan 10000 00:00:00 +0000"); // 5-digit year
        _assertDateInvalid("1 Jan 999 00:00:00 +0000"); // 3-digit year
        _assertDateInvalid("1 Jan 26 00:00:00 +0000"); // obsolete 2-digit year
    }

    // --- malformed inputs -------------------------------------------------------

    function test_date_malformed() public pure {
        _assertDateInvalid(""); // empty
        _assertDateInvalid("   "); // whitespace only
        _assertDateInvalid("not a date at all");
        _assertDateInvalid("Wed, 12 Aug 2026"); // no time
        _assertDateInvalid("12 Aug 2026 14:03:11"); // no zone
        _assertDateInvalid("Aug 12 2026 14:03:11 +0000"); // US order
        _assertDateInvalid("2026-08-12T14:03:11Z"); // ISO 8601
        _assertDateInvalid("Wed 12 Aug 2026 14:03:11 +0000"); // missing comma
        _assertDateInvalid("Wed,12 Aug 2026 14:03:11 +0000"); // missing FWS after comma
        _assertDateInvalid("Wednesday, 12 Aug 2026 14:03:11 +0000"); // long weekday
        _assertDateInvalid("Xyz, 12 Aug 2026 14:03:11 +0000"); // not a weekday
        _assertDateInvalid("12 Foo 2026 14:03:11 +0000"); // not a month
        _assertDateInvalid("12 August 2026 14:03:11 +0000"); // long month name
        _assertDateInvalid("012 Aug 2026 14:03:11 +0000"); // 3-digit day
        _assertDateInvalid("12 Aug 2026 4:03:11 +0000"); // 1-digit hour
        _assertDateInvalid("12 Aug 2026 24:00:00 +0000"); // hour out of range
        _assertDateInvalid("12 Aug 2026 14:60:00 +0000"); // minute out of range
        _assertDateInvalid("12 Aug 2026 14:03:60 +0000"); // leap second: no Unix instant
        _assertDateInvalid("12 Aug 2026 14-03-11 +0000"); // wrong time separator
        _assertDateInvalid("12 Aug 2026 14:03:11 0000"); // zone without a sign
        _assertDateInvalid("12 Aug 2026 14:03:11 +000"); // 3-digit zone
        _assertDateInvalid("12 Aug 2026 14:03:11 +00000"); // 5-digit zone
        _assertDateInvalid("12 Aug 2026 14:03:11 +2400"); // zone hour out of range
        _assertDateInvalid("12 Aug 2026 14:03:11 +0060"); // zone minute out of range
        _assertDateInvalid("12 Aug 2026 14:03:11 EST"); // ambiguous obsolete zone
        _assertDateInvalid("12 Aug 2026 14:03:11 Z"); // not RFC 2822
        _assertDateInvalid("12 Aug 2026 14:03:11 +0000 (EDT)"); // trailing comment
        _assertDateInvalid("12 Aug 2026 14:03:11 +0000 extra"); // trailing junk
        _assertDateInvalid("12 Aug 2026 14:03:11 +0000\r\n"); // trailing CRLF
        _assertDateInvalid("12 Aug 2026 14:03:11+0000"); // no FWS before the zone
        _assertDateInvalid("12Aug 2026 14:03:11 +0000"); // no FWS after the day
        _assertDateInvalid("12 Aug2026 14:03:11 +0000"); // no FWS after the month
        _assertDateInvalid("Wed, , 12 Aug 2026 14:03:11 +0000");
        _assertDateInvalid("-12 Aug 2026 14:03:11 +0000"); // signed day
    }

    /// @dev Leading/trailing spaces and tabs are tolerated (a `c=simple` header keeps the
    /// space after the colon), but nothing else is.
    function test_date_surroundingWhitespaceTolerated() public pure {
        _assertDate(" Wed, 12 Aug 2026 14:03:11 -0400", 1786557791);
        _assertDate("\tWed, 12 Aug 2026 14:03:11 -0400 \t", 1786557791);
    }

    function testFuzz_date_neverReverts(bytes memory value) public pure {
        (uint256 ts, bool ok) = HeaderParser.parseRfc2822Date(value);
        if (!ok) assertEq(ts, 0);
    }

    /// @dev Random ASCII noise must essentially never parse; if it does, it must at least
    /// round-trip through the two invariants we rely on.
    function testFuzz_date_asciiNoise(uint256 seed) public pure {
        bytes memory value = new bytes(1 + (seed % 40));
        for (uint256 i = 0; i < value.length; ++i) {
            value[i] = bytes1(uint8(32 + (uint256(keccak256(abi.encode(seed, i))) % 95)));
        }
        (uint256 ts, bool ok) = HeaderParser.parseRfc2822Date(value);
        if (ok) assertLe(ts, 253402300799);
    }

    // ===========================================================================
    // Composition: the signed date (BUG 1)
    // ===========================================================================

    /// @dev The timestamp a market window should be gated on: derived from the signed
    /// header bytes, not from an attacker-supplied `EmailProof.timestamp`.
    function test_signedDate_fromRealHeader() public pure {
        (uint256 ts, bool ok) = HeaderParser.signedDate(REAL_HEADER);
        assertTrue(ok);
        // Equals the DKIM `t=` tag in the same header, and the Node-computed instant.
        assertEq(ts, 1786557791);
    }

    function test_signedDate_missingOrMalformedDate() public pure {
        (uint256 a, bool okA) = HeaderParser.signedDate("from:a@b.com\r\nsubject:hi");
        assertFalse(okA);
        assertEq(a, 0);

        (, bool okB) = HeaderParser.signedDate("from:a@b.com\r\ndate:whenever\r\nsubject:hi");
        assertFalse(okB);

        // A "date:" hidden inside another value is not a date field.
        (, bool okC) = HeaderParser.signedDate("from:a@b.com date:Wed, 12 Aug 2026 14:03:11 -0400\r\nsubject:hi");
        assertFalse(okC, "mid-value date must not be picked up");
    }

    // ===========================================================================
    // Differential tests against V8's calendar arithmetic (ffi)
    // ===========================================================================

    /// @dev Sweeps every month of nine representative years at the days where month
    /// length and leap rules bite (1, 28, 29, 30, 31) and compares each result with
    /// Node's `Date.UTC`. 540 cases, one ffi call.
    function test_differential_calendarSweepAgainstNode() public {
        uint256[9] memory yearList = [uint256(1970), 1999, 2000, 2023, 2024, 2026, 2100, 2400, 9999];
        uint256[5] memory dayList = [uint256(1), 28, 29, 30, 31];

        string[] memory cases = new string[](9 * 12 * 5);
        uint256 n;
        for (uint256 y = 0; y < yearList.length; ++y) {
            for (uint256 m = 1; m <= 12; ++m) {
                // Alternate zones so both offset directions are swept.
                string memory zone = "+0000";
                if (m % 2 == 1) zone = "-0330";
                for (uint256 d = 0; d < dayList.length; ++d) {
                    cases[n++] =
                        string.concat(_u2(dayList[d]), " ", _monthName(m), " ", _u4(yearList[y]), " 12:34:56 ", zone);
                }
            }
        }
        _checkAgainstNode(cases, n);
    }

    /// @dev 200 pseudo-random date-times, including deliberately out-of-range
    /// components, checked against Node. One ffi call.
    function test_differential_randomDatesAgainstNode() public {
        string[] memory cases = new string[](200);
        for (uint256 i = 0; i < cases.length; ++i) {
            uint256 r = uint256(keccak256(abi.encode("headerparser", i)));
            uint256 year = 1970 + (r % 8030);
            uint256 month = 1 + ((r >> 16) % 12);
            uint256 day = 1 + ((r >> 32) % 31);
            uint256 hour = (r >> 48) % 26; // 24 and 25 must be rejected
            uint256 minute = (r >> 64) % 62; // 60 and 61 must be rejected
            uint256 second = (r >> 80) % 62;
            uint256 zh = (r >> 104) % 24;
            uint256 zm = ((r >> 112) % 4) * 15;
            string memory sign = "+";
            if (((r >> 96) & 1) == 1) sign = "-";
            string memory prefix = "";
            if (((r >> 120) & 1) == 1) prefix = string.concat(_dayName((r >> 128) % 7), ", ");
            cases[i] = string.concat(
                prefix,
                _u2(day),
                " ",
                _monthName(month),
                " ",
                _u4(year),
                " ",
                _u2(hour),
                ":",
                _u2(minute),
                ":",
                _u2(second),
                " ",
                sign,
                _u2(zh),
                _u2(zm)
            );
        }
        _checkAgainstNode(cases, cases.length);
    }

    // ===========================================================================
    // Helpers
    // ===========================================================================

    function _assertField(bytes memory header, string memory name, string memory expected) internal pure {
        (bytes memory value, bool found) = HeaderParser.field(header, bytes(name));
        assertTrue(found, string.concat("field not found: ", name));
        assertEq(string(value), expected, string.concat("wrong value for: ", name));
    }

    function _assertDate(string memory value, uint256 expected) internal pure {
        (uint256 ts, bool ok) = HeaderParser.parseRfc2822Date(bytes(value));
        assertTrue(ok, string.concat("failed to parse: ", value));
        assertEq(ts, expected, string.concat("wrong timestamp for: ", value));
    }

    function _assertDateInvalid(string memory value) internal pure {
        (uint256 ts, bool ok) = HeaderParser.parseRfc2822Date(bytes(value));
        assertFalse(ok, string.concat("should not have parsed: ", value));
        assertEq(ts, 0, "a rejected date must report zero");
    }

    function _contains(bytes memory haystack, bytes memory needle) internal pure returns (bool) {
        if (needle.length == 0 || needle.length > haystack.length) return false;
        for (uint256 i = 0; i + needle.length <= haystack.length; ++i) {
            bool hit = true;
            for (uint256 j = 0; j < needle.length; ++j) {
                if (haystack[i + j] != needle[j]) {
                    hit = false;
                    break;
                }
            }
            if (hit) return true;
        }
        return false;
    }

    /// @dev The oracle: V8's own calendar arithmetic. For each case it recomputes the
    /// instant with `Date.UTC` and requires every component to round-trip (which is what
    /// makes it strict about 31 Apr, 29 Feb 2023, hour 24, ...). Invalid or pre-epoch
    /// cases come back as 0xffffffffffffffff; everything else as an 8-byte timestamp.
    function _checkAgainstNode(string[] memory cases, uint256 n) internal {
        string memory payload = cases[0];
        for (uint256 i = 1; i < n; ++i) {
            payload = string.concat(payload, "|", cases[i]);
        }

        string[] memory cmd = new string[](4);
        cmd[0] = "node";
        cmd[1] = "-e";
        cmd[2] = "const M='janfebmaraprmayjunjulaugsepoctnovdec';let o='0x';"
            "for(const s of process.argv[1].split('|')){"
            "const p=s.trim().split(' ').filter(Boolean);const q=p.slice(p.length-5);"
            "const d=Number(q[0]),mo=M.indexOf(q[1].toLowerCase())/3+1,y=Number(q[2]);"
            "const t=q[3].split(':').map(Number);const z=q[4];let off=0,bad=false;"
            "if(z[0]==='+'||z[0]==='-'){const zh=Number(z.slice(1,3)),zm=Number(z.slice(3,5));"
            "if(zh>23||zm>59)bad=true;off=(zh*3600+zm*60)*(z[0]==='-'?-1:1);}"
            "const ms=Date.UTC(y,mo-1,d,t[0],t[1],t[2]||0);const c=new Date(ms);"
            "if(c.getUTCFullYear()!==y||c.getUTCMonth()!==mo-1||c.getUTCDate()!==d"
            "||c.getUTCHours()!==t[0]||c.getUTCMinutes()!==t[1]||c.getUTCSeconds()!==(t[2]||0))bad=true;"
            "const v=Math.floor(ms/1000)-off;"
            "o+=(bad||!Number.isFinite(v)||v<0)?'ffffffffffffffff':v.toString(16).padStart(16,'0');}"
            "process.stdout.write(o);";
        cmd[3] = payload;

        bytes memory out = vm.ffi(cmd);
        assertEq(out.length, n * 8, "oracle returned the wrong number of results");

        uint256 rejected;
        for (uint256 i = 0; i < n; ++i) {
            uint256 expected;
            for (uint256 j = 0; j < 8; ++j) {
                expected = (expected << 8) | uint8(out[i * 8 + j]);
            }
            (uint256 ts, bool ok) = HeaderParser.parseRfc2822Date(bytes(cases[i]));
            if (expected == type(uint64).max) {
                ++rejected;
                assertFalse(ok, string.concat("Node rejects but we accepted: ", cases[i]));
            } else {
                assertTrue(ok, string.concat("Node accepts but we rejected: ", cases[i]));
                assertEq(ts, expected, string.concat("timestamp mismatch for: ", cases[i]));
            }
        }
        // Sanity: the corpus must exercise both outcomes, or the comparison proves little.
        assertGt(rejected, 0, "corpus contained no invalid dates");
        assertLt(rejected, n, "corpus contained no valid dates");
    }

    function _u2(uint256 v) internal pure returns (string memory) {
        bytes memory b = new bytes(2);
        b[0] = bytes1(uint8(48 + (v / 10) % 10));
        b[1] = bytes1(uint8(48 + v % 10));
        return string(b);
    }

    function _u4(uint256 v) internal pure returns (string memory) {
        bytes memory b = new bytes(4);
        b[0] = bytes1(uint8(48 + (v / 1000) % 10));
        b[1] = bytes1(uint8(48 + (v / 100) % 10));
        b[2] = bytes1(uint8(48 + (v / 10) % 10));
        b[3] = bytes1(uint8(48 + v % 10));
        return string(b);
    }

    function _monthName(uint256 m) internal pure returns (string memory) {
        return _triplet("JanFebMarAprMayJunJulAugSepOctNovDec", m - 1);
    }

    function _dayName(uint256 d) internal pure returns (string memory) {
        return _triplet("MonTueWedThuFriSatSun", d);
    }

    function _triplet(bytes memory table, uint256 index) internal pure returns (string memory) {
        bytes memory out = new bytes(3);
        out[0] = table[index * 3];
        out[1] = table[index * 3 + 1];
        out[2] = table[index * 3 + 2];
        return string(out);
    }
}
