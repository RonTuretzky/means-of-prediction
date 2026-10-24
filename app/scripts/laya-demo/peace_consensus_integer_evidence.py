#!/usr/bin/env python3
"""Summarize the frozen four-report CPU integer run without scoring new inputs.

This audit reads existing operator receipts and float-parity measurements only.
It does not authenticate operators or decide publisher credibility.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path


SOURCES = ("bbc", "cnn", "abc", "rfi")
QUESTIONS = ("q", "A", "B")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value: bool, message: str):
    if not value:
        raise ValueError(message)


def load(path: Path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, type=Path)
    p.add_argument("--prior-bbc-dir", required=True, type=Path)
    p.add_argument("--source-policy", required=True, type=Path)
    p.add_argument("--runtime-source", required=True, type=Path)
    p.add_argument("--checker-source", required=True, type=Path)
    p.add_argument("--parity-source", required=True, type=Path)
    p.add_argument("--export-manifest", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    run = a.base / "integer-run-v1"
    fpath = a.base / "frozen.private.json"
    tpath = a.base / "tokens.private.json"
    receipt_path = run / "operator-receipt.private.json"
    frozen, tokens, policy, receipt = map(load, (fpath, tpath, a.source_policy, receipt_path))
    require(sha(fpath) == "02e05c7f707d020ecbd91c2af029ef6524c1179a13d3c2c33c31378ec39f054c",
            "four-report frozen evidence pin")
    require(sha(tpath) == "ceb713fe14121f64c362c07aaae26c15b3eb9ae742f60a060bde259f21c58c17",
            "four-report token pin")
    require(sha(a.source_policy) == "464871658b2543c7cfd2fac61ecaf84ec32e437a06265dd12e648ea2750ea3a2",
            "pre-inference policy pin")
    require(sha(a.runtime_source) == "b06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766",
            "unchanged runtime pin")
    require(sha(a.export_manifest) == "b863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d",
            "unchanged export pin")
    require(frozen["sourcePolicy"] == policy and frozen["tokensSHA256"] == sha(tpath),
            "frozen cross-pins")
    require(tuple(policy["sourceOrder"]) == SOURCES and
            tuple(v["sourceKey"] for v in tokens["variants"]) == SOURCES,
            "ordered exact-source set")
    require(receipt["sourceOrder"] == list(SOURCES) and
            receipt["sourcePolicySHA256"] == sha(a.source_policy) and
            receipt["frozenEvidenceSHA256"] == sha(fpath) and
            receipt["parentFrozenTokensSHA256"] == sha(tpath) and
            receipt["runtimeSourceSHA256"] == sha(a.runtime_source) and
            receipt["exportManifestSHA256"] == sha(a.export_manifest),
            "full receipt pins")
    require(receipt["verifiedExportFileCount"] == 337 and
            receipt["verifiedStageFileCount"] == 396 and
            len(receipt["sources"]) == 4,
            "verified inventory")
    prior_tokens = load(a.prior_bbc_dir / "tokens.private.json")
    require(sha(a.prior_bbc_dir / "tokens.private.json") ==
            "030b6e903ae96c335a963151335bc2f33bac31283ad964f7b86bd245716a84fe",
            "prior BBC token pin")
    for field in ("batch", "inputSHA256", "gateHashes"):
        require(tokens["variants"][0][field] == prior_tokens["variants"][0][field],
                f"prior BBC {field} preservation")
    rows = []
    all_cases = []
    for index, source in enumerate(SOURCES):
        source_receipt = receipt["sources"][index]
        parity_path = run / f"{source}.float-parity.private.json"
        parity = load(parity_path)
        selected_path = run / f"{source}.selected-receipt.private.json"
        selected = load(selected_path)
        require(source_receipt["sourceKey"] == parity["source"] == selected["sourceKey"] == source,
                f"source receipt/parity identity {source}")
        require(source_receipt["variantExecutionRootSHA256"] ==
                selected["variantExecutionRootSHA256"],
                f"selected/full execution root {source}")
        require(selected["verifiedExportFileCount"] == 337 and
                selected["verifiedStageFileCount"] == 99,
                f"selected verified file counts {source}")
        require(parity["allInputIdsExact"] and parity["allThresholdFlagsMatch"] and
                parity["caseCount"] == 3 and len(source_receipt["cases"]) == 3,
                f"float input/action parity {source}")
        require(parity["frozenSHA256"] == sha(fpath) and
                parity["tokensSHA256"] == sha(tpath) and
                parity["runtimeSourceSHA256"] == sha(a.runtime_source) and
                parity["exportManifestSHA256"] == sha(a.export_manifest),
                f"float parity pins {source}")
        require([c["question"] for c in source_receipt["cases"]] == list(QUESTIONS),
                f"question order {source}")
        cases = []
        for qi, (case, comparison) in enumerate(zip(source_receipt["cases"],
                                                     parity["cases"], strict=True)):
            result = load(run / f"{source}.q{qi}.result.json")
            require(case["yesSupportPpmRounded4"] == result["yesSupportPpmRounded4"] ==
                    comparison["integerYesRoundedPpm"], f"integer score {source}/{qi}")
            require(case["yesSupportAtThreshold"] == comparison["integerYesAt55Percent"] ==
                    comparison["floatYesAt55Percent"], f"threshold flag {source}/{qi}")
            if source == "bbc":
                old_trace = load(a.prior_bbc_dir / "integer-run-v3-repeat" / f"bbc.q{qi}.trace.json")
                trace = load(run / f"bbc.q{qi}.trace.json")
                require([(s["stage"], s["sha256"]) for s in trace["stages"]] ==
                        [(s["stage"], s["sha256"]) for s in old_trace["stages"]],
                        f"all 33 prior BBC stage tensors {qi}")
            cases.append({"question": case["question"],
                          "integerYesPpm": case["yesSupportPpmRounded4"],
                          "floatYesPpm": comparison["floatYesRoundedPpm"],
                          "thresholdSupport": case["yesSupportAtThreshold"],
                          "executionRootSHA256": case["executionRootSHA256"],
                          "denseMACs": case["denseMACs"],
                          "attentionMACs": case["attentionMACs"],
                          "cpuForwardSeconds": case["cpuForwardSeconds"]})
            all_cases.append(comparison)
        rows.append({"sourceKey": source,
                     "inputSubsetSHA256": source_receipt["inputSubsetSHA256"],
                     "sourceExecutionRootSHA256": source_receipt["variantExecutionRootSHA256"],
                     "selectedReceiptSHA256": sha(selected_path),
                     "paritySHA256": sha(parity_path),
                     "maxRawLogitAbsError": parity["maxRawLogitAbsError"],
                     "maxActionLogitAbsError": parity["maxActionLogitAbsError"],
                     "maxLayerAbsError": parity["maxLayerAbsError"],
                     "maxMarkerLayerAbsError": parity["maxMarkerLayerAbsError"],
                     "cases": cases})
    report = {"schema": "laya-peace-four-report-integer-evidence-v1",
              "marketId": 5371292,
              "sourceOrder": list(SOURCES),
              "sourcePolicySHA256": sha(a.source_policy),
              "frozenEvidenceSHA256": sha(fpath), "frozenTokensSHA256": sha(tpath),
              "runtimeSourceSHA256": sha(a.runtime_source),
              "checkerSourceSHA256": sha(a.checker_source),
              "paritySourceSHA256": sha(a.parity_source),
              "exportManifestSHA256": sha(a.export_manifest),
              "fullReceiptSHA256": sha(receipt_path),
              "consensusExecutionRootSHA256": receipt["consensusExecutionRootSHA256"],
              "verifiedExportFileCount": 337,
              "verifiedStageFileCount": 396,
              "priorBBCAll99StageHashesExact": True,
              "allTwelveInputIdsExact": True,
              "allTwelveThresholdFlagsMatchFloat": True,
              "maxYesRoundedPpmAbsoluteError": max(c["yesRoundedPpmAbsoluteError"] for c in all_cases),
              "maxRawLogitAbsError": max(c["rawLogitMaxAbs"] for c in all_cases),
              "maxLayerAbsError": max(r["maxLayerAbsError"] for r in rows),
              "maxMarkerLayerAbsError": max(r["maxMarkerLayerAbsError"] for r in rows),
              "denseMACs": sum(c["denseMACs"] for r in rows for c in r["cases"]),
              "attentionMACs": sum(c["attentionMACs"] for r in rows for c in r["cases"]),
              "cpuForwardSeconds": sum(c["cpuForwardSeconds"] for r in rows for c in r["cases"]),
              "sources": rows,
              "limits": ["Complete local CPU integer execution, not full-model EVM inference or gas proof.",
                         "Publisher/source admissibility was fixed in the separate policy before inference; this numeric audit does not establish it.",
                         "Float hooks cover 28 encoder and two head layers; raw stage outliers are retained rather than hidden.",
                         "Local time and hashes do not prove independently controlled operators or real-chain finalization."]}
    tmp = a.output.with_suffix(a.output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, a.output)
    print(json.dumps({"output": str(a.output), "sha256": sha(a.output),
                      "root": report["consensusExecutionRootSHA256"],
                      "scores": [[c["integerYesPpm"] for c in r["cases"]] for r in rows],
                      "denseMACs": report["denseMACs"],
                      "attentionMACs": report["attentionMACs"],
                      "cpuForwardSeconds": report["cpuForwardSeconds"]}, sort_keys=True))


if __name__ == "__main__":
    main()
