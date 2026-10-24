// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.28;

/// @notice Bounded Q24 row matmul for a 32x1024 Laya projection feasibility measurement.
/// @dev The two inner assembly kernels reproduce Qwen3.matmulRows' int8 (32 weights/MLOAD,
///      eight-way unrolled) and int16 paths from solidity-sdk commit
///      d44f65d6267cf68edc86c64cff446d1d4fe48d06, src/examples/onchain-llm/Qwen3.sol
///      (AGPL-3.0-only). Shape, input and shift guards here are specific to this spike.
///      Each row is [u8 shift][1024 signed int8 or big-endian int16 weights]. Inputs and
///      outputs are signed Q24. Output = arithmetic-right-shift(sum(weight * input), shift),
///      so negative values round toward negative infinity. This is not a full model kernel.
///      With |input| <= 2^31 and int16 magnitude <= 2^15, each accumulator's absolute
///      value is <= 1024*2^15*2^31 = 2^56, far inside int256. Shift is limited to 31.
library LayaMatmul {
    uint256 internal constant COLS = 1024;
    uint256 internal constant MAX_ROWS = 32;
    int256 internal constant MAX_ABS_INPUT = 1 << 31; // 128.0 in Q24

    error InvalidShape(uint256 rows, uint256 cols);
    error InvalidWeightBytes(uint256 weightBytes);
    error PackedLengthMismatch(uint256 actual, uint256 expected);
    error InputWidthMismatch(uint256 actual);
    error InputOutOfRange(uint256 index);
    error ShiftOutOfRange(uint256 row);

    function matmulRows(bytes memory packed, uint256 rows, uint256 cols, uint256 weightBytes, int256[] memory x)
        internal
        pure
        returns (int256[] memory out)
    {
        if (rows == 0 || rows > MAX_ROWS || cols != COLS) revert InvalidShape(rows, cols);
        if (weightBytes != 1 && weightBytes != 2) revert InvalidWeightBytes(weightBytes);
        uint256 expectedLength = rows * (1 + cols * weightBytes);
        if (packed.length != expectedLength) revert PackedLengthMismatch(packed.length, expectedLength);
        if (x.length != cols) revert InputWidthMismatch(x.length);
        for (uint256 i; i < cols; ++i) {
            if (x[i] < -MAX_ABS_INPUT || x[i] > MAX_ABS_INPUT) revert InputOutOfRange(i);
        }
        uint256 stride = 1 + cols * weightBytes;
        for (uint256 row; row < rows; ++row) {
            if (uint8(packed[row * stride]) > 31) revert ShiftOutOfRange(row);
        }

        out = new int256[](rows);
        if (weightBytes == 1) _matmulI8(packed, rows, cols, x, out);
        else _matmulI16(packed, rows, cols, x, out);
    }

    /// @dev Reproduced from Qwen3._matmulI8 at the pinned commit above.
    function _matmulI8(bytes memory buf, uint256 rows, uint256 cols, int256[] memory x, int256[] memory out)
        private
        pure
    {
        assembly ("memory-safe") {
            let xp := add(x, 0x20)
            let op := add(out, 0x20)
            let rp := add(buf, 0x20)
            let full := and(cols, not(31))
            for { let i := 0 } lt(i, rows) { i := add(i, 1) } {
                let acc := 0
                let xq := xp
                for { let j := 0 } lt(j, full) { j := add(j, 32) } {
                    let word := mload(add(add(rp, 1), j))
                    for { let b := 0 } lt(b, 32) { b := add(b, 8) } {
                        let w := shl(mul(b, 8), word)
                        acc := add(acc, mul(signextend(0, byte(0, w)), mload(xq)))
                        acc := add(acc, mul(signextend(0, byte(1, w)), mload(add(xq, 0x20))))
                        acc := add(acc, mul(signextend(0, byte(2, w)), mload(add(xq, 0x40))))
                        acc := add(acc, mul(signextend(0, byte(3, w)), mload(add(xq, 0x60))))
                        acc := add(acc, mul(signextend(0, byte(4, w)), mload(add(xq, 0x80))))
                        acc := add(acc, mul(signextend(0, byte(5, w)), mload(add(xq, 0xa0))))
                        acc := add(acc, mul(signextend(0, byte(6, w)), mload(add(xq, 0xc0))))
                        acc := add(acc, mul(signextend(0, byte(7, w)), mload(add(xq, 0xe0))))
                        xq := add(xq, 0x100)
                    }
                }
                for { let j := full } lt(j, cols) { j := add(j, 1) } {
                    acc := add(acc, mul(signextend(0, shr(248, mload(add(add(rp, 1), j)))), mload(add(xp, shl(5, j)))))
                }
                mstore(op, sar(shr(248, mload(rp)), acc))
                op := add(op, 0x20)
                rp := add(rp, add(1, cols))
            }
        }
    }

    /// @dev Reproduced from Qwen3._matmulI16 at the pinned commit above.
    function _matmulI16(bytes memory buf, uint256 rows, uint256 cols, int256[] memory x, int256[] memory out)
        private
        pure
    {
        assembly ("memory-safe") {
            let xp := add(x, 0x20)
            let op := add(out, 0x20)
            let rp := add(buf, 0x20)
            for { let i := 0 } lt(i, rows) { i := add(i, 1) } {
                let acc := 0
                for { let j := 0 } lt(j, cols) { j := add(j, 1) } {
                    let wv := signextend(1, shr(240, mload(add(add(rp, 1), shl(1, j)))))
                    acc := add(acc, mul(wv, mload(add(xp, shl(5, j)))))
                }
                mstore(op, sar(shr(248, mload(rp)), acc))
                op := add(op, 0x20)
                rp := add(rp, add(1, shl(1, cols)))
            }
        }
    }
}
