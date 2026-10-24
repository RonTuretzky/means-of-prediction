#!/usr/bin/env python3
"""Independent synthetic decimal LayerNorm reference for the Solidity kernel tests.

These are deliberately generated features and gamma values, not checkpoint weights,
real inference activations, or evidence of full-model parity.
"""

import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN, localcontext


SCALE = 1_000_000


def vectors(width: int) -> dict:
    if width not in (5, 128, 1024):
        raise ValueError("expected a test width of 5, 128, or 1024")
    if width == 5:
        raw_x = [-2_000_000, -1_000_000, 0, 1_000_000, 2_000_000]
        raw_gamma = [1_000_000, 900_000, 1_050_000, 1_100_000, 750_000]
    else:
        raw_x = [(((i * 73 + 17) % 401) - 200) * 10_000 for i in range(width)]
        raw_gamma = [1_000_000 + ((((i * 29 + 7) % 21) - 10) * 5_000) for i in range(width)]

    with localcontext() as context:
        context.prec = 80
        x = [Decimal(value) / SCALE for value in raw_x]
        gamma = [Decimal(value) / SCALE for value in raw_gamma]
        mean = sum(x) / width
        variance = sum((value - mean) ** 2 for value in x) / width
        denominator = (variance + Decimal("0.00001")).sqrt()
        expected = [
            int((((value - mean) / denominator) * gain * SCALE).to_integral_value(rounding=ROUND_HALF_EVEN))
            for value, gain in zip(x, gamma)
        ]
    return {"x": raw_x, "gamma": raw_gamma, "expected": expected}


if __name__ == "__main__":
    print(json.dumps(vectors(int(sys.argv[1])), separators=(",", ":")))
