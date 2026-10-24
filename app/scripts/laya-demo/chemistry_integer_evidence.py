#!/usr/bin/env python3
"""Audit and bind exported integer weights, frozen inputs, traces and results.

Creates a local commitment inventory only.  This is neither a cryptographic
inference proof nor an onchain gas/correctness certificate.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path


DEFAULT_PRIVATE = Path("/Users/wk/.local/share/means-of-prediction")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(8 << 20), b""):
            h.update(part)
    return h.hexdigest()


def canonical_hash(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def assert_file_hash(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"hash mismatch {path}: {actual} != {expected}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--export-dir", type=Path, default=DEFAULT_PRIVATE / "laya-chemistry-integer-20261021/export-v1")
    p.add_argument("--integer-dir", type=Path, default=DEFAULT_PRIVATE / "laya-chemistry-integer-20261021/run-v2")
    p.add_argument("--replay-dir", type=Path, default=DEFAULT_PRIVATE / "laya-chemistry-integer-20261021/run-v1")
    p.add_argument("--frozen-dir", type=Path, default=DEFAULT_PRIVATE / "chemistry-demo-20261021")
    p.add_argument("--runtime-source", type=Path, default=Path(__file__).with_name("chemistry_integer_runtime.py"))
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    manifest_path = a.export_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["version"] != "laya-int16-q16-v1":
        raise ValueError("arithmetic version")
    export_files = 0
    for name, info in manifest["tensors"].items():
        for component in info["files"].values():
            assert_file_hash(a.export_dir / component["path"], component["sha256"])
            export_files += 1
    for name, info in manifest["luts"].items():
        assert_file_hash(a.export_dir / f"{name}.npy", info["sha256"])
        export_files += 1
    token_file = a.frozen_dir / "tokens.private.json"
    tokens = json.loads(token_file.read_text())
    source_hash = sha(a.runtime_source)
    manifest_hash = sha(manifest_path)
    token_hash = sha(token_file)
    semantics = json.loads((a.frozen_dir / "probability-semantics.private.json").read_text())
    profile_hash = semantics["profileSHA256"]
    cases = []
    sources = []
    for variant in tokens["variants"]:
        source = variant["sourceKey"]
        sources.append({"sourceKey": source, "inputHash": variant["gateHashes"]["inputHash"],
                        "tokenIdsHash": variant["gateHashes"]["tokenIdsHash"],
                        "frozenExactInputSHA256": variant["inputSHA256"]})
        for qi, question in enumerate(("q", "A", "B")):
            name = f"{source}.q{qi}"
            path = a.integer_dir / f"{name}.result.json"
            result = json.loads(path.read_text())
            if result["name"] != name or result["version"] != manifest["version"]:
                raise ValueError(f"case/version mismatch {name}")
            if result["inputFileSha256"] != token_hash or result["exportManifestSha256"] != manifest_hash:
                raise ValueError(f"input/export binding mismatch {name}")
            if result["runtimeSourceSha256"] != source_hash:
                raise ValueError(f"runtime source binding mismatch {name}")
            b = variant["batch"]
            fields = ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")
            bound = {field: b[field][qi] for field in fields}
            if canonical_hash(bound) != result["batchBindingSha256"]:
                raise ValueError(f"batch fields mismatch {name}")
            commitment = result.pop("resultCommitmentSha256")
            if canonical_hash(result) != commitment:
                raise ValueError(f"result commitment mismatch {name}")
            result["resultCommitmentSha256"] = commitment
            trace_path = a.integer_dir / f"{name}.trace.json"
            assert_file_hash(trace_path, result["traceSha256"])
            trace = json.loads(trace_path.read_text())
            if trace["batchBindingSha256"] != result["batchBindingSha256"] or len(trace["stages"]) != 33:
                raise ValueError(f"trace binding or stage count {name}")
            for stage in trace["stages"]:
                assert_file_hash(a.integer_dir / f"{name}.{stage['stage']}.npy", stage["sha256"])
            ordered_tensors = [{"stage": stage["stage"], "shape": stage["shape"],
                                "tensorSHA256": stage["sha256"]} for stage in trace["stages"]]
            numerical = {"arithmeticVersion": result["version"],
                         "exportManifestSHA256": manifest_hash, "batchBindingSHA256": result["batchBindingSha256"],
                         "orderedStages": ordered_tensors,
                         "rawLogitsQ16": result["rawLogitsQ16"],
                         "probabilitiesQ16": result["probabilitiesQ16"],
                         "actionLogitsQ16": result["actLogitsQ16"],
                         "temperatureQ16": result["temperatureQ16"],
                         "thresholdQ16": result["thresholdQ16"]}
            numeric_root = canonical_hash(numerical)
            execution_root = canonical_hash({"runtimeSourceSHA256": source_hash, "numericRootSHA256": numeric_root})
            previous = json.loads((a.replay_dir / f"{name}.result.json").read_text())
            previous_trace = json.loads((a.replay_dir / f"{name}.trace.json").read_text())
            replay_numerical = dict(numerical)
            replay_numerical["orderedStages"] = [{"stage": s["stage"], "shape": s["shape"],
                                                    "tensorSHA256": s["sha256"]} for s in previous_trace["stages"]]
            replay_numerical.update(rawLogitsQ16=previous["rawLogitsQ16"],
                                    probabilitiesQ16=previous["probabilitiesQ16"],
                                    actionLogitsQ16=previous["actLogitsQ16"],
                                    temperatureQ16=previous["temperatureQ16"],
                                    thresholdQ16=previous["thresholdQ16"])
            replay_root = canonical_hash(replay_numerical)
            if replay_root != numeric_root:
                raise ValueError(f"numerical replay mismatch {name}")
            cases.append({"name": name, "question": question, "sourceKey": source,
                          "resultCommitmentSha256": commitment, "resultFileSHA256": sha(path),
                          "traceSHA256": result["traceSha256"],
                          "deterministicNumericRootSHA256": numeric_root,
                          "deterministicExecutionRootSHA256": execution_root,
                          "priorReplayNumericRootSHA256": replay_root,
                          "priorReplayExact": replay_root == numeric_root,
                          "yesSupportPpmRounded4": result["yesSupportPpmRounded4"],
                          "yesSupportAtThreshold": result["consumerYesSupportAtThreshold"],
                          "denseMACs": result["denseMACs"], "attentionMACs": result["attentionMACs"],
                          "cpuElapsedSeconds": result["elapsedSeconds"]})
    parity_path = a.integer_dir / "parity.private.json"
    parity = json.loads(parity_path.read_text())
    if parity["caseCount"] != 9 or not parity["allInputIdsExact"]:
        raise ValueError("incomplete parity report")
    report = {
        "schema": "laya-chemistry-integer-cpu-evidence-v1",
        "arithmeticVersion": manifest["version"],
        "originalWeightsSHA256": manifest["sourceSha256"],
        "originalAgentConfigSHA256": manifest["agentConfigSha256"],
        "originalEncoderConfigSHA256": manifest["encoderConfigSha256"],
        "originalProfileSHA256": profile_hash,
        "runtimeSourceSHA256": source_hash, "exportManifestSHA256": manifest_hash,
        "frozenTokenFileSHA256": token_hash,
        "frozenEvidenceSHA256": sha(a.frozen_dir / "frozen.private.json"),
        "floatReferenceResultsSHA256": sha(a.frozen_dir / "reference-results.private.json"),
        "parityReportSHA256": sha(parity_path),
        "exportTensorCount": len(manifest["tensors"]), "verifiedExportFileCount": export_files,
        "caseCount": len(cases), "verifiedStageFileCount": len(cases) * 33,
        "allNinePriorNumericalReplaysExact": all(x["priorReplayExact"] for x in cases),
        "allThresholdFlagsMatchFloat": parity["allYesThresholdFlagsMatch"],
        "maxFloatYesProbabilityError": parity["maxYesProbabilityAbsoluteError"],
        "maxFloatRawLogitError": parity["maxRawLogitAbsError"],
        "measuredDenseMACs": sum(x["denseMACs"] for x in cases),
        "measuredAttentionMACs": sum(x["attentionMACs"] for x in cases),
        "measuredCpuForwardSecondsSum": sum(x["cpuElapsedSeconds"] for x in cases),
        "sources": sources, "cases": cases,
        "variantSupport": {source: {
            question: {"yesSupportPpmRounded4": next(c["yesSupportPpmRounded4"] for c in cases
                        if c["sourceKey"] == source and c["question"] == question),
                       "yesSupportAtThreshold": next(c["yesSupportAtThreshold"] for c in cases
                        if c["sourceKey"] == source and c["question"] == question)}
            for question in ("q", "A", "B")} for source in ("reuters_early", "ap", "reuters_later")},
        "limitations": ["CPU integer executor only; no complete Solidity/EVM execution or transaction gas proof.",
                        "Derived int16/Q16 checkpoint is numerically close but not bit-identical to original float32.",
                        "The q score is diagnostic; only independent A and B YES probabilities are support decisions.",
                        "Threshold agreement on this frozen candidate does not establish worst-case error bounds.",
                        "Overflow prechecks cover main matrix, LayerNorm, attention, RoPE, GLU, residual and calibration paths on this admitted shape; no formal all-input arithmetic safety proof is claimed.",
                        "Manifest/file hash verification is local and does not prove the execution trace cryptographically."],
    }
    report["consensusExecutionRootSHA256"] = canonical_hash({
        "arithmeticVersion": manifest["version"], "runtimeSourceSHA256": source_hash,
        "exportManifestSHA256": manifest_hash, "frozenTokenFileSHA256": token_hash,
        "originalProfileSHA256": profile_hash,
        "orderedCaseExecutionRoots": [x["deterministicExecutionRootSHA256"] for x in cases]})
    report["evidenceCommitmentSHA256"] = canonical_hash(report)
    target = a.output or a.integer_dir / "evidence.private.json"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    print(json.dumps({"evidence": str(target), "sha256": sha(target),
                      "commitment": report["evidenceCommitmentSHA256"],
                      "consensusExecutionRoot": report["consensusExecutionRootSHA256"],
                      "allNinePriorNumericalReplaysExact": report["allNinePriorNumericalReplaysExact"],
                      "caseCount": len(cases), "verifiedExportFileCount": export_files,
                      "measuredDenseMACs": report["measuredDenseMACs"],
                      "measuredAttentionMACs": report["measuredAttentionMACs"],
                      "measuredCpuForwardSecondsSum": report["measuredCpuForwardSecondsSum"]}, sort_keys=True))


if __name__ == "__main__":
    main()
