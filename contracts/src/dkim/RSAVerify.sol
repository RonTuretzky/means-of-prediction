// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title RSAVerify
/// @notice Real RSASSA-PKCS1-v1_5 signature verification with SHA-256, using the
/// EVM's modexp precompile (address 0x05). This is genuine RSA verification — the
/// same operation an email server performs to check a DKIM signature — not a mock.
///
/// A signature `s` over message digest `d` (32-byte SHA-256) verifies iff
/// `s^e mod n` equals the EMSA-PKCS1-v1_5 encoding of `d` for the modulus length:
///
///   0x00 0x01  0xFF … 0xFF  0x00  <DigestInfo>       (DigestInfo = SHA-256 DER prefix ++ d)
///
/// Works for any modulus length (2048, 4096, …) — NYT signs with RSA-4096.
library RSAVerify {
    /// SHA-256 DigestInfo DER prefix (RFC 8017 §9.2): the 19 bytes preceding the hash.
    bytes internal constant SHA256_PREFIX = hex"3031300d060960864801650304020105000420";

    /// @param digest  SHA-256 of the signed message
    /// @param signature  RSA signature `s` (big-endian, length == modulus length)
    /// @param exponent  public exponent `e` (big-endian, e.g. 0x010001)
    /// @param modulus  public modulus `n` (big-endian)
    function pkcs1Sha256(bytes32 digest, bytes memory signature, bytes memory exponent, bytes memory modulus)
        internal
        view
        returns (bool)
    {
        uint256 k = modulus.length;
        if (signature.length != k) return false;
        // 0x00 01 || PS(>=8 of 0xFF) || 00 || prefix(19) || digest(32)
        if (k < SHA256_PREFIX.length + 32 + 11) return false;

        (bool ok, bytes memory decrypted) = modExp(signature, exponent, modulus);
        if (!ok || decrypted.length != k) return false;

        // Byte 0 = 0x00, byte 1 = 0x01
        if (decrypted[0] != 0x00 || decrypted[1] != 0x01) return false;
        // Padding string: 0xFF up to the 0x00 separator
        uint256 i = 2;
        for (; i < k; i++) {
            if (decrypted[i] != 0xFF) break;
        }
        // need at least 8 bytes of 0xFF, then a 0x00 separator
        if (i < 10 || i >= k || decrypted[i] != 0x00) return false;
        i++;
        // DigestInfo prefix
        for (uint256 j = 0; j < SHA256_PREFIX.length; j++) {
            if (decrypted[i + j] != SHA256_PREFIX[j]) return false;
        }
        i += SHA256_PREFIX.length;
        // the 32-byte digest, and it must run exactly to the end
        if (i + 32 != k) return false;
        for (uint256 j = 0; j < 32; j++) {
            if (decrypted[i + j] != digest[j]) return false;
        }
        return true;
    }

    /// @dev Calls the modexp precompile (0x05): base^exp mod modulus, all big-endian.
    function modExp(bytes memory base, bytes memory exp, bytes memory mod)
        internal
        view
        returns (bool ok, bytes memory result)
    {
        uint256 bl = base.length;
        uint256 el = exp.length;
        uint256 ml = mod.length;
        bytes memory input = abi.encodePacked(
            uint256(bl), uint256(el), uint256(ml), base, exp, mod
        );
        result = new bytes(ml);
        assembly {
            ok :=
                staticcall(
                    gas(),
                    0x05,
                    add(input, 0x20),
                    mload(input),
                    add(result, 0x20),
                    ml
                )
        }
    }
}
