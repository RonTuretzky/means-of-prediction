#!/usr/bin/env python3
"""Assemble BBC Peace integer replay and unchanged-float comparison receipts."""
import argparse
import hashlib
import json
import os
from pathlib import Path

QUESTIONS = ("q", "A", "B")
STAGES = ("embeddings",) + tuple(f"encoder_{i:02d}" for i in range(28)) + (
    "encoder_final_norm", "typed_embedding", "head_0", "head_1")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path: Path):
    return json.loads(path.read_text())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--peace-dir", type=Path, required=True)
    p.add_argument("--runtime-source", type=Path, required=True)
    p.add_argument("--checker-source", type=Path, required=True)
    p.add_argument("--export-manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    frozen = a.peace_dir / "frozen.private.json"
    tokens = a.peace_dir / "tokens.private.json"
    subset = a.peace_dir / "tokens.bbc-integer-subset.private.json"
    first = a.peace_dir / "integer-run-v1"
    second = a.peace_dir / "integer-run-v2-subset"
    repeat = a.peace_dir / "integer-run-v3-repeat"
    receipt_paths = (second / "operator-receipt.private.json", repeat / "operator-receipt.private.json")
    receipts = [read(path) for path in receipt_paths]
    parity_path = second / "float-parity.private.json"
    parity = read(parity_path)
    f = read(frozen)
    t = read(tokens)
    require(f["tokensSHA256"] == sha(tokens), "frozen token pin")
    require(len(t["variants"]) == 1 and t["variants"][0]["sourceKey"] == "bbc", "single BBC source")
    for receipt in receipts:
        require(receipt["runtimeSourceSHA256"] == sha(a.runtime_source), "runtime pin")
        require(receipt["exportManifestSHA256"] == sha(a.export_manifest), "export pin")
        require(receipt["inputSubsetSHA256"] == sha(subset), "subset pin")
        require(receipt["parentFrozenTokensSHA256"] == sha(tokens), "parent tokens pin")
        require(receipt["frozenEvidenceSHA256"] == sha(frozen), "frozen evidence pin")
        require(receipt["verifiedExportFileCount"] == 337, "export file count")
        require(receipt["verifiedStageFileCount"] == 99, "stage file count")
        require([case["question"] for case in receipt["cases"]] == list(QUESTIONS), "q/A/B order")
    require(receipts[0]["variantExecutionRootSHA256"] == receipts[1]["variantExecutionRootSHA256"], "repeat source root")
    require([case["executionRootSHA256"] for case in receipts[0]["cases"]] ==
            [case["executionRootSHA256"] for case in receipts[1]["cases"]], "repeat case roots")
    require(parity["allInputIdsExact"] and parity["allThresholdFlagsMatch"] and parity["caseCount"] == 3,
            "float input/threshold parity")
    all_stage_bytes_equal = True
    cases = []
    for i, question in enumerate(QUESTIONS):
        name = f"bbc.q{i}"
        result_paths = [directory / f"{name}.result.json" for directory in (first, second, repeat)]
        results = [read(path) for path in result_paths]
        traces = [read(directory / f"{name}.trace.json") for directory in (first, second, repeat)]
        require(all([stage["stage"] for stage in trace["stages"]] == list(STAGES) for trace in traces),
                f"stage order {name}")
        output_fields = ("rawLogitsQ16", "actLogitsQ16", "probabilitiesQ16", "yesSupportPpmRounded4",
                         "consumerYesSupportAtThreshold", "denseMACs", "attentionMACs")
        require(all(all(result[field] == results[0][field] for field in output_fields) for result in results[1:]),
                f"exact integer output replay {name}")
        stage_hash_lists = [[stage["sha256"] for stage in trace["stages"]] for trace in traces]
        for directory, trace in zip((first, second, repeat), traces):
            for stage in trace["stages"]:
                require(sha(directory / f"{name}.{stage['stage']}.npy") == stage["sha256"],
                        f"stage bytes differ from trace at {name}/{stage['stage']}")
        require(stage_hash_lists[0] == stage_hash_lists[1] == stage_hash_lists[2],
                f"exact all-stage replay {name}")
        case = receipts[0]["cases"][i]
        require(case["yesSupportPpmRounded4"] == results[1]["yesSupportPpmRounded4"], "receipt score")
        cases.append({"name": name, "question": question,
                      "sequenceLength": len(t["variants"][0]["batch"]["input_ids"][i]),
                      "validTokenCount": sum(t["variants"][0]["batch"]["attention_mask"][i]),
                      "resultSHA256ByRun": [sha(path) for path in result_paths],
                      "all33StageBytesExactAcrossThreeRuns": True,
                      "executionRootSHA256": case["executionRootSHA256"],
                      "integerYesPpm": results[1]["yesSupportPpmRounded4"],
                      "floatYesPpm": parity["cases"][i]["floatYesRoundedPpm"],
                      "integerFlag": results[1]["consumerYesSupportAtThreshold"],
                      "floatFlag": parity["cases"][i]["floatYesAt55Percent"],
                      "denseMACs": results[1]["denseMACs"],
                      "attentionMACs": results[1]["attentionMACs"],
                      "cpuForwardSecondsByRun": [result["elapsedSeconds"] for result in results]})
    report = {"schema": "laya-peace-bbc-integer-evidence-v1", "sourceKey": "bbc",
              "marketId": int(f["market"]["id"]),
              "runtimeSourceSHA256": sha(a.runtime_source), "checkerSourceSHA256": sha(a.checker_source),
              "exportManifestSHA256": sha(a.export_manifest),
              "frozenEvidenceSHA256": sha(frozen), "frozenTokensSHA256": sha(tokens),
              "inputSubsetSHA256": sha(subset), "exactInputHash": receipts[0]["inputHash"],
              "tokenIdsHash": receipts[0]["tokenIdsHash"],
              "profileSHA256": f["profileSHA256"], "sourcePolicySHA256": f["sourcePolicySHA256"],
              "sourceExecutionRootSHA256": receipts[0]["variantExecutionRootSHA256"],
              "receiptSHA256ByRun": [sha(path) for path in receipt_paths],
              "paritySHA256": sha(parity_path),
              "threeRunsExactIntegerOutputsAnd99Stages": all_stage_bytes_equal,
              "verifiedExportFileCount": 337, "verifiedStageFileCountPerRun": 99,
              "allFloatThresholdFlagsMatch": parity["allThresholdFlagsMatch"],
              "maxYesProbabilityAbsoluteError": parity["maxYesProbabilityAbsoluteError"],
              "maxYesRoundedPpmAbsoluteError": parity["maxYesRoundedPpmAbsoluteError"],
              "maxRawLogitAbsError": parity["maxRawLogitAbsError"],
              "maxActionLogitAbsError": parity["maxActionLogitAbsError"],
              "maxLayerMeanAbsError": parity["maxLayerMeanAbsError"],
              "maxLayerAbsError": parity["maxLayerAbsError"],
              "denseMACsPerBBCSource": sum(c["denseMACs"] for c in cases),
              "attentionMACsPerBBCSource": sum(c["attentionMACs"] for c in cases),
              "cpuForwardSecondsByRun": {"fullTokens": sum(c["cpuForwardSecondsByRun"][0] for c in cases),
                                         "boundSubset": sum(c["cpuForwardSecondsByRun"][1] for c in cases),
                                         "boundSubsetRepeat": sum(c["cpuForwardSecondsByRun"][2] for c in cases)},
              "cases": cases,
              "limits": ["Complete CPU integer model replay only; no full-model EVM inference or gas measurement.",
                         "Numeric agreement does not admit the single BBC source under the policy's independent-source requirement.",
                         "Float hooks include 28 encoder and two head layers, not every internal operator."]}
    require(report["marketId"] == 5371292, "unexpected market")
    tmp = a.output.with_suffix(a.output.suffix + ".tmp")
    tmp.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, a.output)
    print(json.dumps({"output": str(a.output), "sha256": sha(a.output),
                      "sourceRoot": report["sourceExecutionRootSHA256"],
                      "scorePpm": [case["integerYesPpm"] for case in cases],
                      "flags": [case["integerFlag"] for case in cases],
                      "denseMACs": report["denseMACsPerBBCSource"],
                      "attentionMACs": report["attentionMACsPerBBCSource"]}, sort_keys=True))


if __name__ == "__main__":
    main()
