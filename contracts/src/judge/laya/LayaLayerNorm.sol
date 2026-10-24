// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @notice Bounded, synthetic-demo LayerNorm operator for the width-1024 Laya ModernBERT encoder.
/// @dev This is a single operator, not an exported model or model-parity claim. ModernBERT
///      subtracts the feature mean; Qwen-style RMSNorm would be the wrong operation here.
///      x, gamma and result use signed Q6 (1e6 means 1.0). Epsilon is 1e-5, represented
///      exactly as 1e7 in squared-Q6 units. There is no beta (norm_bias=false).
///      Centering uses (n*x[i] - sum(x))/n so a fractional mean is not rounded early.
///      Variance is floored once in squared-Q6 units; integer sqrt is floored at Q12
///      precision; final signed division rounds toward zero. These are intentional
///      deterministic EVM rounding rules, not float32 bit parity.
///      For 1 <= n <= 1024 and |x|, |gamma| <= 1e9, intermediate sums and products
///      fit comfortably in int256/uint256 (worst centered-square sum < 2^92).
library LayaLayerNorm {
    int256 internal constant SCALE = 1_000_000;
    uint256 internal constant MAX_WIDTH = 1024;
    int256 internal constant MAX_ABS_VALUE = 1_000_000_000;
    uint256 internal constant EPSILON_SQUARED_Q6 = 10_000_000;

    error InvalidWidth(uint256 width);
    error GammaWidthMismatch(uint256 inputs, uint256 gamma);
    error InputOutOfRange(uint256 index);
    error GammaOutOfRange(uint256 index);

    function normalize(int256[] memory x, int256[] memory gamma) internal pure returns (int256[] memory result) {
        uint256 n = x.length;
        if (n == 0 || n > MAX_WIDTH) revert InvalidWidth(n);
        if (gamma.length != n) revert GammaWidthMismatch(n, gamma.length);

        int256 sum;
        for (uint256 i; i < n; ++i) {
            if (x[i] < -MAX_ABS_VALUE || x[i] > MAX_ABS_VALUE) revert InputOutOfRange(i);
            if (gamma[i] < -MAX_ABS_VALUE || gamma[i] > MAX_ABS_VALUE) revert GammaOutOfRange(i);
            sum += x[i];
        }

        int256 signedN = int256(n);
        uint256 squaredSum;
        for (uint256 i; i < n; ++i) {
            int256 centeredN = signedN * x[i] - sum;
            uint256 magnitude = uint256(centeredN < 0 ? -centeredN : centeredN);
            squaredSum += magnitude * magnitude;
        }
        uint256 variance = squaredSum / (n * n * n);
        // Q12 square root of the variance + epsilon, still in raw input units.
        uint256 denominatorQ12 = _sqrt((variance + EPSILON_SQUARED_Q6) * uint256(SCALE * SCALE));

        result = new int256[](n);
        int256 signedDenominator = int256(n * denominatorQ12);
        for (uint256 i; i < n; ++i) {
            int256 centeredN = signedN * x[i] - sum;
            result[i] = centeredN * gamma[i] * SCALE / signedDenominator;
        }
    }

    /// @dev Floor(sqrt(a)); integer Babylonian method, independent of external math libraries.
    function _sqrt(uint256 a) private pure returns (uint256) {
        if (a == 0) return 0;
        uint256 x = a;
        uint256 y = (x + 1) / 2;
        while (y < x) {
            x = y;
            y = (a / y + y) / 2;
        }
        return x;
    }
}
