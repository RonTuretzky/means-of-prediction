#!/usr/bin/env python3
"""Small independent arithmetic tests for the derived integer profile."""

import math
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from chemistry_integer_runtime import Q, Runtime, _qweight, checked_add, round_even_pow2, round_even_ratio


class IntegerArithmeticTests(unittest.TestCase):
    def _tiny_export(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        artifacts = {
            "one.q.npy": np.array([[1, -2]], dtype=np.int16),
            "one.shift.npy": np.array([0], dtype=np.uint8),
            "exp_q30.npy": np.array([1 << 30, 0], dtype=np.int64),
        }
        for name, arr in artifacts.items():
            np.save(root / name, arr)
        digest = lambda name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        manifest = {
            "version": "laya-int16-q16-v1",
            "sourceSha256": "5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169",
            "luts": {"exp_q30": {"sha256": digest("exp_q30.npy"), "dtype": "int64", "shape": [2]}},
            "tensors": {"one": {"kind": "int16_matrix", "shape": [1, 2], "files": {
                "q": {"path": "one.q.npy", "sha256": digest("one.q.npy")},
                "shift": {"path": "one.shift.npy", "sha256": digest("one.shift.npy")}}}},
        }
        (root / "manifest.json").write_text(json.dumps(manifest))
        return tmp, root

    def test_export_bit_corruption_fails_closed(self):
        for corrupted in ("one.q.npy", "one.shift.npy", "exp_q30.npy"):
            with self.subTest(file=corrupted):
                tmp, root = self._tiny_export()
                try:
                    payload = bytearray((root / corrupted).read_bytes())
                    payload[-1] ^= 1
                    (root / corrupted).write_bytes(payload)
                    if corrupted == "exp_q30.npy":
                        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                            Runtime(root)
                    else:
                        r = Runtime(root)
                        with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                            r.get("one")
                finally:
                    tmp.cleanup()

    def test_nearest_even_signed_rows(self):
        x = torch.tensor([[-5, -3, -1, 1, 3, 5]], dtype=torch.int64)
        self.assertEqual(round_even_pow2(x, torch.tensor([1])).tolist(), [[-2, -2, 0, 0, 2, 2]])
        self.assertEqual([round_even_ratio(n, 2) for n in (1, 3, 5, 7)], [0, 2, 2, 4])

    def test_weight_scale_bounds_and_ties(self):
        w = np.array([[0.5, -0.5], [1.0, -1.0]], dtype=np.float32)
        q, shift = _qweight(w)
        self.assertEqual(q.tolist(), [[16384, -16384], [16384, -16384]])
        self.assertEqual(shift.tolist(), [1, 2])

    def test_matrix_signed_arithmetic_shift(self):
        r = Runtime.__new__(Runtime)
        r.cache = {}
        r.matmul_count = r.mac_count = r.attn_mac_count = 0
        weight = torch.tensor([[10000, -20000], [-500, 500]], dtype=torch.int64)
        scale = torch.tensor([0, 0], dtype=torch.int64)
        r.get = lambda name: (weight, scale)
        x = torch.tensor([[100000, -80000], [-1, 1]], dtype=torch.int64)
        actual = r.mm(x, "synthetic")
        qx0 = [round(v / 4) for v in x[0].tolist()]
        qx1 = x[1].tolist()
        expected = [[sum(a * b for a, b in zip(row, wrow)) * (4 if i == 0 else 1) // Q
                     for wrow in weight.tolist()] for i, row in enumerate((qx0, qx1))]
        self.assertEqual(actual.tolist(), expected)
        self.assertEqual(r.mac_count, 8)

    def test_layer_norm_integer_reference(self):
        r = Runtime.__new__(Runtime)
        r.get = lambda name: torch.tensor([Q, Q, Q, Q], dtype=torch.int64)
        x = torch.tensor([[Q, 2 * Q, 3 * Q, 4 * Q]], dtype=torch.int64)
        got = r.norm(x, "gamma").tolist()[0]
        mu = sum(x.tolist()[0]) // 4
        centers = [v - mu for v in x.tolist()[0]]
        variance = sum(v * v for v in centers) // 4
        root = math.isqrt(variance + 42950)
        expected = [math.trunc(v * Q / root) for v in centers]
        self.assertEqual(got, expected)

    def test_large_values_rejected_before_overflow(self):
        r = Runtime.__new__(Runtime)
        r.get = lambda name: torch.full((4,), Q, dtype=torch.int64)
        with self.assertRaisesRegex(OverflowError, "LayerNorm square"):
            r.norm(torch.tensor([[1 << 40, 0, 0, 0]], dtype=torch.int64), "gamma")
        with self.assertRaisesRegex(OverflowError, "residual"):
            checked_add(torch.tensor([1 << 61]), torch.tensor([1 << 61]), "residual")
        huge = torch.full((16, 1, 64), 1 << 32, dtype=torch.int64)
        with self.assertRaisesRegex(OverflowError, "attention QK"):
            r.attention(huge, huge, huge, torch.tensor([True]), False)

    def test_softmax_mask_and_rope_zero_position(self):
        r = Runtime.__new__(Runtime)
        r.lut = {
            "exp_q30": torch.tensor(np.rint(np.exp(-np.arange(4097) / 256) * (1 << 30)), dtype=torch.int64),
            "rope_full_cos_q16": torch.full((1, 32), Q, dtype=torch.int64),
            "rope_full_sin_q16": torch.zeros((1, 32), dtype=torch.int64),
        }
        p = r.softmax(torch.tensor([[Q, 0, 100 * Q]], dtype=torch.int64),
                      torch.tensor([[True, True, False]]))
        self.assertEqual(int(p.sum()), Q)
        self.assertEqual(int(p[0, 2]), 0)
        self.assertGreater(int(p[0, 0]), int(p[0, 1]))
        q = torch.arange(64, dtype=torch.int64).reshape(1, 1, 64) * 1000
        self.assertTrue(torch.equal(r.rope(q, "full"), q))


if __name__ == "__main__":
    unittest.main()
