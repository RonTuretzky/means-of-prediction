// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

/// @title Secp256k1
/// @notice Minimal affine secp256k1 point arithmetic over the base field, used by
///         `SchnorrStakeRegistry` to maintain the aggregate operator public key and to
///         subtract non-signers from it. The identity (point at infinity) is represented
///         as `(0, 0)`.
/// @dev Signature *verification* does not use this library — that goes through the
///      `ecrecover` trick in `SchnorrVerify`. Point math is only needed for aggregation
///      (register/deregister) and per-non-signer subtraction at verify time (zero cost at
///      full participation). Modular inversion uses the `modexp` (0x05) precompile.
library Secp256k1 {
    /// secp256k1 base field prime `p`.
    uint256 internal constant P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F;
    /// secp256k1 curve constant `b` (a = 0).
    uint256 internal constant B = 7;

    error NotOnCurve();

    /// @notice `y² == x³ + 7 (mod p)` with `0 < x,y < p`.
    function isOnCurve(uint256 x, uint256 y) internal pure returns (bool) {
        if (x == 0 || y == 0 || x >= P || y >= P) return false;
        uint256 lhs = mulmod(y, y, P);
        uint256 rhs = addmod(mulmod(mulmod(x, x, P), x, P), B, P);
        return lhs == rhs;
    }

    /// @notice The negation `-P = (x, p - y)` (identity maps to identity).
    function negate(uint256 x, uint256 y) internal pure returns (uint256, uint256) {
        if (x == 0 && y == 0) return (0, 0);
        return (x, P - y);
    }

    /// @notice Affine point addition `(x1,y1) + (x2,y2)`, handling identities, doubling and
    ///         the `P + (-P) = O` case.
    function add(uint256 x1, uint256 y1, uint256 x2, uint256 y2) internal view returns (uint256 x3, uint256 y3) {
        if (x1 == 0 && y1 == 0) return (x2, y2);
        if (x2 == 0 && y2 == 0) return (x1, y1);

        uint256 lambda;
        if (x1 == x2) {
            // Same x: either doubling (y1 == y2) or inverse (y1 == p - y2 → identity).
            if (addmod(y1, y2, P) == 0) return (0, 0);
            // lambda = 3·x1² / (2·y1)
            uint256 num = mulmod(3, mulmod(x1, x1, P), P);
            uint256 den = mulmod(2, y1, P);
            lambda = mulmod(num, _inv(den), P);
        } else {
            // lambda = (y2 - y1) / (x2 - x1)
            uint256 num = _sub(y2, y1);
            uint256 den = _sub(x2, x1);
            lambda = mulmod(num, _inv(den), P);
        }
        // x3 = lambda² - x1 - x2
        x3 = _sub(_sub(mulmod(lambda, lambda, P), x1), x2);
        // y3 = lambda·(x1 - x3) - y1
        y3 = _sub(mulmod(lambda, _sub(x1, x3), P), y1);
    }

    /// @notice Point subtraction `(x1,y1) - (x2,y2)`.
    function sub(uint256 x1, uint256 y1, uint256 x2, uint256 y2) internal view returns (uint256, uint256) {
        (uint256 nx, uint256 ny) = negate(x2, y2);
        return add(x1, y1, nx, ny);
    }

    /// @notice `(a - b) mod p` for `a, b < p`.
    function _sub(uint256 a, uint256 b) private pure returns (uint256) {
        return addmod(a, P - b, P);
    }

    /// @notice Modular inverse `a^(p-2) mod p` via the `modexp` precompile (0x05).
    function _inv(uint256 a) private view returns (uint256 result) {
        uint256 p = P;
        uint256 expo = P - 2;
        assembly ("memory-safe") {
            let ptr := mload(0x40)
            mstore(ptr, 0x20) // len(base)
            mstore(add(ptr, 0x20), 0x20) // len(exp)
            mstore(add(ptr, 0x40), 0x20) // len(mod)
            mstore(add(ptr, 0x60), a)
            mstore(add(ptr, 0x80), expo)
            mstore(add(ptr, 0xa0), p)
            if iszero(staticcall(gas(), 0x05, ptr, 0xc0, ptr, 0x20)) { revert(0, 0) }
            result := mload(ptr)
        }
    }
}
