// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {RSAVerify} from "../src/dkim/RSAVerify.sol";

/// @notice Proves the onchain RSA-SHA256 verification (modexp precompile) accepts a
/// REAL RSA signature made by the committed dev key and rejects tampering — the same
/// operation used to check a DKIM signature.
contract RSAVerifyTest is Test {
    bytes modulus;
    bytes exponent;

    function setUp() public {
        (modulus, exponent) = devPubKey();
    }

    function sign(bytes memory message) internal returns (bytes memory) {
        string[] memory cmd = new string[](3);
        cmd[0] = "node";
        cmd[1] = "test/helpers/rsa-sign.mjs";
        cmd[2] = vm.toString(message);
        return vm.ffi(cmd);
    }

    function devPubKey() internal returns (bytes memory mod, bytes memory exp) {
        mod = ffiPub("--pub-n");
        exp = ffiPub("--pub-e");
    }

    function ffiPub(string memory which) internal returns (bytes memory) {
        string[] memory cmd = new string[](3);
        cmd[0] = "node";
        cmd[1] = "test/helpers/rsa-sign.mjs";
        cmd[2] = which;
        return vm.ffi(cmd);
    }

    function test_VerifiesRealSignature() public {
        bytes memory message = bytes("from:nyt <nytdirect@nytimes.com>\r\nsubject:Fed cuts rates");
        bytes memory sig = sign(message);
        assertEq(modulus.length, 256); // 2048-bit dev key
        assertTrue(RSAVerify.pkcs1Sha256(sha256(message), sig, exponent, modulus));
    }

    function test_RejectsWrongMessage() public {
        bytes memory sig = sign(bytes("the signed message"));
        assertFalse(RSAVerify.pkcs1Sha256(sha256(bytes("a different message")), sig, exponent, modulus));
    }

    function test_RejectsTamperedSignature() public {
        bytes memory message = bytes("authentic content");
        bytes memory sig = sign(message);
        sig[100] = bytes1(uint8(sig[100]) ^ 0x01); // flip a bit
        assertFalse(RSAVerify.pkcs1Sha256(sha256(message), sig, exponent, modulus));
    }

    function test_RejectsWrongLengthSignature() public view {
        bytes memory sig = new bytes(255);
        assertFalse(RSAVerify.pkcs1Sha256(sha256(bytes("x")), sig, exponent, modulus));
    }
}
