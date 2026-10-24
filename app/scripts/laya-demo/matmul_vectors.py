#!/usr/bin/env python3
"""Export one private, actual-weight 32x1024 Laya projection benchmark fixture.

Reads only the first 32 rows of the selected checkpoint's Wqkv tensor. The input
is the real first embedding LayerNorm's float32 output *rounded to Q6* in the
private fixture, then converted to Q24. This second quantization is an explicit
approximation, not the exact original float32 activation or a model-parity test.

Run with the local Laya venv Python. Never commit the generated fixture.
"""

import argparse
import json
import os
from pathlib import Path

import torch
from safetensors import safe_open


Q24 = 1 << 24
TENSOR = "encoder.layers.0.attn.Wqkv.weight"


def round_ratio_ties_even(numerator: int, denominator: int) -> int:
    sign = -1 if numerator < 0 else 1
    whole, remainder = divmod(abs(numerator), denominator)
    if 2 * remainder > denominator or (2 * remainder == denominator and whole % 2):
        whole += 1
    return sign * whole


def encode_rows(rows: list[list[float]], x_q24: list[int], byte_width: int) -> tuple[str, list[int], list[int]]:
    maximum = (1 << (8 * byte_width - 1)) - 1
    packed = bytearray()
    shifts = []
    outputs = []
    for row in rows:
        for shift in range(31, -1, -1):
            quantized = [round(weight * (1 << shift)) for weight in row]
            if all(-maximum - 1 <= weight <= maximum for weight in quantized):
                break
        else:
            raise ValueError("weight row cannot be represented at a nonnegative power-of-two shift")
        packed.append(shift)
        for weight in quantized:
            packed.extend(weight.to_bytes(byte_width, "big", signed=True))
        shifts.append(shift)
        outputs.append(sum(weight * value for weight, value in zip(quantized, x_q24)) >> shift)
    return "0x" + packed.hex(), shifts, outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--norm-fixture", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    model_path = args.checkpoint / "model.safetensors"
    manifest = json.loads(args.manifest.read_text())
    norm = json.loads(args.norm_fixture.read_text())
    if Path(manifest["path"]).resolve() != args.checkpoint.resolve():
        raise ValueError("selected checkpoint path and model manifest disagree")
    if norm.get("weightsSha256") != manifest.get("weightsSha256"):
        raise ValueError("LayerNorm fixture and checkpoint manifest disagree")
    if len(norm["floatOriginalQ6"]) != 1024:
        raise ValueError("expected a width-1024 genuine LayerNorm output")
    x_q6 = norm["floatOriginalQ6"]
    x_q24 = [round_ratio_ties_even(value * Q24, 1_000_000) for value in x_q6]
    if any(abs(value) > 1 << 31 for value in x_q24):
        raise ValueError("Q24 input exceeds Solidity benchmark bound")

    with safe_open(model_path, framework="pt", device="cpu") as weights:
        if TENSOR not in weights.keys():
            raise ValueError(f"missing actual checkpoint tensor: {TENSOR}")
        tensor = weights.get_slice(TENSOR)
        if tensor.get_shape() != [3072, 1024]:
            raise ValueError(f"unexpected Wqkv shape: {tensor.get_shape()}")
        first_rows = tensor[:32].contiguous().to(torch.float32)
    rows = first_rows.tolist()
    packed_i8, shifts_i8, expected_i8 = encode_rows(rows, x_q24, 1)
    packed_i16, shifts_i16, expected_i16 = encode_rows(rows, x_q24, 2)

    # Reference float matmul uses the same Q6-rounded input; it measures weight
    # quantization + Q24 arithmetic drift, not error against untouched activations.
    float_input = torch.tensor([value / 1_000_000 for value in x_q6], dtype=torch.float32)
    float_output = torch.mv(first_rows, float_input)
    float_q24 = [round(float(value) * Q24) for value in float_output]
    fixture = {
        "schema": 1,
        "tensor": TENSOR,
        "weightsSha256": manifest["weightsSha256"],
        "inputProvenance": "private first encoder.embeddings.norm floatOriginalQ6, converted to Q24 ties-even",
        "rounding": "per-row weights nearest ties-even; signed accumulated output arithmetic shift floors negatives",
        "rows": 32,
        "cols": 1024,
        "xQ24": x_q24,
        "packedI8": packed_i8,
        "packedI16": packed_i16,
        "shiftsI8": shifts_i8,
        "shiftsI16": shifts_i16,
        "expectedI8Q24": expected_i8,
        "expectedI16Q24": expected_i16,
        "floatReferenceQ24": float_q24,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(args.out, flags, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(fixture, stream, separators=(",", ":"))
    print(json.dumps({
        "rows": 32,
        "cols": 1024,
        "macsPerCall": 32 * 1024,
        "i8MaxAbsFloatDriftQ24": max(abs(a - b) for a, b in zip(expected_i8, float_q24)),
        "i16MaxAbsFloatDriftQ24": max(abs(a - b) for a, b in zip(expected_i16, float_q24)),
        "i8ShiftRange": [min(shifts_i8), max(shifts_i8)],
        "i16ShiftRange": [min(shifts_i16), max(shifts_i16)],
    }))


if __name__ == "__main__":
    main()
