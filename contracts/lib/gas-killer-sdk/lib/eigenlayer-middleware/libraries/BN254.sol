// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @notice MINIMAL mirror of eigenlayer-middleware `src/libraries/BN254.sol`: only the point
/// structs, which fix the ABI layout of `IBLSSignatureCheckerTypes.NonSignerStakesAndSignature`
/// (and therefore of `GasKillerSDK.verifyAndUpdate`). Field order/types are verbatim.
library BN254 {
    struct G1Point {
        uint256 X;
        uint256 Y;
    }

    struct G2Point {
        uint256[2] X;
        uint256[2] Y;
    }
}
