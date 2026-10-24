// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// Exact pinned integer matrix kernel. No model authentication or settlement claim.
/// Weight bytes are signed big-endian int16, row-major. No bias for layer0 QKV.
library LayaQ16Matmul {
    error BadShape();
    error BadMagnitude();
    error UnsafeShift();

    function run(int256[] memory x, uint256 width, bytes memory weights, bytes memory shifts)
        internal
        pure
        returns (int256[] memory out)
    {
        uint256 outputs = shifts.length;
        if (
            width == 0 || width > 4096 || x.length == 0 || x.length % width != 0 || x.length / width > 320
                || outputs == 0 || outputs > 16384 || weights.length != outputs * width * 2
        ) revert BadShape();
        // Enforce the runtime's symmetric int16 range (not -32768).
        for (uint256 j; j < weights.length; j += 2) {
            int256 w;
            assembly ("memory-safe") {
                w := signextend(1, shr(sub(240, mul(and(j, 31), 8)), mload(add(add(weights, 32), and(j, not(31))))))
            }
            if (w == -32768) revert BadMagnitude();
        }
        out = new int256[](x.length / width * outputs);
        int256[] memory qx = new int256[](width);
        for (uint256 row; row < x.length / width; ++row) {
            uint256 maximum;
            for (uint256 k; k < width; ++k) {
                int256 value = x[row * width + k];
                if (value <= -int256(1 << 62) || value >= int256(1 << 62)) revert BadMagnitude();
                uint256 magnitude = uint256(value < 0 ? -value : value);
                if (magnitude > maximum) maximum = magnitude;
            }
            uint256 shift;
            while (maximum > (32767 << shift)) ++shift;
            if (shift > 16) revert UnsafeShift();
            uint256 den = 1 << shift;
            for (uint256 k; k < width; ++k) {
                int256 value = x[row * width + k];
                uint256 magnitude = uint256(value < 0 ? -value : value);
                uint256 whole = magnitude / den;
                uint256 rem = magnitude % den;
                if (rem * 2 > den || (rem * 2 == den && whole % 2 == 1)) ++whole;
                if (whole > 32767) revert BadMagnitude();
                qx[k] = value < 0 ? -int256(whole) : int256(whole);
            }
            for (uint256 j; j < outputs; ++j) {
                uint256 combined = shift + uint8(shifts[j]);
                if (combined > 16) revert UnsafeShift();
                int256 dot;
                // width<=4096 and each magnitude<=32767 prove accumulator<2^42.
                // Lengths validated above. Aligned loads stay within the allocated
                // padded bytes buffer, including its last two-byte element.
                // Absolute offsets also support odd widths across weight rows.
                assembly ("memory-safe") {
                    let xp := add(qx, 32)
                    let end := add(xp, mul(width, 32))
                    let offset := mul(mul(j, width), 2)
                    let base := add(weights, 32)
                    for {} lt(xp, end) {
                        xp := add(xp, 32)
                        offset := add(offset, 2)
                    } {
                        dot := add(
                            dot,
                            mul(
                                mload(xp),
                                signextend(
                                    1,
                                    shr(sub(240, mul(and(offset, 31), 8)), mload(add(base, and(offset, not(31)))))
                                )
                            )
                        )
                    }
                }
                out[row * outputs + j] = dot >> (16 - combined);
            }
        }
    }
}
