#!/usr/bin/env python3
"""Verify four precommitted Peace q/A/B replays with frozen request-bound inputs.

The checker reads SHA-pinned policy, frozen inputs, derived export, runtime
source, and the operator's own output files. It never reads float reference
scores or another operator's results. The policy must be frozen before
inference; this checker verifies binding, not whether reporting is credible.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np


STAGES = (["embeddings"] + [f"encoder_{i:02d}" for i in range(28)] +
          ["encoder_final_norm", "typed_embedding", "head_0", "head_1"])
FIELDS = ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")
Q = 65536


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(8 << 20), b""):
            h.update(part)
    return h.hexdigest()


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check(condition: bool, label: str):
    if not condition:
        raise ValueError(label)


def checked_hash(path: Path, expected: str):
    check(sha(path) == expected, f"file hash mismatch: {path}")


def round_even_ratio(numer: int, denom: int) -> int:
    quotient, remainder = divmod(numer, denom)
    return quotient + int(2 * remainder > denom or
                          (2 * remainder == denom and quotient % 2 == 1))


def validate_subset(subset: dict, original_tokens: dict, frozen_evidence: dict,
                    original_tokens_sha: str) -> dict:
    """Derive exactly one permitted q/A/B subset from both pinned frozen files."""
    check(frozen_evidence["tokensSHA256"] == original_tokens_sha,
          "frozen evidence/token file cross-pin mismatch")
    check(len(subset["variants"]) == 1, "expected one source subset")
    candidate = subset["variants"][0]
    source = candidate["sourceKey"]
    matching_tokens = [v for v in original_tokens["variants"] if v["sourceKey"] == source]
    matching_items = [v for v in frozen_evidence["items"] if v["sourceKey"] == source]
    check(len(matching_tokens) == len(matching_items) == 1, "source missing or duplicated in pinned originals")
    original = matching_tokens[0]
    frozen_item = matching_items[0]
    check(original["batch"] == frozen_item["batch"], "original batch/frozen evidence mismatch")
    check(original["gateHashes"] == frozen_item["gateHashes"], "original gate hash/frozen evidence mismatch")
    check(original["inputSHA256"] == frozen_item["inputSHA256"], "original input hash/frozen evidence mismatch")
    fields = {field: original["batch"][field] for field in FIELDS}
    derived = {"schema": "laya-frozen-peace-source-subset-v1",
               "parentFrozenTokensSHA256": original_tokens_sha,
               "questionOrder": original_tokens["questionOrder"],
               "variants": [{"sourceKey": source, "inputSHA256": original["inputSHA256"],
                             "gateHashes": {"inputHash": original["gateHashes"]["inputHash"],
                                            "tokenIdsHash": original["gateHashes"]["tokenIdsHash"]},
                             "batch": fields}]}
    check(subset == derived, "subset differs from pinned original q/A/B derivation")
    return candidate


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path, action="append",
                   help="one-source q/A/B subset JSON; repeat in frozen source order")
    p.add_argument("--run-dir", required=True, type=Path, help="independent operator output directory")
    p.add_argument("--runtime-source", required=True, type=Path)
    p.add_argument("--export-dir", required=True, type=Path)
    p.add_argument("--expected-runtime-sha", required=True)
    p.add_argument("--expected-export-sha", required=True)
    p.add_argument("--expected-input-sha", required=True, action="append",
                   help="precommitted subset SHA256; repeat in frozen source order")
    p.add_argument("--expected-parent-tokens-sha", required=True, help="precommitted full frozen token file SHA256")
    p.add_argument("--expected-input-hash", required=True, action="append",
                   help="precommitted exact-input keccak; repeat in frozen source order")
    p.add_argument("--expected-token-ids-hash", required=True, action="append",
                   help="precommitted ABI token-array keccak; repeat in frozen source order")
    p.add_argument("--expected-source-order", required=True,
                   help="four precommitted comma-separated source keys")
    p.add_argument("--selected-source", choices=("bbc", "cnn", "abc", "rfi"),
                   help="verify one actor's q/A/B outputs after checking all four frozen inputs")
    p.add_argument("--source-policy", required=True, type=Path)
    p.add_argument("--expected-source-policy-sha", required=True)
    p.add_argument("--frozen-evidence", required=True, type=Path)
    p.add_argument("--frozen-tokens", required=True, type=Path)
    p.add_argument("--expected-frozen-evidence-sha", required=True)
    p.add_argument("--expected-frozen-tokens-sha", required=True)
    p.add_argument("--prior-bbc-frozen-evidence", required=True, type=Path)
    p.add_argument("--prior-bbc-frozen-tokens", required=True, type=Path)
    p.add_argument("--expected-prior-bbc-frozen-evidence-sha", required=True)
    p.add_argument("--expected-prior-bbc-frozen-tokens-sha", required=True)
    p.add_argument("--operator", required=True, help="local receipt label; excluded from execution root")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    source_order = a.expected_source_order.split(",")
    check(len(source_order) == len(set(source_order)) == 4 and source_order[0] == "bbc",
          "expected four distinct source keys, starting with preserved BBC")
    check(all(len(v) == 4 for v in (a.input, a.expected_input_sha,
                                     a.expected_input_hash, a.expected_token_ids_hash)),
          "expected four ordered inputs and hash pins")
    runtime_sha = sha(a.runtime_source)
    export_path = a.export_dir / "manifest.json"
    export_sha = sha(export_path)
    check(runtime_sha == a.expected_runtime_sha, "runtime source pin mismatch")
    check(export_sha == a.expected_export_sha, "export manifest pin mismatch")
    export = json.loads(export_path.read_text())
    check(export["version"] == "laya-int16-q16-v1", "arithmetic profile mismatch")
    count = 0
    for entry in export["tensors"].values():
        for component in entry["files"].values():
            checked_hash(a.export_dir / component["path"], component["sha256"])
            count += 1
    for key, entry in export["luts"].items():
        checked_hash(a.export_dir / f"{key}.npy", entry["sha256"])
        count += 1
    check(count == 337 and len(STAGES) == 33, "export or stage inventory changed")
    frozen_evidence_sha = sha(a.frozen_evidence)
    original_tokens_sha = sha(a.frozen_tokens)
    source_policy_sha = sha(a.source_policy)
    check(frozen_evidence_sha == a.expected_frozen_evidence_sha, "frozen evidence SHA pin mismatch")
    check(original_tokens_sha == a.expected_frozen_tokens_sha, "frozen token SHA pin mismatch")
    check(source_policy_sha == a.expected_source_policy_sha, "source policy SHA pin mismatch")
    frozen_evidence = json.loads(a.frozen_evidence.read_text())
    original_tokens = json.loads(a.frozen_tokens.read_text())
    source_policy = json.loads(a.source_policy.read_text())
    check(frozen_evidence["sourcePolicySHA256"] == source_policy_sha and
          frozen_evidence["sourcePolicy"] == source_policy,
          "frozen policy cross-pin mismatch")
    check(source_policy["schema"] == "peace-exact-four-report-qualitative-consensus-policy-v1" and
          source_policy["sourceOrder"] == source_order and
          source_policy["marketId"] == int(frozen_evidence["market"]["id"]) == 5371292 and
          source_policy["fullRules"] == frozen_evidence["market"]["fullRules"] and
          source_policy["fullRulesSHA256"] == frozen_evidence["market"]["fullRulesSHA256"] and
          source_policy["profileSHA256"] == frozen_evidence["profileSHA256"],
          "frozen policy market/profile binding")
    check(len(source_policy["reports"]) == 4, "frozen policy report count")
    check(original_tokens["questionOrder"] == ["q", "A", "B"], "question order")
    check([v["sourceKey"] for v in original_tokens["variants"]] == source_order,
          "frozen token source order")
    check([v["sourceKey"] for v in frozen_evidence["items"]] == source_order,
          "frozen evidence source order")
    check(len({v["sourceGroup"] for v in frozen_evidence["items"]}) == 4,
          "four distinct reporting-origin groups required for this case")
    for i, (report, item) in enumerate(zip(source_policy["reports"],
                                          frozen_evidence["items"], strict=True)):
        check(report["sourceIndex"] == i and report["sourceKey"] == item["sourceKey"] and
              report["reportingOrigin"] == item["sourceGroup"] and
              report["rawSHA256"] == item["rawSHA256"] and
              report["unitSHA256"] == item["unitSHA256"] and
              report["resultIndex"] == item["resultIndex"] and
              report["rawPath"] == item["rawPath"],
              "frozen policy/report identity mismatch")
    checked_hash(a.prior_bbc_frozen_evidence, a.expected_prior_bbc_frozen_evidence_sha)
    checked_hash(a.prior_bbc_frozen_tokens, a.expected_prior_bbc_frozen_tokens_sha)
    prior_evidence = json.loads(a.prior_bbc_frozen_evidence.read_text())
    prior_tokens = json.loads(a.prior_bbc_frozen_tokens.read_text())
    check(len(prior_evidence["items"]) == len(prior_tokens["variants"]) == 1 and
          prior_evidence["items"][0]["sourceKey"] ==
          prior_tokens["variants"][0]["sourceKey"] == "bbc", "prior BBC source")
    new_bbc = original_tokens["variants"][0]
    old_bbc = prior_tokens["variants"][0]
    check(new_bbc["batch"] == old_bbc["batch"] and
          new_bbc["inputSHA256"] == old_bbc["inputSHA256"] and
          new_bbc["gateHashes"] == old_bbc["gateHashes"],
          "prior BBC input changed")
    check(frozen_evidence["items"][0]["batch"] == prior_evidence["items"][0]["batch"],
          "prior BBC frozen batch changed")
    source_receipts = []
    for source, input_path, expected_input_sha, expected_input_hash, expected_token_hash in zip(
            source_order, a.input, a.expected_input_sha, a.expected_input_hash,
            a.expected_token_ids_hash, strict=True):
      frozen = json.loads(input_path.read_text())
      variant = validate_subset(frozen, original_tokens, frozen_evidence, original_tokens_sha)
      check(variant["sourceKey"] == source, "subset source/order mismatch")
      batch = variant["batch"]
      check(all(len(batch[k]) == 3 for k in FIELDS), "expected q/A/B batch")
      input_file_sha = sha(input_path)
      check(input_file_sha == expected_input_sha, "one-source input subset pin mismatch")
      check(frozen["parentFrozenTokensSHA256"] == a.expected_parent_tokens_sha == original_tokens_sha,
            "parent frozen token file pin mismatch")
      check(variant["gateHashes"]["inputHash"] == expected_input_hash,
            "exact-input keccak pin mismatch")
      check(variant["gateHashes"]["tokenIdsHash"] == expected_token_hash,
            "ABI token-array keccak pin mismatch")
      if a.selected_source is not None and source != a.selected_source:
          continue
      cases = []
      for qi, question in enumerate(("q", "A", "B")):
        name = f"{source}.q{qi}"
        result_path = a.run_dir / f"{name}.result.json"
        trace_path = a.run_dir / f"{name}.trace.json"
        result = json.loads(result_path.read_text())
        trace = json.loads(trace_path.read_text())
        check(result["name"] == name and result["version"] == export["version"], "result name/profile")
        check(result["inputFileSha256"] == input_file_sha, "subset input hash")
        check(result["runtimeSourceSha256"] == runtime_sha, "result runtime hash")
        check(result["exportManifestSha256"] == export_sha, "result export hash")
        bound = {field: batch[field][qi] for field in FIELDS}
        bound_sha = canonical_hash(bound)
        check(result["batchBindingSha256"] == bound_sha, "batch binding")
        ids_sha = hashlib.sha256(np.asarray(bound["input_ids"], dtype="<i8").tobytes()).hexdigest()
        check(result["inputTokenSha256"] == ids_sha, "token ID byte hash")
        audit_commitment = result.pop("resultCommitmentSha256")
        check(canonical_hash(result) == audit_commitment, "audit result commitment")
        result["resultCommitmentSha256"] = audit_commitment
        checked_hash(trace_path, result["traceSha256"])
        check(trace["batchBindingSha256"] == bound_sha, "trace batch binding")
        check(trace["runtimeSourceSha256"] == runtime_sha, "trace runtime binding")
        check(trace["exportManifestSha256"] == export_sha, "trace export binding")
        check([s["stage"] for s in trace["stages"]] == STAGES, "stage order/completeness")
        ordered = []
        for stage in trace["stages"]:
            check(stage["shape"] == [len(bound["input_ids"]), 1024], "stage tensor shape")
            checked_hash(a.run_dir / f"{name}.{stage['stage']}.npy", stage["sha256"])
            ordered.append({"stage": stage["stage"], "shape": stage["shape"],
                            "tensorSHA256": stage["sha256"]})
        check(len(result["rawLogitsQ16"]) == len(result["probabilitiesQ16"]) ==
              len(result["actLogitsQ16"]) == 2, "output vector shape")
        check(sum(result["probabilitiesQ16"]) == Q, "softmax sum")
        check(result["temperatureQ16"] == 72673 and result["thresholdQ16"] == 36045,
              "calibration constants")
        yes_q = result["probabilitiesQ16"][1]
        yes_ppm = 100 * round_even_ratio(yes_q * 10000, Q)
        check(result["yesOptionIndex"] == 1 and result["yesSupportProbabilityQ16"] == yes_q,
              "YES option semantics")
        check(result["yesSupportPpmRounded4"] == yes_ppm and
              result["consumerYesSupportAtThreshold"] == (yes_ppm >= 550000),
              "consumer probability/threshold semantics")
        numerical = {"arithmeticVersion": result["version"],
                     "exportManifestSHA256": export_sha, "batchBindingSHA256": bound_sha,
                     "orderedStages": ordered, "rawLogitsQ16": result["rawLogitsQ16"],
                     "probabilitiesQ16": result["probabilitiesQ16"],
                     "actionLogitsQ16": result["actLogitsQ16"],
                     "temperatureQ16": result["temperatureQ16"],
                     "thresholdQ16": result["thresholdQ16"]}
        numeric_root = canonical_hash(numerical)
        execution_root = canonical_hash({"runtimeSourceSHA256": runtime_sha,
                                         "numericRootSHA256": numeric_root})
        cases.append({"name": name, "question": question, "batchBindingSHA256": bound_sha,
                      "numericRootSHA256": numeric_root, "executionRootSHA256": execution_root,
                      "yesSupportPpmRounded4": yes_ppm,
                      "yesSupportAtThreshold": yes_ppm >= 550000,
                      "denseMACs": result["denseMACs"],
                      "attentionMACs": result["attentionMACs"],
                      "cpuForwardSeconds": result["elapsedSeconds"]})
      # Policy, source bytes, and full model execution bind this source root.
      # Elapsed time, file paths, and the local operator label are excluded.
      variant_root = canonical_hash({"arithmeticVersion": export["version"],
          "runtimeSourceSHA256": runtime_sha, "exportManifestSHA256": export_sha,
          "frozenEvidenceSHA256": frozen_evidence_sha,
          "sourcePolicySHA256": source_policy_sha,
          "parentFrozenTokensSHA256": frozen["parentFrozenTokensSHA256"],
          "inputSubsetSHA256": input_file_sha,
          "sourceKey": source, "inputHash": variant["gateHashes"]["inputHash"],
          "tokenIdsHash": variant["gateHashes"]["tokenIdsHash"],
          "orderedCaseExecutionRoots": [case["executionRootSHA256"] for case in cases]})
      source_receipts.append({"sourceKey": source, "inputSubsetSHA256": input_file_sha,
          "inputHash": variant["gateHashes"]["inputHash"],
          "tokenIdsHash": variant["gateHashes"]["tokenIdsHash"],
          "verifiedStageFileCount": 3 * len(STAGES),
          "variantExecutionRootSHA256": variant_root, "cases": cases})
    check(len(source_receipts) == (1 if a.selected_source else 4),
          "source execution receipt count")
    consensus_root = None if a.selected_source else canonical_hash({
        "schema": "laya-peace-four-report-root-v1",
        "sourcePolicySHA256": source_policy_sha,
        "frozenEvidenceSHA256": frozen_evidence_sha,
        "parentFrozenTokensSHA256": original_tokens_sha,
        "runtimeSourceSHA256": runtime_sha, "exportManifestSHA256": export_sha,
        "orderedSourceExecutionRoots": [r["variantExecutionRootSHA256"]
                                        for r in source_receipts]})
    receipt = {"schema": ("laya-peace-one-of-four-integer-operator-receipt-v1"
                          if a.selected_source else
                          "laya-peace-four-report-integer-operator-receipt-v1"),
               "operatorLabel": a.operator, "sourceOrder": source_order,
               "runtimeSourceSHA256": runtime_sha, "exportManifestSHA256": export_sha,
               "parentFrozenTokensSHA256": original_tokens_sha,
               "frozenEvidenceSHA256": frozen_evidence_sha,
               "sourcePolicySHA256": source_policy_sha,
               "verifiedExportFileCount": count,
               "verifiedStageFileCount": len(source_receipts) * 3 * len(STAGES),
               "sources": source_receipts,
               "limitations": ["Local hash-checked CPU replay; no EVM execution or transaction gas proof.",
                               "A receipt hash alone does not authenticate an independent operator or prove execution.",
                               "This checker binds the pre-frozen policy; it does not determine publisher credibility or market resolution."]}
    if a.selected_source:
        receipt.update({"sourceKey": a.selected_source,
                        "inputSubsetSHA256": source_receipts[0]["inputSubsetSHA256"],
                        "inputHash": source_receipts[0]["inputHash"],
                        "tokenIdsHash": source_receipts[0]["tokenIdsHash"],
                        "variantExecutionRootSHA256": source_receipts[0]["variantExecutionRootSHA256"],
                        "cases": source_receipts[0]["cases"]})
    else:
        receipt["consensusExecutionRootSHA256"] = consensus_root
    target = a.output or a.run_dir / "operator-receipt.private.json"
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    print(json.dumps({"receipt": str(target), "sha256": sha(target),
                      "consensusExecutionRootSHA256": consensus_root,
                      "sourceExecutionRoots": [r["variantExecutionRootSHA256"]
                                               for r in source_receipts]}, sort_keys=True))


if __name__ == "__main__":
    main()
