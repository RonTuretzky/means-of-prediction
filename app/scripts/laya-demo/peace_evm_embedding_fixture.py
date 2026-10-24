#!/usr/bin/env python3
"""Export private EVM fixtures for the exact Peace embedding prefix; no full inference.

Verify existing pins before reading tensors. Recompute only Runtime.norm, compare it
element-for-element with all twelve prior embedding tensors, then export input weights
and output SHA256 oracles. Solidity must compute outputs; no answer tensor is supplied
to the Solidity kernel. Nothing is downloaded or written to the original artifacts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

BASE = Path("/Users/wk/.local/share/means-of-prediction")
RUNTIME_SHA = "b06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766"
EXPORT_SHA = "b863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d"
RECEIPT_SHA = "db26d245a6da48b9e0693e4bf62ee6e5a6ddc698fb1a736241e880e0636c7c64"
TOKENS_SHA = "ceb713fe14121f64c362c07aaae26c15b3eb9ae742f60a060bde259f21c58c17"
FROZEN_SHA = "02e05c7f707d020ecbd91c2af029ef6524c1179a13d3c2c33c31378ec39f054c"
MODEL_SHA = "5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pinned(path, expected):
    require(sha(path) == expected, f"Pin mismatch: {path}")


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evm_array_sha(array):
    # Solidity sha256(abi.encodePacked(int256[])): consecutive signed 32-byte words.
    h = hashlib.sha256()
    for value in array.reshape(-1):
        h.update(int(value).to_bytes(32, "big", signed=True))
    return "0x" + h.hexdigest()


def write(path, data):
    payload = json.dumps(data, sort_keys=True, indent=2) + "\n"
    path.write_text(payload)
    path.chmod(0o600)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reference", type=Path, default=BASE / "peace-four-report-demo-20261021")
    p.add_argument("--export", type=Path, default=BASE / "laya-chemistry-integer-20261021/export-v1")
    args = p.parse_args()
    runtime = Path(__file__).with_name("chemistry_integer_runtime.py")
    pinned(runtime, RUNTIME_SHA)
    pinned(args.export / "manifest.json", EXPORT_SHA)
    pinned(args.reference / "tokens.private.json", TOKENS_SHA)
    pinned(args.reference / "frozen.private.json", FROZEN_SHA)
    run = args.reference / "integer-run-v1"
    pinned(run / "operator-receipt.private.json", RECEIPT_SHA)
    import numpy as np
    import torch
    from chemistry_integer_runtime import Runtime
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    manifest = json.loads((args.export / "manifest.json").read_text())
    require(manifest["sourceSha256"] == MODEL_SHA and manifest["version"] == "laya-int16-q16-v1",
            "Wrong model/arithmetic")
    records = manifest["tensors"]
    names = ("encoder.embeddings.tok_embeddings.weight", "encoder.embeddings.norm.weight")
    arrays = []
    for name in names:
        record = records[name]
        part = record["files"]["q"]
        f = args.export / part["path"]
        pinned(f, part["sha256"])
        a = np.load(f, mmap_mode="r", allow_pickle=False)
        require(a.dtype == np.dtype("int32") and list(a.shape) == record["shape"], "Weight shape/dtype")
        arrays.append(a)
    embedding, gamma = arrays
    require(embedding.shape == (50368, 1024) and gamma.shape == (1024,), "Wrong model dimensions")
    tokens = json.loads((args.reference / "tokens.private.json").read_text())
    frozen = json.loads((args.reference / "frozen.private.json").read_text())
    receipt = json.loads((run / "operator-receipt.private.json").read_text())
    require(tokens["questionOrder"] == ["q", "A", "B"] and frozen["tokensSHA256"] == TOKENS_SHA,
            "Frozen question/token binding")
    unique = sorted({i for v in tokens["variants"] for row in v["batch"]["input_ids"] for i in row})
    packed_rows = embedding[unique].astype(">i4").tobytes()
    packed_gamma = gamma.astype(">i4").tobytes()
    args.output.mkdir(parents=True, mode=0o700, exist_ok=True)
    args.output.chmod(0o700)
    write(args.output / "weights.private.json", {
        "modelSHA256": "0x" + MODEL_SHA, "runtimeSHA256": "0x" + RUNTIME_SHA,
        "exportSHA256": "0x" + EXPORT_SHA, "arithmetic": manifest["version"],
        "tableIds": unique, "packedRows": "0x" + packed_rows.hex(),
        "packedGamma": "0x" + packed_gamma.hex(),
        "rowsSHA256": "0x" + hashlib.sha256(packed_rows).hexdigest(),
        "gammaSHA256": "0x" + hashlib.sha256(packed_gamma).hexdigest(),
    })
    rt = Runtime(args.export)  # Only small LUTs and normalization gamma; no model forward.
    cases = []
    for v in tokens["variants"]:
        source = v["sourceKey"]
        frozen_v = next(x for x in frozen["items"] if x["sourceKey"] == source)
        require(v["batch"] == frozen_v["batch"], "Batch differs from frozen evidence")
        source_receipt = next(x for x in receipt["sources"] if x["sourceKey"] == source)
        for qi in range(3):
            name = f"{source}.q{qi}"
            bound = {k: v["batch"][k][qi] for k in ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")}
            result = json.loads((run / f"{name}.result.json").read_text())
            trace_path = run / f"{name}.trace.json"
            pinned(trace_path, result["traceSha256"])
            trace = json.loads(trace_path.read_text())
            numerical = {"arithmeticVersion": result["version"], "exportManifestSHA256": EXPORT_SHA,
                "batchBindingSHA256": canonical(bound),
                "orderedStages": [{"stage": s["stage"], "shape": s["shape"], "tensorSHA256": s["sha256"]}
                                  for s in trace["stages"]],
                "rawLogitsQ16": result["rawLogitsQ16"], "probabilitiesQ16": result["probabilitiesQ16"],
                "actionLogitsQ16": result["actLogitsQ16"], "temperatureQ16": result["temperatureQ16"],
                "thresholdQ16": result["thresholdQ16"]}
            pinned_case = next(x for x in source_receipt["cases"] if x["name"] == name)
            require(canonical(numerical) == pinned_case["numericRootSHA256"], "Unpinned stage metadata")
            require(trace["batchBindingSha256"] == canonical(bound) and trace["runtimeSourceSha256"] == RUNTIME_SHA
                    and trace["exportManifestSha256"] == EXPORT_SHA, "Wrong reference context")
            stage = trace["stages"][0]
            require(stage["stage"] == "embeddings", "First stage is not embeddings")
            golden_path = run / f"{name}.embeddings.npy"
            pinned(golden_path, stage["sha256"])
            expected = np.load(golden_path, allow_pickle=False)
            ids = bound["input_ids"]
            require(expected.dtype == np.dtype("int64") and expected.shape == (len(ids), 1024), "Golden dimensions")
            recomputed = rt.norm(torch.from_numpy(embedding[ids].astype(np.int64)), names[1]).numpy()
            require(np.array_equal(recomputed, expected), f"Reference replay mismatch: {name}")
            row = {"name": name, "tokenIds": ids, "expectedSHA256": evm_array_sha(expected),
                   "firstTwoExpectedSHA256": evm_array_sha(expected[:2]),
                   "expectedScalarCount": int(expected.size), "goldenNpySHA256": stage["sha256"],
                   "boundInputSHA256": canonical(bound), "validTokens": sum(bound["attention_mask"])}
            write(args.output / f"{name}.private.json", row)
            cases.append({k: value for k, value in row.items() if k != "tokenIds"})
    require(len(cases) == 12, "Expected all four q/A/B triples")
    report = {"schema": "peace-evm-embedding-fixtures-v1", "modelSHA256": MODEL_SHA,
              "runtimeSHA256": RUNTIME_SHA, "exportSHA256": EXPORT_SHA, "frozenTokensSHA256": TOKENS_SHA,
              "frozenEvidenceSHA256": FROZEN_SHA, "receiptSHA256": RECEIPT_SHA,
              "cases": cases, "uniqueEmbeddingRows": len(unique), "packedWeightBytes": len(packed_rows) + len(packed_gamma),
              "exactReferenceScalars": sum(x["expectedScalarCount"] for x in cases), "fullModelInferenceRun": False,
              "productionWeightAuthentication": False, "source": str(args.reference), "export": str(args.export)}
    write(args.output / "fixture-manifest.private.json", report)
    print(json.dumps({k: report[k] for k in ("exactReferenceScalars", "uniqueEmbeddingRows", "packedWeightBytes", "fullModelInferenceRun")}))


if __name__ == "__main__":
    main()
