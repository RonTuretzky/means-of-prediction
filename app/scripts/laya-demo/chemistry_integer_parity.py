#!/usr/bin/env python3
"""Compare frozen Chemistry integer traces with unchanged stock float32 hooks.

Only raw input IDs, 28 encoder/2 head hidden tensors and raw output logits are
read.  Labels and expected outcomes are deliberately ignored.  This report is
numeric parity evidence, not an inference proof or EVM cost measurement.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch


Q = 65536
SOURCES = ("reuters_early", "ap", "reuters_later")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--float-dir", type=Path, default=Path("/Users/wk/.local/share/means-of-prediction/chemistry-demo-20261021"))
    p.add_argument("--integer-dir", type=Path, default=Path("/Users/wk/.local/share/means-of-prediction/laya-chemistry-integer-20261021/run-v1"))
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    semantics_path = args.float_dir / "probability-semantics.private.json"
    semantics = json.loads(semantics_path.read_text())
    stock_probs = {v["sourceKey"]: v["qAB"] for v in semantics["variants"]}
    cases = []
    for source in SOURCES:
        float_path = args.float_dir / f"{source}-float-trace.private.pt"
        original = torch.load(float_path, map_location="cpu", weights_only=False)
        bound = original["boundBatch"]
        for qi in range(3):
            name = f"{source}.q{qi}"
            result_path = args.integer_dir / f"{name}.result.json"
            result = json.loads(result_path.read_text())
            ids = torch.as_tensor(bound["input_ids"][qi], dtype=torch.int64)
            matching_ids = hashlib.sha256(ids.numpy().tobytes()).hexdigest() == result["inputTokenSha256"]
            if not matching_ids:
                raise ValueError(f"float/integer input mismatch: {name}")
            stages = []
            for layer in range(28):
                s = f"encoder_{layer:02d}"
                ref = original["layers"][f"encoder.layers.{layer}"][qi].numpy().astype(np.float64)
                integer = np.load(args.integer_dir / f"{name}.{s}.npy").astype(np.float64) / Q
                if integer.shape != ref.shape:
                    raise ValueError(f"layer shape mismatch: {name}/{s}")
                diff = np.abs(integer - ref)
                stages.append({"stage": s, "maxAbs": float(diff.max()), "meanAbs": float(diff.mean()),
                               "referenceRange": [float(ref.min()), float(ref.max())]})
            for layer in range(2):
                s = f"head_{layer}"
                ref = original["layers"][f"head.layers.{layer}"][qi].numpy().astype(np.float64)
                integer = np.load(args.integer_dir / f"{name}.{s}.npy").astype(np.float64) / Q
                if integer.shape != ref.shape:
                    raise ValueError(f"layer shape mismatch: {name}/{s}")
                diff = np.abs(integer - ref)
                stages.append({"stage": s, "maxAbs": float(diff.max()), "meanAbs": float(diff.mean()),
                               "referenceRange": [float(ref.min()), float(ref.max())]})
            raw_float = original["rawModelOutputs"][0][qi].double()
            act_float = original["rawModelOutputs"][1][qi].double()
            raw_int = torch.tensor(result["rawLogitsQ16"], dtype=torch.float64) / Q
            act_int = torch.tensor(result["actLogitsQ16"], dtype=torch.float64) / Q
            question = ("q", "A", "B")[qi]
            recorded = stock_probs[source][question]
            float_yes = recorded["trueProbabilityUnroundedFloat32"]
            integer_yes = result["probabilitiesQ16"][1] / Q
            integer_ppm = result.get("yesSupportPpmRounded4")
            if integer_ppm is None:
                integer_ppm = 100 * round(integer_yes * 10000)
            cases.append({
                "name": name, "source": source, "questionIndex": qi,
                "inputIdsExact": matching_ids, "sequenceLength": len(ids),
                "integerResultSHA256": sha(result_path), "stockFloatTraceSHA256": sha(float_path),
                "stageCount": len(stages), "stages": stages,
                "largestMeanAbsStage": max(stages, key=lambda x: x["meanAbs"])["stage"],
                "largestMeanAbs": max(x["meanAbs"] for x in stages),
                "largestMaxAbsStage": max(stages, key=lambda x: x["maxAbs"])["stage"],
                "largestMaxAbs": max(x["maxAbs"] for x in stages),
                "floatRawLogits": raw_float.tolist(), "integerRawLogits": raw_int.tolist(),
                "rawLogitMaxAbs": float((raw_int - raw_float).abs().max()),
                "floatActionLogits": act_float.tolist(), "integerActionLogits": act_int.tolist(),
                "actionLogitMaxAbs": float((act_int - act_float).abs().max()),
                "floatYesProbability": float_yes, "integerYesProbability": integer_yes,
                "yesProbabilityAbsoluteError": abs(float_yes - integer_yes),
                "floatYesRoundedPpm": recorded["returnedRoundedProbabilityPPM"],
                "integerYesRoundedPpm": integer_ppm,
                "yesRoundedPpmAbsoluteError": abs(recorded["returnedRoundedProbabilityPPM"] - integer_ppm),
                "floatYesAt55Percent": float_yes >= .55,
                "integerYesAt55Percent": integer_yes >= .55,
            })
    report = {
        "schema": "laya-chemistry-integer-parity-v1",
        "caseCount": len(cases), "floatSource": "unchanged pinned alert-student-base float32 model",
        "integerSource": "derived laya-int16-q16-v1 model; CPU integer replay",
        "stageCountPerCase": 30, "allInputIdsExact": all(x["inputIdsExact"] for x in cases),
        "allYesThresholdFlagsMatch": all(x["floatYesAt55Percent"] == x["integerYesAt55Percent"] for x in cases),
        "maxYesProbabilityAbsoluteError": max(x["yesProbabilityAbsoluteError"] for x in cases),
        "maxYesRoundedPpmAbsoluteError": max(x["yesRoundedPpmAbsoluteError"] for x in cases),
        "maxRawLogitAbsError": max(x["rawLogitMaxAbs"] for x in cases),
        "maxHeadMeanAbsError": max(s["meanAbs"] for c in cases for s in c["stages"] if s["stage"].startswith("head")),
        "cases": cases,
        "stockProbabilitySemanticsSHA256": sha(semantics_path),
        "limits": ["Float hooks do not include final encoder norm or typed embedding; these integer stages are traced but unpaired.",
                   "Action head is compared at final logits; its internal layers were not float-hooked.",
                   "Numeric/threshold parity does not prove onchain execution, gas viability, or cryptographic soundness."],
    }
    out = args.output or args.integer_dir / "parity.private.json"
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, out)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, sort_keys=True))
    print(json.dumps({"report": str(out), "sha256": sha(out)}))


if __name__ == "__main__":
    main()
