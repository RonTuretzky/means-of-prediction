// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {LayaQ16LayerNorm} from "./LayaQ16LayerNorm.sol";

/// @notice Exact embedding lookup + Q16 LayerNorm prefix of the pinned model.
/// @dev A sparse, sorted table carries complete 1024-element rows for the requested
/// vocabulary IDs. Every token, including padding, is computed. Big-endian int32
/// packing changes transport only. Production authentication/availability of the
/// table against the full model commitment remains unimplemented; this is a kernel.
library LayaQ16Embedding {
    uint256 internal constant WIDTH = 1024;
    uint256 internal constant VOCAB = 50368;
    error BadTable();
    error BadTokens();
    error MissingToken(uint256 token);

    function run(uint32[] memory tokenIds, uint32[] memory tableIds, bytes memory packedRows, bytes memory packedGamma)
        internal
        pure
        returns (int256[] memory)
    {
        if (tokenIds.length < 2 || tokenIds.length > 320) revert BadTokens();
        if (
            tableIds.length == 0 || tableIds.length > VOCAB || packedRows.length != tableIds.length * WIDTH * 4
                || packedGamma.length != WIDTH * 4
        ) revert BadTable();
        for (uint256 i; i < tableIds.length; ++i) {
            if (tableIds[i] >= VOCAB || (i > 0 && tableIds[i] <= tableIds[i - 1])) revert BadTable();
        }
        int256[] memory x = new int256[](tokenIds.length * WIDTH);
        int256[] memory gamma = new int256[](WIDTH);
        for (uint256 col; col < WIDTH; ++col) {
            gamma[col] = _i32(packedGamma, col * 4);
        }
        for (uint256 row; row < tokenIds.length; ++row) {
            uint256 token = tokenIds[row];
            if (token >= VOCAB) revert BadTokens();
            uint256 lo;
            uint256 hi = tableIds.length;
            while (lo < hi) {
                uint256 mid = (lo + hi) / 2;
                if (tableIds[mid] < token) lo = mid + 1;
                else hi = mid;
            }
            if (lo == tableIds.length || tableIds[lo] != token) revert MissingToken(token);
            for (uint256 col; col < WIDTH; ++col) {
                x[row * WIDTH + col] = _i32(packedRows, (lo * WIDTH + col) * 4);
            }
        }
        return LayaQ16LayerNorm.normalize(x, gamma, new int256[](0));
    }

    function _i32(bytes memory packed, uint256 offset) private pure returns (int256 v) {
        // Callers validate all lengths. Discard the following 28 loaded bytes.
        assembly ("memory-safe") { v := signextend(3, shr(224, mload(add(add(packed, 32), offset)))) }
    }
}
