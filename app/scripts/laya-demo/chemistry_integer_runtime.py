#!/usr/bin/env python3
"""Versioned, CPU-only integer replay of the pinned Laya ModernBERT decision model.

This is a *derived arithmetic model*, never the unchanged float32 checkpoint.  All
forward tensor arithmetic is integer.  The one-time export uses the original
float32 weights to make Q16/int16 tensors and fixed integer lookup tables.

Arithmetic version laya-int16-q16-v1:
  * Q16 signed activations, bias, embedding, norm and lookup values.
  * Matrices: float32 -> nearest-even Q16 -> per-output-row power-of-two
    quantization into [-32767,32767] int16.  Matrix inputs use the same
    per-token-row power-of-two int16 quantization.
  * Exact signed int64 dot accumulation, then signed arithmetic right shift
    (floor for negative) to Q16.  The input/weight rounding loss is explicit.
  * LayerNorm mean/variance floor, integer square root, signed division toward
    zero, then gamma multiply arithmetic-shifted to Q16; eps=round-even(1e-5*2^32).
  * RoPE/GELU/exp/log lookup tables are generated once at export with float64
    math, rounded nearest-even to Q16/Q30, hashed, then integer interpolated.
  * Softmax probabilities Q16 floor normalized, remainder added to argmax.
  * All intermediate/matrix dimensions and int64 magnitude are checked.

The output is a local feasibility trace.  It is not an EVM executor or proof of
onchain affordability.  No labels, training, sealed evaluation, or network.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import time
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open


VERSION = "laya-int16-q16-v1"
Q = 1 << 16
EPS_Q32 = 42950  # nearest-even 1e-5 * 2**32
MAX_Q = 32767
TEMPERATURE_Q16 = 72673  # nearest-even 1.1089085340499878 * 65536
THRESHOLD_Q16 = 36045  # nearest-even 0.55 * 65536
LOG_TWO_Q16 = 45426
SOURCE_SHA = "5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169"
DEFAULT_MODEL = Path("/Users/wk/.local/share/means-of-prediction/laya-alert-demo-20261021/reference/runtime-model")
DEFAULT_EXPORT = Path("/Users/wk/.local/share/means-of-prediction/laya-chemistry-integer-20261021/export-v1")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tensor_hash(x: torch.Tensor) -> str:
    return hashlib.sha256(x.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def _save_npy(path: Path, a: np.ndarray) -> str:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        np.save(f, a, allow_pickle=False)
    os.replace(tmp, path)
    return sha(path)


def _q16(a: np.ndarray) -> np.ndarray:
    scaled = np.rint(a.astype(np.float64) * Q)
    if not np.isfinite(scaled).all() or np.max(np.abs(scaled)) >= 1 << 31:
        raise ValueError("nonfinite or out-of-range Q16 source tensor")
    return scaled.astype(np.int32)


def _qweight(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    q = _q16(a).astype(np.int64)
    if q.ndim != 2:
        raise ValueError("matrix expected")
    maxabs = np.max(np.abs(q), axis=1)
    shifts = np.zeros(len(maxabs), dtype=np.uint8)
    scale = np.ones(len(maxabs), dtype=np.int64)
    while np.any(maxabs > MAX_Q * scale):
        bigger = maxabs > MAX_Q * scale
        scale[bigger] *= 2
        shifts[bigger] += 1
    z = np.rint(q / scale[:, None]).astype(np.int64)
    if np.max(np.abs(z)) > MAX_Q:
        raise ValueError("int16 weight quantization overflow")
    return z.astype(np.int16), shifts


def _make_luts(dest: Path, max_pos: int = 320) -> dict:
    out = {}
    xs = np.arange(-12 * 256, 12 * 256 + 1, dtype=np.float64) / 256
    gelu = np.array([0.5 * x * (1 + math.erf(x / math.sqrt(2))) for x in xs])
    tables = {
        "gelu_q16": np.rint(gelu * Q).astype(np.int32),
        "exp_q30": np.rint(np.exp(-np.arange(16 * 256 + 1) / 256) * (1 << 30)).astype(np.int64),
        "log_q16": np.rint(np.log(np.maximum(np.arange(Q + 1) / Q, 1e-9)) * Q).astype(np.int32),
    }
    for kind, theta in (("full", 160000.0), ("sliding", 10000.0)):
        inv = theta ** (-np.arange(0, 64, 2, dtype=np.float64) / 64)
        freqs = np.arange(max_pos, dtype=np.float64)[:, None] * inv[None, :]
        tables[f"rope_{kind}_cos_q16"] = np.rint(np.cos(freqs) * Q).astype(np.int32)
        tables[f"rope_{kind}_sin_q16"] = np.rint(np.sin(freqs) * Q).astype(np.int32)
    for name, a in tables.items():
        out[name] = {"shape": list(a.shape), "dtype": str(a.dtype), "sha256": _save_npy(dest / f"{name}.npy", a)}
    return out


def export(model: Path, dest: Path) -> None:
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    original = model / "model.safetensors"
    actual_sha = sha(original)
    if actual_sha != SOURCE_SHA:
        raise ValueError(f"source checkpoint SHA mismatch: {actual_sha}")
    manifest_path = dest / "manifest.json"
    prior = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if prior and (prior.get("version") != VERSION or prior.get("sourceSha256") != SOURCE_SHA):
        raise ValueError("existing export is for a different source/policy")
    manifest = {
        "version": VERSION,
        "sourceSha256": SOURCE_SHA,
        "encoderConfigSha256": sha(model / "encoder/config.json"),
        "agentConfigSha256": sha(model / "rl_agent_config.json"),
        "q": Q,
        "epsilonQ32": EPS_Q32,
        "maxQuantizedMagnitude": MAX_Q,
        "rounding": "nearest-even source/row quantization; SAR floor dot/product; LN integer sqrt floor and signed quotient toward zero",
        "matmul": "exact CPU torch.int64 accumulation of signed int16 operands; per-input-row and per-weight-output-row power-of-two Q16-unit scales",
        "luts": _make_luts(dest),
        "tensors": {},
    }
    with safe_open(str(original), framework="pt", device="cpu") as f:
        for i, name in enumerate(sorted(f.keys())):
            t = f.get_tensor(name).numpy()
            is_matrix = t.ndim == 2 and (".weight" in name or name.endswith("_weight")) and not any(
                z in name for z in ("tok_embeddings", "type_emb")
            )
            if is_matrix:
                a, shift = _qweight(t)
                kind = "int16_matrix"
                pieces = [("q", a), ("shift", shift)]
            else:
                kind = "q16_tensor"
                pieces = [("q", _q16(t))]
            record = {"kind": kind, "shape": list(t.shape), "files": {}}
            for suffix, val in pieces:
                filename = f"{name}.{suffix}.npy"
                record["files"][suffix] = {"path": filename, "sha256": _save_npy(dest / filename, val)}
            manifest["tensors"][name] = record
            if i % 10 == 0 or i + 1 == len(f.keys()):
                print(f"export {i + 1}/{len(f.keys())} {name}", flush=True)
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, manifest_path)
    print(json.dumps({"exportManifest": str(manifest_path), "sha256": sha(manifest_path), "tensorCount": len(manifest["tensors"])}))


def div_trunc(a: torch.Tensor, b: torch.Tensor | int) -> torch.Tensor:
    return torch.div(a, b, rounding_mode="trunc")


def round_even_ratio(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator <= 0:
        raise ValueError("unsigned rounding ratio required")
    whole, remainder = divmod(numerator, denominator)
    return whole + int(remainder * 2 > denominator or
                       (remainder * 2 == denominator and whole % 2 == 1))


def round_even_pow2(x: torch.Tensor, shifts: torch.Tensor) -> torch.Tensor:
    """Divide signed integer tensor by per-row 2**shift, nearest ties to even."""
    den = (torch.ones_like(shifts, dtype=torch.int64) << shifts)[:, None]
    absolute = torch.abs(x)
    base = absolute // den
    rem = absolute % den
    inc = ((rem * 2 > den) | ((rem * 2 == den) & ((base & 1) == 1))).to(torch.int64)
    return torch.sign(x) * (base + inc)


def maxabs(x: torch.Tensor) -> int:
    return int(torch.max(torch.abs(x))) if x.numel() else 0


def guard_product(*magnitudes: int, label: str):
    bound = 1
    for magnitude in magnitudes:
        bound *= int(magnitude)
        if bound >= 1 << 62:
            raise OverflowError(f"{label} may exceed signed int64 safe bound")


def checked_add(a: torch.Tensor, b: torch.Tensor, label: str) -> torch.Tensor:
    guard_product(maxabs(a) + maxabs(b), label=label)
    return a + b


class Runtime:
    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads((root / "manifest.json").read_text())
        if self.manifest["version"] != VERSION or self.manifest["sourceSha256"] != SOURCE_SHA:
            raise ValueError("export policy/source mismatch")
        self.cache: dict[str, torch.Tensor | tuple[torch.Tensor, torch.Tensor]] = {}
        self.lut = {}
        for name, info in self.manifest["luts"].items():
            table = self._verified_numpy(name + ".npy", info["sha256"],
                                         np.dtype(info["dtype"]), tuple(info["shape"]))
            self.lut[name] = torch.from_numpy(table.astype(np.int64))
        self.matmul_count = 0
        self.mac_count = 0
        self.attn_mac_count = 0

    def _verified_numpy(self, filename: str, expected_hash: str,
                        expected_dtype: np.dtype, expected_shape: tuple[int, ...]) -> np.ndarray:
        # Hash the exact bytes that np.load consumes, with pickle explicitly off.
        payload = (self.root / filename).read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError(f"export artifact SHA mismatch: {filename}")
        value = np.load(io.BytesIO(payload), allow_pickle=False)
        if value.dtype != expected_dtype or value.shape != expected_shape:
            raise ValueError(f"export artifact dtype/shape mismatch: {filename}")
        return value

    def get(self, name: str):
        if name in self.cache:
            return self.cache[name]
        record = self.manifest["tensors"][name]
        q_type = np.dtype("int16" if record["kind"] == "int16_matrix" else "int32")
        q_file = record["files"]["q"]
        q = torch.from_numpy(self._verified_numpy(q_file["path"], q_file["sha256"],
                                                  q_type, tuple(record["shape"])).astype(np.int64))
        if record["kind"] == "int16_matrix":
            s_file = record["files"]["shift"]
            s = torch.from_numpy(self._verified_numpy(s_file["path"], s_file["sha256"],
                                                      np.dtype("uint8"), (record["shape"][0],)).astype(np.int64))
            out = (q, s)
        else:
            out = q
        self.cache[name] = out
        return out

    def drop_prefix(self, prefix: str):
        for k in [x for x in self.cache if x.startswith(prefix)]:
            del self.cache[k]

    def mm(self, x: torch.Tensor, weight_name: str, bias_name: str | None = None) -> torch.Tensor:
        if x.ndim != 2 or x.dtype != torch.int64:
            raise ValueError("mm expects 2D int64 Q16 activations")
        w, ws = self.get(weight_name)
        if x.shape[1] != w.shape[1]:
            raise ValueError(f"mm shape mismatch {weight_name}: {tuple(x.shape)} vs {tuple(w.shape)}")
        guard_product(x.shape[1], MAX_Q, MAX_Q, label="matrix accumulator")
        row_maxabs = x.abs().amax(dim=1)
        shift = torch.zeros_like(row_maxabs)
        scale = torch.ones_like(row_maxabs)
        while bool(torch.any(row_maxabs > MAX_Q * scale)):
            bigger = row_maxabs > MAX_Q * scale
            shift += bigger.to(torch.int64)
            scale = torch.where(bigger, scale * 2, scale)
        qx = round_even_pow2(x, shift)
        if bool(torch.any(qx.abs() > MAX_Q)):
            raise OverflowError("activation quantization escaped int16 range")
        # int64 GEMM is exact for this shape/range; deliberately avoid float BLAS.
        dot = qx @ w.T
        if maxabs(dot) >= (1 << 62):
            raise OverflowError("dot accumulator magnitude")
        right = 16 - shift[:, None] - ws[None, :]
        if bool(torch.any(right < 0)):
            raise OverflowError("matrix rescale requires unsafe left shift")
        out = dot >> right
        if bias_name is not None:
            out = checked_add(out, self.get(bias_name)[None, :], "matrix bias addition")
        self.matmul_count += 1
        self.mac_count += x.shape[0] * x.shape[1] * w.shape[0]
        return out

    def norm(self, x: torch.Tensor, weight: str, bias: str | None = None) -> torch.Tensor:
        n = x.shape[-1]
        guard_product(n, maxabs(x), label="LayerNorm mean sum")
        mean = x.sum(-1, keepdim=True) // n
        centered = x - mean
        guard_product(maxabs(x) + maxabs(mean), label="LayerNorm centering")
        guard_product(maxabs(centered), maxabs(centered), label="LayerNorm square")
        sq = centered * centered
        # Python's unbounded integers make the reduction safe even when the
        # maximal squared element times width would reject a sparse outlier.
        totals = [sum(int(v) for v in row) for row in sq.reshape(-1, n).tolist()]
        if any(v >= 1 << 62 for v in totals):
            raise OverflowError("LayerNorm variance sum")
        variance = torch.tensor([v // n for v in totals], dtype=torch.int64).reshape(sq.shape[:-1] + (1,))
        roots = torch.tensor([math.isqrt(int(v) + EPS_Q32) for v in variance.flatten()], dtype=torch.int64).reshape(variance.shape)
        guard_product(maxabs(centered), Q, label="LayerNorm normalized numerator")
        normalized = div_trunc(centered * Q, roots)
        guard_product(maxabs(normalized), maxabs(self.get(weight)), label="LayerNorm gamma multiplication")
        out = (normalized * self.get(weight)) >> 16
        if bias is not None:
            out = checked_add(out, self.get(bias), "LayerNorm bias addition")
        return out

    def gelu(self, x: torch.Tensor) -> torch.Tensor:
        table = self.lut["gelu_q16"]
        lo = -12 * Q
        clipped = x.clamp(lo, 12 * Q)
        idx = (clipped - lo) >> 8
        rem = (clipped - lo) & 255
        nxt = torch.clamp(idx + 1, max=len(table) - 1)
        out = (table[idx] * (256 - rem) + table[nxt] * rem) >> 8
        return torch.where(x <= lo, torch.zeros_like(x), torch.where(x >= 12 * Q, x, out))

    def softmax(self, x: torch.Tensor, mask: torch.Tensor | None = None) -> torch.Tensor:
        if mask is not None:
            x = x.masked_fill(~mask, -(1 << 50))
        top, argmax = x.max(dim=-1, keepdim=True)
        diff = (top - x).clamp(0, 16 * Q)
        idx = diff >> 8
        rem = diff & 255
        table = self.lut["exp_q30"]
        nxt = torch.clamp(idx + 1, max=len(table) - 1)
        exps = (table[idx] * (256 - rem) + table[nxt] * rem) >> 8
        exps = torch.where(diff >= 16 * Q, 0, exps)
        if mask is not None:
            exps = exps.masked_fill(~mask, 0)
        den = exps.sum(-1, keepdim=True)
        if bool(torch.any(den == 0)):
            raise ValueError("fully masked softmax row")
        p = (exps * Q) // den
        p.scatter_add_(-1, argmax, Q - p.sum(-1, keepdim=True))
        return p

    def rope(self, x: torch.Tensor, kind: str) -> torch.Tensor:
        # [head, sequence, 64], rotate first/second 32 coordinates.
        length = x.shape[-2]
        cos = self.lut[f"rope_{kind}_cos_q16"][:length][None, :, :]
        sin = self.lut[f"rope_{kind}_sin_q16"][:length][None, :, :]
        a, b = x[..., :32], x[..., 32:]
        guard_product(maxabs(x), Q, 2, label="RoPE complex product")
        first = ((a * cos) - (b * sin)) >> 16
        second = ((b * cos) + (a * sin)) >> 16
        return torch.cat((first, second), -1)

    def attention(self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor,
                  valid: torch.Tensor, sliding: bool) -> torch.Tensor:
        # each [16, sequence, 64] Q16.  Head dimension exactly 64 => scale 1/8.
        h, n, d = q.shape
        if (h, d) != (16, 64) or k.shape != q.shape or v.shape != q.shape:
            raise ValueError("attention shape")
        guard_product(d, maxabs(q), maxabs(k), label="attention QK accumulator")
        scores = (q @ k.transpose(-1, -2)) >> 19
        mask = valid[None, None, :].expand(h, n, n)
        if sliding:
            position = torch.arange(n)
            mask = mask & ((position[:, None] - position[None, :]).abs()[None, :, :] <= 64)
        p = self.softmax(scores, mask)
        guard_product(n, Q, maxabs(v), label="attention probability-value accumulator")
        output = (p @ v) >> 16
        self.attn_mac_count += 2 * h * n * n * d
        return output

    def encoder_layer(self, x: torch.Tensor, i: int, valid: torch.Tensor) -> torch.Tensor:
        base = f"encoder.layers.{i}."
        normed = x if i == 0 else self.norm(x, base + "attn_norm.weight")
        n = x.shape[0]
        qkv = self.mm(normed, base + "attn.Wqkv.weight").reshape(n, 3, 16, 64)
        q, k, v = [qkv[:, j].transpose(0, 1) for j in range(3)]
        sliding = i % 3 != 0
        kind = "sliding" if sliding else "full"
        att = self.attention(self.rope(q, kind), self.rope(k, kind), v, valid, sliding)
        att = att.transpose(0, 1).reshape(n, 1024)
        x = checked_add(x, self.mm(att, base + "attn.Wo.weight"), "encoder attention residual")
        mid = self.norm(x, base + "mlp_norm.weight")
        wi = self.mm(mid, base + "mlp.Wi.weight")
        left, gate = wi.chunk(2, -1)
        gelu = self.gelu(left)
        guard_product(maxabs(gelu), maxabs(gate), label="encoder GLU product")
        activated = (gelu * gate) >> 16
        x = checked_add(x, self.mm(activated, base + "mlp.Wo.weight"), "encoder MLP residual")
        self.drop_prefix(base)
        return x

    def head_layer(self, x: torch.Tensor, i: int, valid: torch.Tensor) -> torch.Tensor:
        base = f"head.layers.{i}."
        n = x.shape[0]
        normed = self.norm(x, base + "norm1.weight", base + "norm1.bias")
        qkv = self.mm(normed, base + "self_attn.in_proj_weight", base + "self_attn.in_proj_bias").reshape(n, 3, 16, 64)
        q, k, v = [qkv[:, j].transpose(0, 1) for j in range(3)]
        att = self.attention(q, k, v, valid, False).transpose(0, 1).reshape(n, 1024)
        x = checked_add(x, self.mm(att, base + "self_attn.out_proj.weight", base + "self_attn.out_proj.bias"),
                        "head attention residual")
        mid = self.norm(x, base + "norm2.weight", base + "norm2.bias")
        ffn = self.mm(mid, base + "linear1.weight", base + "linear1.bias")
        ffn = torch.maximum(ffn, torch.zeros_like(ffn))
        x = checked_add(x, self.mm(ffn, base + "linear2.weight", base + "linear2.bias"), "head FFN residual")
        self.drop_prefix(base)
        return x

    def scorer(self, x: torch.Tensor, markers: list[int], marker_mask: list[int]) -> tuple[torch.Tensor, torch.Tensor]:
        ix = torch.tensor(markers, dtype=torch.int64).clamp(min=0)
        marker = x[ix]
        y = self.norm(marker, "scorer.0.weight", "scorer.0.bias")
        y = self.gelu(self.mm(y, "scorer.1.weight", "scorer.1.bias"))
        logits = self.mm(y, "scorer.3.weight", "scorer.3.bias").flatten()
        valid = torch.tensor(marker_mask, dtype=torch.bool)
        logits = logits.masked_fill(~valid, -10000 * Q)
        guard_product(maxabs(logits), Q, label="temperature calibration numerator")
        calibrated = div_trunc(logits * Q, TEMPERATURE_Q16)
        probabilities = self.softmax(calibrated[None, :], valid[None, :]).flatten()
        return logits, probabilities

    def action(self, x: torch.Tensor, logits: torch.Tensor, marker_mask: list[int]) -> torch.Tensor:
        valid = torch.tensor(marker_mask, dtype=torch.bool)
        p = self.softmax(logits[None, :], valid[None, :]).flatten()
        top2 = torch.topk(p, min(2, len(p))).values
        if len(top2) == 1:
            top2 = torch.cat((top2, torch.zeros_like(top2)))
        count = max(2, int(valid.sum()))
        if count != 2:
            raise ValueError("this pinned noul:2 arithmetic profile requires two markers")
        logp = self.lut["log_q16"][p.clamp(0, Q)]
        ent_q16 = -int(((p * logp) >> 16).sum()) * Q // LOG_TWO_Q16
        feats = torch.tensor([int(top2[0]), int(top2[0] - top2[1]), ent_q16, count * Q // 255], dtype=torch.int64)
        joined = torch.cat((x[0], feats))[None, :]
        z = self.gelu(self.mm(joined, "act_head.0.weight", "act_head.0.bias"))
        return self.mm(z, "act_head.2.weight", "act_head.2.bias").flatten()

    def run_one(self, name: str, batch: dict, output_dir: Path, *, input_file_sha: str,
                reference: dict | None = None) -> dict:
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(output_dir, 0o700)
        fields = ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")
        batch_binding = hashlib.sha256(json.dumps({k: batch[k] for k in fields}, sort_keys=True,
                                                  separators=(",", ":")).encode()).hexdigest()
        export_hash = sha(self.root / "manifest.json")
        source_hash = sha(Path(__file__))
        ids = torch.tensor(batch["input_ids"], dtype=torch.int64).reshape(-1)
        valid = torch.tensor(batch["attention_mask"], dtype=torch.bool).reshape(-1)
        markers = np.asarray(batch["marker_pos"]).reshape(-1).tolist()
        marker_mask = np.asarray(batch["marker_mask"]).reshape(-1).tolist()
        qtype = int(np.asarray(batch["qtype"]).reshape(-1)[0])
        if len(ids) > 320 or len(ids) < 2 or len(ids) != len(valid):
            raise ValueError("input sequence length/padding")
        if bool(torch.any(ids < 0)) or bool(torch.any(ids >= 50368)) or qtype not in (0, 1, 2):
            raise ValueError("input token/type range")
        for m, enabled in zip(markers, marker_mask):
            if enabled and not (0 <= m < len(ids)):
                raise ValueError("marker position range")
        t0 = time.perf_counter()
        start_dense, start_attn, start_matmul = self.mac_count, self.attn_mac_count, self.matmul_count
        x = self.get("encoder.embeddings.tok_embeddings.weight")[ids]
        x = self.norm(x, "encoder.embeddings.norm.weight")
        trace: list[dict] = []

        def checkpoint(stage: str, value: torch.Tensor, start: float):
            path = output_dir / f"{name}.{stage}.npy"
            _save_npy(path, value.numpy())
            record = {"stage": stage, "shape": list(value.shape), "sha256": sha(path),
                      "minQ16": int(value.min()), "maxQ16": int(value.max()),
                      "elapsedSeconds": round(time.perf_counter() - start, 6),
                      "denseMACsCumulative": self.mac_count - start_dense,
                      "attentionMACsCumulative": self.attn_mac_count - start_attn}
            if reference and stage in reference:
                f = torch.as_tensor(reference[stage], dtype=torch.float64)
                if f.shape == value.shape:
                    delta = value.to(torch.float64) / Q - f
                    record["floatErrorMaxAbs"] = float(delta.abs().max())
                    record["floatErrorMeanAbs"] = float(delta.abs().mean())
            trace.append(record)
            _write_json(output_dir / f"{name}.trace.json", {"version": VERSION,
                "batchBindingSha256": batch_binding, "exportManifestSha256": export_hash,
                "runtimeSourceSha256": source_hash, "stages": trace})
            print(f"{name} {stage}: {record['elapsedSeconds']:.3f}s min/max {record['minQ16']}/{record['maxQ16']}", flush=True)

        checkpoint("embeddings", x, t0)
        for i in range(28):
            t = time.perf_counter()
            x = self.encoder_layer(x, i, valid)
            checkpoint(f"encoder_{i:02d}", x, t)
        t = time.perf_counter()
        x = self.norm(x, "encoder.final_norm.weight")
        checkpoint("encoder_final_norm", x, t)
        x = checked_add(x, self.get("type_emb.weight")[qtype], "typed embedding residual")
        checkpoint("typed_embedding", x, time.perf_counter())
        for i in range(2):
            t = time.perf_counter()
            x = self.head_layer(x, i, valid)
            checkpoint(f"head_{i}", x, t)
        logits, probabilities = self.scorer(x, markers, marker_mask)
        act_logits = self.action(x, logits, marker_mask)
        result = {
            "version": VERSION, "name": name, "inputTokenSha256": tensor_hash(ids),
            "inputFileSha256": input_file_sha, "batchBindingSha256": batch_binding,
            "exportManifestSha256": export_hash, "runtimeSourceSha256": source_hash,
            "rawLogitsQ16": logits.tolist(), "probabilitiesQ16": probabilities.tolist(),
            "actLogitsQ16": act_logits.tolist(),
            "optionFlagsAtThreshold": [bool(int(p) >= THRESHOLD_Q16) for p in probabilities],
            "yesOptionIndex": 1, "yesSupportProbabilityQ16": int(probabilities[1]),
            "yesSupportAtThreshold": bool(int(probabilities[1]) >= THRESHOLD_Q16),
            "yesSupportPpmRounded4": 100 * round_even_ratio(int(probabilities[1]) * 10000, Q),
            "consumerRounding": "nearest-even four decimals, then parts per million",
            "consumerThresholdPpm": 550000,
            "consumerYesSupportAtThreshold": 100 * round_even_ratio(int(probabilities[1]) * 10000, Q) >= 550000,
            "thresholdQ16": THRESHOLD_Q16, "temperatureQ16": TEMPERATURE_Q16,
            "denseMACs": self.mac_count - start_dense, "attentionMACs": self.attn_mac_count - start_attn,
            "matmulCount": self.matmul_count - start_matmul, "elapsedSeconds": time.perf_counter() - t0,
            "traceSha256": sha(output_dir / f"{name}.trace.json"),
        }
        result["resultCommitmentSha256"] = hashlib.sha256(json.dumps(result, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        _write_json(output_dir / f"{name}.result.json", result)
        return result


def _write_json(path: Path, content: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(content, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("export", "run", "self-test"))
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EXPORT.parent / "run-v1")
    parser.add_argument("--name", default="chemistry")
    args = parser.parse_args()
    if args.command == "export":
        export(args.model, args.export_dir)
        return
    if args.command == "self-test":
        x = torch.tensor([[-65537, -65536, -32768, -1, 0, 1, 32768, 65536, 65537]], dtype=torch.int64)
        for s in range(4):
            z = round_even_pow2(x, torch.tensor([s]))
            expected = torch.tensor(np.rint(x.numpy().astype(np.float64) / (1 << s)).astype(np.int64))
            assert torch.equal(z, expected), (s, z, expected)
        print("integer nearest-even quantizer self-test passed")
        return
    if args.input is None:
        raise SystemExit("--input frozen token JSON required")
    rt = Runtime(args.export_dir)
    data = json.loads(args.input.read_text())
    if "variants" in data:
        batches = {}
        for variant in data["variants"]:
            key = variant["sourceKey"]
            batched = variant["batch"]
            for j in range(len(batched["input_ids"])):
                batches[f"{key}.q{j}"] = {field: batched[field][j] for field in
                    ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")}
    elif "batch" in data:
        batches = {args.name: data["batch"]}
    elif "items" in data:
        batches = {str(k): v["tokens"]["batch"] if "tokens" in v else v["batch"] for k, v in data["items"].items()}
    else:
        batches = {args.name: data}
    for name, batch in batches.items():
        print(json.dumps(rt.run_one(name, batch, args.output_dir, input_file_sha=sha(args.input)), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
