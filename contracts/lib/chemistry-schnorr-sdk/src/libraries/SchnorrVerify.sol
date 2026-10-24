// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

/// @title SchnorrVerify
/// @notice Constant-gas verification of an aggregate secp256k1 Schnorr signature using the
///         audited Chronicle/MakerDAO "Scribe" `ecrecover` trick — the EVM performs **one**
///         `ecrecover` and no elliptic-curve scalar multiplication.
/// @dev The signing/verification convention is fixed and must match the Rust signer
///      (`common/src/schnorr`) byte-for-byte:
///
///        e = keccak256(Xx ‖ Xparity ‖ message ‖ Raddr) mod n      (Xparity a single 0/1 byte)
///        s = k − e·x (mod n)   ⇒   R = s·G + e·X
///        verify: ecrecover(−s·Xx mod n, 27+Xparity, Xx, e·Xx mod n) == Raddr
library SchnorrVerify {
    /// secp256k1 group order `n`.
    uint256 internal constant N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;

    /// @notice Verifies `sig = (s, Raddr)` over `message` against the aggregate key
    ///         `(Xx, Xparity)`.
    /// @param Xx        x-coordinate of the aggregate public key `X` (must be `< n`).
    /// @param Xparity   y-parity of `X`: `0` if even, `1` if odd.
    /// @param message   the 32-byte signed message (the task digest).
    /// @param s         the aggregate response scalar (`0 < s < n`).
    /// @param Raddr     `address(R)` — the nonce point's Ethereum address (non-zero).
    /// @return ok       true iff the signature is valid.
    function verify(uint256 Xx, uint8 Xparity, bytes32 message, uint256 s, address Raddr)
        internal
        pure
        returns (bool ok)
    {
        // Scribe validity domain: Xx a usable `r` (< n and non-zero), canonical s, real R,
        // and a defined parity bit.
        if (Xx == 0 || Xx >= N) return false;
        if (s == 0 || s >= N) return false;
        if (Raddr == address(0)) return false;
        if (Xparity > 1) return false;

        uint256 e = uint256(keccak256(abi.encodePacked(Xx, Xparity, message, Raddr))) % N;
        if (e == 0) return false;

        // h = −s·Xx (mod n) ; sp = e·Xx (mod n). Both non-zero because s,e,Xx ∈ (0,n), n prime.
        uint256 sXx = mulmod(s, Xx, N);
        if (sXx == 0) return false;
        bytes32 h = bytes32(N - sXx);
        bytes32 sp = bytes32(mulmod(e, Xx, N));

        address recovered = ecrecover(h, Xparity == 0 ? 27 : 28, bytes32(Xx), sp);
        return recovered != address(0) && recovered == Raddr;
    }
}
