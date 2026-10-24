// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {GoogleAlertBodyParser} from "../src/lib/GoogleAlertBodyParser.sol";

contract NobelAlertBodyHarness {
    function verify(bytes memory header, bytes calldata body, uint256 start, uint256 length, string calldata excerpt)
        external
        pure
        returns (bool)
    {
        return GoogleAlertBodyParser.verify(header, body, start, length, excerpt);
    }
}

/// @notice Genuine, privately stored Nobel evidence under the unchanged parser v2.
/// @dev Pure full-body/MIME binding only: no Solidity RSA, source-policy, model,
/// certificate or settlement claim. Cached-key DKIM replay is a separate artifact.
contract NobelAlertRealBodyTest is Test {
    bytes32 private constant FIXTURE_SHA256 = 0x521e6317c29b3a2610fd0c83e6cf6ea3929524ae63a4663e1944287cd29886ae;
    NobelAlertBodyHarness private parser;
    bytes private bbcHeader;
    bytes private bbcBody;
    bytes private bbcDecoded;
    bytes private committeeHeader;
    bytes private committeeBody;
    bytes private committeeDecoded;

    function setUp() public {
        string memory path = vm.envOr("LAYA_NOBEL_MIME_FIXTURE", string(""));
        if (bytes(path).length == 0) {
            vm.skip(true, "LAYA_NOBEL_MIME_FIXTURE absent; genuine Nobel suite not run");
            return;
        }
        string[] memory command = new string[](4);
        command[0] = "python3";
        command[1] = "-c";
        command[2] = "import pathlib,sys\nprint('0x'+pathlib.Path(sys.argv[1]).read_bytes().hex())";
        command[3] = path;
        bytes memory rawFixture = vm.ffi(command);
        assertEq(sha256(rawFixture), FIXTURE_SHA256);
        string memory fixture = string(rawFixture);
        bbcHeader = vm.parseJsonBytes(fixture, ".sources.bbc.headerHex");
        bbcBody = vm.parseJsonBytes(fixture, ".sources.bbc.bodyHex");
        bbcDecoded = vm.parseJsonBytes(fixture, ".sources.bbc.decodedHex");
        committeeHeader = vm.parseJsonBytes(fixture, ".sources.committee.headerHex");
        committeeBody = vm.parseJsonBytes(fixture, ".sources.committee.bodyHex");
        committeeDecoded = vm.parseJsonBytes(fixture, ".sources.committee.decodedHex");
        assertEq(sha256(bbcBody), 0xef09cd6700414ff97c243c6c7b564b457c19db3efdc26a0e84033bd033e939b4);
        assertEq(sha256(committeeBody), 0xf4c2a011a2fecf1d497b65b7edaf5fb6fe56a13e30d2810cf0e931120fdc03b1);
        assertEq(bbcBody.length, 20461);
        assertEq(committeeBody.length, 239824);
        assertEq(vm.parseJsonUint(fixture, ".sources.bbc.bodyOffset"), 8078);
        assertEq(vm.parseJsonUint(fixture, ".sources.bbc.encodedLength"), 1265);
        assertEq(vm.parseJsonUint(fixture, ".sources.committee.bodyOffset"), 38663);
        assertEq(vm.parseJsonUint(fixture, ".sources.committee.encodedLength"), 1340);
        assertTrue(vm.parseJsonBool(fixture, ".sources.bbc.allFourFieldsIncluded"));
        assertTrue(vm.parseJsonBool(fixture, ".sources.committee.allFourFieldsIncluded"));
        assertTrue(vm.parseJsonBool(fixture, ".sources.bbc.withinCurrentParserV2"));
        assertFalse(vm.parseJsonBool(fixture, ".sources.committee.withinCurrentParserV2"));
        parser = new NobelAlertBodyHarness();
    }

    function test_NobelBBCCompleteBodyAndOriginalFourFieldWindow() public {
        uint256 before = gasleft();
        assertTrue(parser.verify(bbcHeader, bbcBody, 8078, 1265, string(bbcDecoded)));
        emit log_named_uint("genuine Nobel BBC full-body MIME parser gas", before - gasleft());
    }

    function test_NobelMutationOutsideSelectedWindowFails() public view {
        bytes memory changed = bbcBody;
        changed[changed.length - 8] ^= 0x01;
        assertFalse(parser.verify(bbcHeader, changed, 8078, 1265, string(bbcDecoded)));
    }

    function test_NobelWrongExcerptOrOffsetFails() public view {
        bytes memory changed = bbcDecoded;
        changed[0] ^= 0x01;
        assertFalse(parser.verify(bbcHeader, bbcBody, 8078, 1265, string(changed)));
        assertFalse(parser.verify(bbcHeader, bbcBody, 8079, 1265, string(bbcDecoded)));
    }

    function test_GenuineOversizedCommitteeBodyIsRejectedByUnchangedV2() public view {
        assertGt(committeeBody.length, 196608);
        assertFalse(parser.verify(committeeHeader, committeeBody, 38663, 1340, string(committeeDecoded)));
    }

    function test_CroppingCommitteeBodyCannotTurnItIntoAValidProof() public view {
        bytes memory cropped = committeeBody;
        // Test an adversarial prefix without modifying the retained original.
        assembly ("memory-safe") {
            mstore(cropped, 196608)
        }
        assertEq(cropped.length, 196608);
        assertTrue(sha256(cropped) != sha256(committeeBody));
        assertFalse(parser.verify(committeeHeader, cropped, 38663, 1340, string(committeeDecoded)));
    }
}
