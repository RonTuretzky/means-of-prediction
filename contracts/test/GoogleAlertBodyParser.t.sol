// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {GoogleAlertBodyParser} from "../src/lib/GoogleAlertBodyParser.sol";

contract GoogleAlertBodyParserHarness {
    function verify(bytes memory header, bytes calldata body, uint256 start, uint256 length, string calldata excerpt)
        external
        pure
        returns (bool)
    {
        return GoogleAlertBodyParser.verify(header, body, start, length, excerpt);
    }
}

/// @dev Independently constructed synthetic MIME and bh= values; no RSA signatures
/// or genuine-email claims. Structural attacks are rehashed so the body-hash gate
/// cannot hide a MIME parser failure. The parser witnesses HTML bytes, not articles.
contract GoogleAlertBodyParserTest is Test {
    GoogleAlertBodyParserHarness internal parser = new GoogleAlertBodyParserHarness();
    string internal constant CT = 'multipart/alternative; boundary="CaseSensitive42"';
    string internal constant PLAIN_HEADERS =
        'Content-Type: text/plain; charset="UTF-8"; format=flowed; delsp=yes\r\nContent-Transfer-Encoding: base64\r\n\r\n';
    string internal constant HTML_HEADERS =
        'Content-Type: text/html; charset="UTF-8"\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n';
    string internal constant HTML = "<p>Rates =3C 5%=20today=\r\n.</p>";
    string internal constant DECODED = "<p>Rates < 5% today.</p>";

    function header(bytes memory body, string memory ct, string memory tags) internal pure returns (bytes memory) {
        return bytes.concat(
            bytes(
                string.concat(
                    "from:Google Alerts <googlealerts-noreply@google.com>\r\ncontent-type:",
                    ct,
                    "\r\ndkim-signature:v=1; a=rsa-sha256; c=relaxed/relaxed; h=from:content-type; bh="
                )
            ),
            bytes(vm.toBase64(abi.encodePacked(sha256(body)))),
            bytes(string.concat(tags, "; b="))
        );
    }

    function mime(
        string memory boundary,
        string memory plainHeaders,
        string memory plain,
        string memory htmlHeaders,
        string memory html
    ) internal pure returns (bytes memory body, uint256 offset) {
        bytes memory prefix = bytes(
            string.concat("--", boundary, "\r\n", plainHeaders, plain, "\r\n--", boundary, "\r\n", htmlHeaders)
        );
        offset = prefix.length;
        body = bytes.concat(prefix, bytes(html), bytes(string.concat("\r\n--", boundary, "--\r\n")));
    }

    function fixture() internal pure returns (bytes memory body, uint256 offset) {
        return mime("CaseSensitive42", PLAIN_HEADERS, "cGxhaW4=", HTML_HEADERS, HTML);
    }

    function valid(bytes memory body, uint256 offset) internal view returns (bool) {
        return parser.verify(header(body, CT, ""), body, offset, bytes(HTML).length, DECODED);
    }

    function rejectedMime(string memory plainHeaders, string memory plain, string memory htmlHeaders) internal view {
        (bytes memory body, uint256 offset) = mime("CaseSensitive42", plainHeaders, plain, htmlHeaders, "safe");
        assertFalse(parser.verify(header(body, CT, ""), body, offset, 4, "safe"));
    }

    function test_RealShapedFullBodyHashAndHtmlQuotedPrintableWindow() public view {
        (bytes memory body, uint256 offset) = fixture();
        assertTrue(valid(body, offset));
        assertTrue(parser.verify(header(body, CT, ""), body, offset + 3, 5, "Rates"));
    }

    function test_MimeCaseInsensitiveButBoundaryCaseSensitive() public view {
        (bytes memory body, uint256 offset) = fixture();
        assertTrue(
            parser.verify(
                header(body, 'Multipart/Alternative; BOUNDARY="CaseSensitive42"', ""),
                body,
                offset,
                bytes(HTML).length,
                DECODED
            )
        );
        assertFalse(
            parser.verify(
                header(body, 'multipart/alternative; boundary="casesensitive42"', ""),
                body,
                offset,
                bytes(HTML).length,
                DECODED
            )
        );
        assertTrue(
            parser.verify(
                header(body, "multipart/alternative; boundary=CaseSensitive42", ""),
                body,
                offset,
                bytes(HTML).length,
                DECODED
            )
        );
    }

    function test_QuotedBoundaryPunctuationAndSpace() public view {
        (bytes memory body, uint256 offset) = mime("A:b=c (42)", PLAIN_HEADERS, "cGxhaW4=", HTML_HEADERS, HTML);
        assertTrue(
            parser.verify(
                header(body, 'multipart/alternative; boundary="A:b=c (42)"', ""),
                body,
                offset,
                bytes(HTML).length,
                DECODED
            )
        );
        assertFalse(
            parser.verify(
                header(body, "multipart/alternative; boundary=A:b=c (42)", ""),
                body,
                offset,
                bytes(HTML).length,
                DECODED
            )
        );
    }

    function test_QuotedBoundaryMalformedEscapedOrAmbiguousRejected() public view {
        (bytes memory body, uint256 offset) = fixture();
        string[8] memory bad = [
            'multipart/alternative; boundary="CaseSensitive42',
            'multipart/alternative; boundary="CaseSensitive42"junk',
            'multipart/alternative; boundary="CaseSensitive42;ignored"',
            'multipart/alternative; boundary="CaseSensitive42\\""',
            'multipart/alternative; boundary="CaseSensitive42 "',
            'multipart/alternative; boundary=""',
            "multipart/alternative; boundary=CaseSensitive42;",
            'multipart/alternative; boundary="CaseSensitive42"; x="boundary=evil"'
        ];
        for (uint256 i; i < bad.length; ++i) {
            assertFalse(parser.verify(header(body, bad[i], ""), body, offset, bytes(HTML).length, DECODED));
        }
    }

    function test_MissingDuplicateAndWrongMultipartBoundaryRejected() public view {
        (bytes memory body, uint256 offset) = fixture();
        string[4] memory bad = [
            "multipart/alternative",
            "multipart/alternative; boundary=CaseSensitive42; boundary=CaseSensitive42",
            "multipart/alternative; boundary=CaseSensitive42; BOUNDARY=evil",
            "multipart/mixed; boundary=CaseSensitive42"
        ];
        for (uint256 i; i < bad.length; ++i) {
            assertFalse(parser.verify(header(body, bad[i], ""), body, offset, bytes(HTML).length, DECODED));
        }
    }

    function test_ContentTypeMustBeUniqueAndExplicitlySigned() public view {
        (bytes memory body, uint256 offset) = fixture();
        bytes memory h = header(body, CT, "");
        assertFalse(
            parser.verify(
                bytes.concat("content-type:", bytes(CT), "\r\n", h), body, offset, bytes(HTML).length, DECODED
            )
        );
        assertFalse(
            parser.verify(
                bytes.concat("Content-Type:", bytes(CT), "\r\n", h), body, offset, bytes(HTML).length, DECODED
            )
        );
        h = bytes.concat(
            "content-type:",
            bytes(CT),
            "\r\ndkim-signature:c=relaxed/relaxed; h=from:subject; bh=",
            bytes(vm.toBase64(abi.encodePacked(sha256(body))))
        );
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
        h = bytes.concat(
            "dkim-signature:c=relaxed/relaxed; h=from:content-type; bh=",
            bytes(vm.toBase64(abi.encodePacked(sha256(body))))
        );
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
    }

    function test_DuplicateSignatureCanonicalizationHashAndFieldListTagsRejected() public view {
        (bytes memory body, uint256 offset) = fixture();
        bytes memory h = header(body, CT, "");
        assertFalse(
            parser.verify(
                bytes.concat(h, "\r\ndkim-signature:c=relaxed/relaxed"), body, offset, bytes(HTML).length, DECODED
            )
        );
        assertFalse(parser.verify(header(body, CT, "; c=relaxed/relaxed"), body, offset, bytes(HTML).length, DECODED));
        assertFalse(parser.verify(header(body, CT, "; h=content-type"), body, offset, bytes(HTML).length, DECODED));
        assertFalse(
            parser.verify(
                header(body, CT, "; bh=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="),
                body,
                offset,
                bytes(HTML).length,
                DECODED
            )
        );
        h = bytes.concat(
            "content-type:",
            bytes(CT),
            "\r\ndkim-signature:c=relaxed/relaxed; h=from:date:content-type:content-type:from:date:subject; bh=",
            bytes(vm.toBase64(abi.encodePacked(sha256(body))))
        );
        assertTrue(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
        assertFalse(
            parser.verify(
                bytes.concat("content-type:", bytes(CT), "\r\n", h), body, offset, bytes(HTML).length, DECODED
            )
        );
    }

    function test_PartialBodyHashAndEveryLengthTagRejected() public view {
        (bytes memory body, uint256 offset) = fixture();
        assertFalse(parser.verify(header(body, CT, "; l=7"), body, offset, bytes(HTML).length, DECODED));
        assertFalse(parser.verify(header(body, CT, "; l="), body, offset, bytes(HTML).length, DECODED));
        assertFalse(parser.verify(header(body, CT, "; l=7; l=7"), body, offset, bytes(HTML).length, DECODED));
        bytes memory partialHeader = bytes.concat(
            "content-type:",
            bytes(CT),
            "\r\ndkim-signature:c=relaxed/relaxed; h=content-type; bh=",
            bytes(vm.toBase64(abi.encodePacked(sha256(bytes("partial body")))))
        );
        assertFalse(parser.verify(partialHeader, body, offset, bytes(HTML).length, DECODED));
    }

    function test_MissingUnsupportedOrDuplicateCanonicalizationRejected() public view {
        (bytes memory body, uint256 offset) = fixture();
        string[3] memory modes = ["simple/relaxed", "simple/simple", "relaxed"];
        bytes memory tail = bytes.concat("; h=content-type; bh=", bytes(vm.toBase64(abi.encodePacked(sha256(body)))));
        for (uint256 i; i < modes.length; ++i) {
            bytes memory h = bytes.concat("content-type:", bytes(CT), "\r\ndkim-signature:c=", bytes(modes[i]), tail);
            assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
        }
        bytes memory h = bytes.concat("content-type:", bytes(CT), "\r\ndkim-signature:", tail);
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
        h = bytes.concat("content-type:", bytes(CT), "\r\ndkim-signature:c=relaxed/simple", tail);
        assertTrue(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
    }

    function test_TamperPlainPartOrHtmlPartAndUnsignedAppendRejected() public view {
        (bytes memory body, uint256 offset) = fixture();
        bytes memory h = header(body, CT, "");
        body[bytes(string.concat("--CaseSensitive42\r\n", PLAIN_HEADERS)).length] = "d";
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
        (body, offset) = fixture();
        body[offset + 4] = "X";
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
        (body, offset) = fixture();
        body = bytes.concat(body, "unsigned article\r\n");
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, DECODED));
    }

    function test_PreambleEpilogueAndTrailingEmptyLineRejectedAfterRehash() public view {
        (bytes memory body, uint256 offset) = fixture();
        assertFalse(valid(bytes.concat("preamble\r\n", body), offset + 10));
        assertFalse(valid(bytes.concat(body, "epilogue\r\n"), offset));
        assertFalse(valid(bytes.concat(body, "\r\n"), offset));
    }

    function test_ExtraPartMalformedDelimiterAndMissingCloseRejectedAfterRehash() public view {
        (bytes memory body, uint256 offset) = mime(
            "CaseSensitive42",
            PLAIN_HEADERS,
            "cGxhaW4=",
            HTML_HEADERS,
            string.concat(HTML, "\r\n--CaseSensitive42\r\n", HTML_HEADERS, HTML)
        );
        assertFalse(valid(body, offset));
        (body, offset) = mime(
            "CaseSensitive42",
            PLAIN_HEADERS,
            "cGxhaW4=",
            HTML_HEADERS,
            string.concat(HTML, "\r\n--CaseSensitive42 trailing junk\r\n")
        );
        assertFalse(valid(body, offset));
        (body, offset) = fixture();
        body[body.length - 4] = "x";
        assertFalse(valid(body, offset));
    }

    function test_NestedMimeAndWrongPartOrderRejected() public view {
        rejectedMime(HTML_HEADERS, "cGxhaW4=", HTML_HEADERS);
        rejectedMime(PLAIN_HEADERS, "cGxhaW4=", PLAIN_HEADERS);
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: multipart/mixed; boundary=inner\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
        );
    }

    function test_DuplicatePartHeadersAndCharsetParametersRejected() public view {
        rejectedMime(
            PLAIN_HEADERS, "cGxhaW4=", string.concat("Content-Type: text/html; charset=utf-8\r\n", HTML_HEADERS)
        );
        rejectedMime(
            PLAIN_HEADERS, "cGxhaW4=", string.concat("CONTENT-TRANSFER-ENCODING: quoted-printable\r\n", HTML_HEADERS)
        );
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: text/html; charset=utf-8; CHARSET=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
        );
    }

    function test_UnsupportedCteCharsetAndPartHeadersRejected() public view {
        rejectedMime(PLAIN_HEADERS, "cGxhaW4=", string.concat("X-Other: value\r\n", HTML_HEADERS));
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
        );
        rejectedMime(
            "Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: 7bit\r\n\r\n",
            "cGxhaW4=",
            HTML_HEADERS
        );
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: text/html; charset=iso-8859-1\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
        );
    }

    function test_FoldedBareLfAndMissingPartHeadersRejected() public view {
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: text/html;\r\n charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
        );
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: text/html; charset=utf-8\nContent-Transfer-Encoding: quoted-printable\n\n"
        );
        rejectedMime(PLAIN_HEADERS, "cGxhaW4=", "Content-Type: text/html; charset=utf-8\r\n\r\n");
        rejectedMime(
            PLAIN_HEADERS,
            "cGxhaW4=",
            "Content-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n"
        );
    }

    function test_MalformedBase64RejectedAfterRehash() public view {
        string[6] memory bad = ["not base64", "cGxhaW4", "cGxhaW4===", "cGx=haW4", "cGxhaW5=", "QQ==="];
        for (uint256 i; i < bad.length; ++i) {
            rejectedMime(PLAIN_HEADERS, bad[i], HTML_HEADERS);
        }
    }

    function test_MalformedQpOutsideSelectedWindowRejectedAfterRehash() public view {
        (bytes memory body, uint256 offset) =
            mime("CaseSensitive42", PLAIN_HEADERS, "cGxhaW4=", HTML_HEADERS, "valid=GZ");
        assertFalse(parser.verify(header(body, CT, ""), body, offset, 5, "valid"));
        (body, offset) = mime("CaseSensitive42", PLAIN_HEADERS, "cGxhaW4=", HTML_HEADERS, "valid=");
        assertFalse(parser.verify(header(body, CT, ""), body, offset, 5, "valid"));
    }

    function test_WindowOnlyInsideHtmlPayloadAndNeverAcrossBoundary() public view {
        (bytes memory body, uint256 offset) = fixture();
        bytes memory h = header(body, CT, "");
        uint256 plainOffset = bytes(string.concat("--CaseSensitive42\r\n", PLAIN_HEADERS)).length;
        assertFalse(parser.verify(h, body, plainOffset, 8, "cGxhaW4="));
        assertFalse(parser.verify(h, body, offset - 5, 5, "ble\r\n"));
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length + 2, string.concat(DECODED, "\r\n")));
        assertFalse(parser.verify(h, body, offset + bytes(HTML).length, 21, "\r\n--CaseSensitive42--\r\n"));
        assertFalse(parser.verify(h, body, offset, bytes(HTML).length, "Rates are lower"));
        assertFalse(parser.verify(h, body, type(uint256).max, 1, "x"));
        assertFalse(parser.verify(h, body, offset, type(uint256).max, "x"));
        assertFalse(parser.verify(h, body, offset, 0, ""));
    }

    function test_WindowCannotSplitEscapesOrSoftBreaks() public view {
        (bytes memory body, uint256 offset) =
            mime("CaseSensitive42", PLAIN_HEADERS, "cGxhaW4=", HTML_HEADERS, "a=20b=\r\nc");
        bytes memory h = header(body, CT, "");
        assertTrue(parser.verify(h, body, offset, 9, "a bc"));
        assertFalse(parser.verify(h, body, offset + 2, 1, "2"));
        assertFalse(parser.verify(h, body, offset + 3, 1, "0"));
        assertFalse(parser.verify(h, body, offset + 6, 2, "\r\n"));
        assertFalse(parser.verify(h, body, offset, 3, "a=2"));
    }

    function test_WindowBound4096AndBodyBound196608() public view {
        bytes memory html = new bytes(4097);
        for (uint256 i; i < html.length; ++i) {
            html[i] = "x";
        }
        (bytes memory body, uint256 offset) =
            mime("CaseSensitive42", PLAIN_HEADERS, "cGxhaW4=", HTML_HEADERS, string(html));
        bytes memory h = header(body, CT, "");
        bytes memory excerpt = new bytes(4096);
        for (uint256 i; i < excerpt.length; ++i) {
            excerpt[i] = "x";
        }
        assertTrue(parser.verify(h, body, offset, 4096, string(excerpt)));
        assertFalse(parser.verify(h, body, offset, 4097, string(html)));
        assertFalse(parser.verify(h, new bytes(196609), 0, 1, "x"));
    }

    function testFuzz_ArbitraryBodyFailClosedWithoutReverting(bytes memory body, uint256 start, uint256 length)
        public
        view
    {
        assertFalse(parser.verify(header(body, CT, ""), body, start, length, "not an authenticated article"));
    }

    function testFuzz_ArbitraryHeaderDoesNotRevert(bytes memory h, uint256 start, uint256 length) public view {
        (bytes memory body,) = fixture();
        assertFalse(parser.verify(h, body, start, length, "not an authenticated article"));
    }
}
