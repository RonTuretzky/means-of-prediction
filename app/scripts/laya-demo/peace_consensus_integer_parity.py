#!/usr/bin/env python3
"""Compare one frozen Peace report's integer q/A/B with unchanged stock float hooks.

This reads already-frozen model outputs solely for error measurement. It never
selects inputs, alters calibration, or supplies expected values to execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch

Q = 65536
QUESTIONS = ("q", "A", "B")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(8 << 20), b""):
            h.update(part)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--peace-dir", type=Path, required=True)
    parser.add_argument("--integer-dir", type=Path, required=True)
    parser.add_argument("--source", required=True, choices=("bbc", "cnn", "abc", "rfi"))
    parser.add_argument("--expected-frozen-sha", required=True)
    parser.add_argument("--expected-tokens-sha", required=True)
    parser.add_argument("--expected-reference-sha", required=True)
    parser.add_argument("--expected-float-trace-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen_path = args.peace_dir / "frozen.private.json"
    tokens_path = args.peace_dir / "tokens.private.json"
    float_path = args.peace_dir / f"{args.source}-float-trace.private.pt"
    reference_path = args.peace_dir / "reference-results.private.json"
    frozen = json.loads(frozen_path.read_text())
    tokens = json.loads(tokens_path.read_text())
    reference = json.loads(reference_path.read_text())
    original = torch.load(float_path, map_location="cpu", weights_only=False)
    if (sha(frozen_path) != args.expected_frozen_sha or
        sha(tokens_path) != args.expected_tokens_sha or
        sha(reference_path) != args.expected_reference_sha or
        sha(float_path) != args.expected_float_trace_sha):
        raise ValueError("precommitted parity file SHA mismatch")
    if frozen["tokensSHA256"] != sha(tokens_path) or original["frozenSHA256"] != sha(frozen_path):
        raise ValueError("original freeze pin mismatch")
    if reference["frozenSHA256"] != sha(frozen_path) or tokens["questionOrder"] != list(QUESTIONS):
        raise ValueError("reference freeze/order mismatch")
    matching = [v for v in tokens["variants"] if v["sourceKey"] == args.source]
    if len(tokens["variants"]) != 4 or len(matching) != 1:
        raise ValueError("expected exactly four frozen sources and one selected source")
    source_index = [v["sourceKey"] for v in tokens["variants"]].index(args.source)
    batch = matching[0]["batch"]
    if original["questionOrder"] != list(QUESTIONS):
        raise ValueError("float question order mismatch")
    if any(original["boundBatch"][k].tolist() != batch[k] for k in
           ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")):
        raise ValueError("float batch differs from frozen integer input")
    answers = reference["outputs"][source_index]["answer"]["answers"]
    temperature = torch.tensor(1.1089085340499878, dtype=torch.float32)
    float_yes = torch.softmax(original["rawModelOutputs"][0] / temperature, dim=-1)[:, 1]
    cases = []
    for qi, question in enumerate(QUESTIONS):
        name = f"{args.source}.q{qi}"
        result_path = args.integer_dir / f"{name}.result.json"
        result = json.loads(result_path.read_text())
        ids = np.asarray(batch["input_ids"][qi], dtype="<i8")
        if result["inputTokenSha256"] != hashlib.sha256(ids.tobytes()).hexdigest():
            raise ValueError(f"input IDs differ at {name}")
        valid_mask = np.asarray(batch["attention_mask"][qi], dtype=bool)
        marker_positions = [pos for pos, enabled in zip(batch["marker_pos"][qi],
                                                           batch["marker_mask"][qi], strict=True)
                            if enabled]
        if not marker_positions or any(pos < 0 or pos >= len(ids) or
                                       not valid_mask[pos] for pos in marker_positions):
            raise ValueError(f"invalid frozen markers at {name}")
        stages = []
        for group, count, stage_prefix, hook_prefix in (
            ("encoder", 28, "encoder_", "encoder.layers."),
            ("head", 2, "head_", "head.layers."),
        ):
            for i in range(count):
                stage = f"{stage_prefix}{i:02d}" if group == "encoder" else f"{stage_prefix}{i}"
                ref = original["layers"][f"{hook_prefix}{i}"][qi].numpy().astype(np.float64)
                actual = np.load(args.integer_dir / f"{name}.{stage}.npy").astype(np.float64) / Q
                if actual.shape != ref.shape:
                    raise ValueError(f"layer shape differs at {name}/{stage}")
                error = np.abs(actual - ref)
                stages.append({"stage": stage, "maxAbs": float(error.max()),
                               "meanAbs": float(error.mean()),
                               "validTokenMaxAbs": float(error[valid_mask].max()),
                               "markerMaxAbs": float(error[marker_positions].max()),
                               "markerMeanAbs": float(error[marker_positions].mean())})
        raw_float = original["rawModelOutputs"][0][qi].double()
        raw_integer = torch.tensor(result["rawLogitsQ16"], dtype=torch.float64) / Q
        act_float = original["rawModelOutputs"][1][qi].double()
        act_integer = torch.tensor(result["actLogitsQ16"], dtype=torch.float64) / Q
        rounded_ppm = int(round(float(answers[question]["noul"]) * 1_000_000))
        if rounded_ppm != 100 * round(float(float_yes[qi]) * 10_000):
            raise ValueError(f"stock rounded probability mismatch at {name}")
        cases.append({"name": name, "question": question,
                      "inputIdsExact": True, "sequenceLength": len(ids),
                      "floatTraceSHA256": sha(float_path),
                      "integerResultSHA256": sha(result_path),
                      "stageCount": len(stages), "stages": stages,
                      "floatRawLogits": raw_float.tolist(),
                      "integerRawLogits": raw_integer.tolist(),
                      "rawLogitMaxAbs": float((raw_integer - raw_float).abs().max()),
                      "floatActionLogits": act_float.tolist(),
                      "integerActionLogits": act_integer.tolist(),
                      "actionLogitMaxAbs": float((act_integer - act_float).abs().max()),
                      "floatYesUnrounded": float(float_yes[qi]),
                      "integerYesQ16": result["probabilitiesQ16"][1],
                      "integerYesUnrounded": result["probabilitiesQ16"][1] / Q,
                      "yesProbabilityAbsoluteError": abs(float(float_yes[qi]) - result["probabilitiesQ16"][1] / Q),
                      "floatYesRoundedPpm": rounded_ppm,
                      "integerYesRoundedPpm": result["yesSupportPpmRounded4"],
                      "yesRoundedPpmAbsoluteError": abs(rounded_ppm - result["yesSupportPpmRounded4"]),
                      "floatYesAt55Percent": rounded_ppm >= 550000,
                      "integerYesAt55Percent": result["consumerYesSupportAtThreshold"]})
    report = {"schema": "laya-peace-four-report-integer-parity-v1", "source": args.source,
              "caseCount": len(cases), "stageCountPerCase": 30,
              "runtimeSourceSHA256": cases and json.loads((args.integer_dir / f"{args.source}.q0.result.json").read_text())["runtimeSourceSha256"],
              "exportManifestSHA256": json.loads((args.integer_dir / f"{args.source}.q0.result.json").read_text())["exportManifestSha256"],
              "frozenSHA256": sha(frozen_path), "tokensSHA256": sha(tokens_path),
              "referenceResultsSHA256": sha(reference_path), "floatTraceSHA256": sha(float_path),
              "allInputIdsExact": all(c["inputIdsExact"] for c in cases),
              "allThresholdFlagsMatch": all(c["floatYesAt55Percent"] == c["integerYesAt55Percent"] for c in cases),
              "maxRawLogitAbsError": max(c["rawLogitMaxAbs"] for c in cases),
              "maxActionLogitAbsError": max(c["actionLogitMaxAbs"] for c in cases),
              "maxYesProbabilityAbsoluteError": max(c["yesProbabilityAbsoluteError"] for c in cases),
              "maxYesRoundedPpmAbsoluteError": max(c["yesRoundedPpmAbsoluteError"] for c in cases),
              "maxLayerMeanAbsError": max(s["meanAbs"] for c in cases for s in c["stages"]),
              "maxLayerAbsError": max(s["maxAbs"] for c in cases for s in c["stages"]),
              "maxMarkerLayerAbsError": max(s["markerMaxAbs"] for c in cases for s in c["stages"]),
              "cases": cases,
              "limits": ["Float hooks cover 28 encoder and two head layers; integer-only embeddings, final encoder norm and typed embedding have no float hook.",
                         "Numeric parity does not prove EVM inference, independent administrative operators or publisher credibility."]}
    tmp = args.output.with_suffix(args.output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, sort_keys=True))
    print(json.dumps({"path": str(args.output), "sha256": sha(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
