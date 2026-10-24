// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @notice LayerNorm for the pinned laya-int16-q16-v1 arithmetic, width 1024.
/// @dev Matches Runtime.norm in chemistry_integer_runtime.py, including its batch-wide
/// magnitude guards. This is distinct from the older Q6 experiment. No model inference,
/// weight authentication, email validation or settlement is implemented here.
library LayaQ16LayerNorm {
    uint256 internal constant WIDTH = 1024;
    uint256 internal constant LIMIT = 1 << 62;
    uint256 internal constant Q = 1 << 16;
    uint256 internal constant EPS_Q32 = 42950;

    error BadShape();
    error MagnitudeOverflow();

    /// @dev Input is row-major Q16. Mutates and returns x to bound temporary memory.
    /// Empty bias means no beta; otherwise beta has 1024 Q16 elements.
    function normalize(int256[] memory x, int256[] memory gamma, int256[] memory bias)
        internal
        pure
        returns (int256[] memory)
    {
        if (
            x.length == 0 || x.length % WIDTH != 0 || x.length / WIDTH > 320 || gamma.length != WIDTH
                || (bias.length != 0 && bias.length != WIDTH)
        ) revert BadShape();
        uint256 maxX = _maxAbs(x);
        _product(WIDTH, maxX);
        uint256 rows = x.length / WIDTH;
        int256[] memory means = new int256[](rows);
        for (uint256 row; row < rows; ++row) {
            int256 sum;
            for (uint256 col; col < WIDTH; ++col) {
                sum += x[row * WIDTH + col];
            }
            // Python // floors negatives; Solidity / truncates toward zero.
            int256 mean = sum / int256(WIDTH);
            if (sum < 0 && sum % int256(WIDTH) != 0) --mean;
            means[row] = mean;
        }
        if (maxX + _maxAbs(means) >= LIMIT) revert MagnitudeOverflow();
        for (uint256 row; row < rows; ++row) {
            for (uint256 col; col < WIDTH; ++col) {
                x[row * WIDTH + col] -= means[row];
            }
        }
        uint256 maxCentered = _maxAbs(x);
        _product(maxCentered, maxCentered);
        _product(maxCentered, Q);
        for (uint256 row; row < rows; ++row) {
            uint256 total;
            for (uint256 col; col < WIDTH; ++col) {
                int256 v = x[row * WIDTH + col];
                total += uint256(v * v);
            }
            // The reference uses an unbounded sum, then rejects >= 2**62.
            if (total >= LIMIT) revert MagnitudeOverflow();
            int256 root = int256(_sqrt(total / WIDTH + EPS_Q32));
            for (uint256 col; col < WIDTH; ++col) {
                uint256 i = row * WIDTH + col;
                x[i] = x[i] * int256(Q) / root; // signed truncation, not floor
            }
        }
        _product(_maxAbs(x), _maxAbs(gamma));
        for (uint256 row; row < rows; ++row) {
            for (uint256 col; col < WIDTH; ++col) {
                uint256 i = row * WIDTH + col;
                x[i] = (x[i] * gamma[col]) >> 16; // signed floor, not truncation
            }
        }
        if (bias.length != 0) {
            if (_maxAbs(x) + _maxAbs(bias) >= LIMIT) revert MagnitudeOverflow();
            for (uint256 row; row < rows; ++row) {
                for (uint256 col; col < WIDTH; ++col) {
                    x[row * WIDTH + col] += bias[col];
                }
            }
        }
        return x;
    }

    function _maxAbs(int256[] memory values) private pure returns (uint256 greatest) {
        for (uint256 i; i < values.length; ++i) {
            int256 v = values[i];
            if (v <= -int256(LIMIT) || v >= int256(LIMIT)) revert MagnitudeOverflow();
            uint256 magnitude = uint256(v < 0 ? -v : v);
            if (magnitude > greatest) greatest = magnitude;
        }
    }

    function _product(uint256 a, uint256 b) private pure {
        // Inputs are already bounded below 2**62, so this cannot overflow uint256.
        if (a * b >= LIMIT) revert MagnitudeOverflow();
    }

    function _sqrt(uint256 n) private pure returns (uint256 root) {
        if (n == 0) return 0;
        root = n;
        uint256 next = (n + 1) / 2;
        while (next < root) {
            root = next;
            next = (n / next + next) / 2;
        }
    }
}
