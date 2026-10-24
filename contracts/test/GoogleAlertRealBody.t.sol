// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {GoogleAlertBodyParser} from "../src/lib/GoogleAlertBodyParser.sol";

contract GoogleAlertRealBodyHarness {
    function verify(bytes memory header, bytes calldata body, uint256 start, uint256 length, string calldata excerpt)
        external
        pure
        returns (bool)
    {
        return GoogleAlertBodyParser.verify(header, body, start, length, excerpt);
    }
}

/// @notice Private genuine Google Alerts bytes, pinned by an immutable fixture SHA.
/// @dev Requires LAYA_GOOGLE_ALERT_MIME_FIXTURE explicitly; absent means SKIP.
/// No private email bytes are in this source. This suite checks the pure parser,
/// not RSA, signer provenance, article extraction, model input, truth or verdicts.
contract GoogleAlertRealBodyTest is Test {
    bytes32 private constant FIXTURE_SHA256 = 0xa2f14b64a38d04925c037c7595a16f4839f0b658d7e6345316c69304a2617816;
    bytes32 private constant RAW_SHA256 = 0x2d75c4968d136851825b44689fb7beddb270d36a148f3070e435236d05cc8f41;
    bytes32 private constant BODY_SHA256 = 0x67b73056b8dbf54e2f8d20fe0fcba89413e3a7f1d93cef33d43dbbb0abef6676;
    GoogleAlertRealBodyHarness private parser;
    bytes private header;
    bytes private body;
    bytes private decoded;
    bytes private wholeRowDecoded;
    uint256 private offset;
    uint256 private length;
    uint256 private wholeRowLength;

    function setUp() public {
        string memory path = vm.envOr("LAYA_GOOGLE_ALERT_MIME_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "LAYA_GOOGLE_ALERT_MIME_FIXTURE absent; genuine MIME suite not run");
            return;
        }
        // Foundry trims textual FFI stdout. Hex transport preserves the fixture's
        // final newline so this is the SHA of the exact private file bytes.
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys\nprint('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory fixtureBytes = vm.ffi(command);
        assertEq(sha256(fixtureBytes), FIXTURE_SHA256, "fixture content drift");
        string memory fixture = string(fixtureBytes);
        assertEq(vm.parseJsonBytes32(fixture, ".rawSha256"), RAW_SHA256, "wrong original mail");
        assertEq(vm.parseJsonBytes32(fixture, ".canonicalBodySha256"), BODY_SHA256);
        assertEq(vm.parseJsonUint(fixture, ".resultIndex"), 3);
        assertEq(vm.parseJsonUint(fixture, ".parserVersion"), 2);
        assertTrue(vm.parseJsonBool(fixture, ".signedBhVerifiedLocally"));
        assertTrue(vm.parseJsonBool(fixture, ".allFourFieldsIncluded"));
        assertFalse(vm.parseJsonBool(fixture, ".wholeRowFitsWindow"));
        assertFalse(vm.parseJsonBool(fixture, ".rsaVerifiedNow"));
        assertFalse(vm.parseJsonBool(fixture, ".networkUsed"));
        assertEq(vm.parseJsonUint(fixture, ".actualSignedContentTypeFields"), 1);
        assertEq(vm.parseJsonUint(fixture, ".signedListContentTypeOccurrences"), 2);
        header = vm.parseJsonBytes(fixture, ".headerHex");
        body = vm.parseJsonBytes(fixture, ".bodyHex");
        decoded = vm.parseJsonBytes(fixture, ".decodedHex");
        wholeRowDecoded = vm.parseJsonBytes(fixture, ".wholeRowDecodedHex");
        offset = vm.parseJsonUint(fixture, ".bodyOffset");
        length = vm.parseJsonUint(fixture, ".encodedLength");
        wholeRowLength = vm.parseJsonUint(fixture, ".wholeRowEncodedLength");
        assertEq(sha256(body), BODY_SHA256);
        assertEq(sha256(header), vm.parseJsonBytes32(fixture, ".canonicalHeaderSha256"));
        assertEq(body.length, 154339);
        assertEq(offset, 39529);
        assertEq(length, 3398);
        assertEq(decoded.length, 3172);
        parser = new GoogleAlertRealBodyHarness();
    }

    function test_RealCanonicalBodyAndExactFourFieldHtmlPrefix() public {
        uint256 before = gasleft();
        assertTrue(parser.verify(header, body, offset, length, string(decoded)));
        emit log_named_uint("genuine full-body MIME parser gas", before - gasleft());
        emit log_named_uint("encoded four-field prefix bytes", length);
        emit log_named_uint("complete Article row encoded bytes exceeds bound", wholeRowLength);
    }

    function test_RealBodyTamperOutsideAndInsideWindowRejected() public view {
        bytes memory altered = body;
        altered[0] ^= 0x01;
        assertFalse(parser.verify(header, altered, offset, length, string(decoded)));
        altered = body;
        altered[offset + 10] ^= 0x01;
        assertFalse(parser.verify(header, altered, offset, length, string(decoded)));
    }

    function test_RealSignedBoundaryHeaderTamperRejected() public view {
        bytes memory altered = header;
        uint256 at = find(altered, bytes('boundary="'), 0) + bytes('boundary="').length;
        altered[at] = "X";
        assertFalse(parser.verify(altered, body, offset, length, string(decoded)));
    }

    function test_RealContentTypeRemovedFromSignedListRejected() public view {
        bytes memory altered = header;
        uint256 start = find(altered, "h=", 0) + 2;
        uint256 end = start;
        while (end < altered.length && altered[end] != ";") ++end;
        uint256 count;
        while (start < end) {
            uint256 at = find(altered, "content-type", start);
            if (at >= end) break;
            altered[at] = "x";
            ++count;
            start = at + 12;
        }
        assertEq(count, 2, "real signature oversigning count");
        assertFalse(parser.verify(altered, body, offset, length, string(decoded)));
    }

    function test_RealExcerptAndOffsetTamperRejected() public view {
        bytes memory altered = decoded;
        altered[0] ^= 0x01;
        assertFalse(parser.verify(header, body, offset, length, string(altered)));
        assertFalse(parser.verify(header, body, offset + 1, length, string(decoded)));
        assertFalse(parser.verify(header, body, offset, length - 1, string(decoded)));
        assertFalse(parser.verify(header, body, type(uint256).max, length, string(decoded)));
    }

    function test_CompleteRealArticleRowExceedsWindowAndIsRejected() public view {
        assertEq(wholeRowLength, 5172);
        assertEq(wholeRowDecoded.length, 4796);
        assertGt(wholeRowLength, 4096);
        assertFalse(parser.verify(header, body, offset, wholeRowLength, string(wholeRowDecoded)));
    }

    function find(bytes memory haystack, bytes memory needle, uint256 start) private pure returns (uint256) {
        if (needle.length > haystack.length) return type(uint256).max;
        for (uint256 i = start; i <= haystack.length - needle.length; ++i) {
            bool hit = true;
            for (uint256 j; j < needle.length; ++j) {
                if (haystack[i + j] != needle[j]) {
                    hit = false;
                    break;
                }
            }
            if (hit) return i;
        }
        return type(uint256).max;
    }
}
