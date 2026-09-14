from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from app.scripts.research.disputes import (
    build_cohort,
    classify_gamma,
    deterministic_split,
    write_cohort,
)
from app.scripts.research.disputes.pipeline import digest


def wrapped(row: dict, line: int = 1) -> dict:
    raw = json.dumps(row, sort_keys=True).encode()
    return {
        "row": row,
        "rawLineSha256": digest(raw),
        "inputPath": "synthetic-fixture.jsonl",
        "lineNumber": line,
        "kind": "event",
    }


def event(**changes) -> dict:
    row = {
        "chainId": "1",
        "oracleAddress": "0xOracle",
        "transactionHash": "0xTransaction",
        "logIndex": 7,
        "requester": "0xRequester",
        "identifier": "ASSERT_TRUTH",
        "timestamp": "2026-09-01T00:00:00Z",
        "ancillaryData": "0x1234",
        "questionId": None,
        "conditionId": None,
        "marketId": "synthetic-market-1",
        "sourceRefs": [{"kind": "synthetic", "ref": "one"}],
        "lifecycle": {
            "eventName": "DisputePrice",
            "blockNumber": 123,
            "removed": None,
            "rpcReceiptVerified": False,
        },
    }
    row.update(changes)
    return row


class DisputePipelineTests(unittest.TestCase):
    def test_current_resolved_status_never_proves_no_dispute(self) -> None:
        self.assertEqual(classify_gamma({"umaResolutionStatus": "resolved"}), "unknown")
        self.assertEqual(
            classify_gamma({"umaResolutionStatuses": ["undisputed", "not_disputed"]}),
            "unknown",
        )
        self.assertEqual(
            classify_gamma(
                {
                    "umaResolutionStatus": "resolved",
                    "umaResolutionStatusHistory": '[{"status":"disputed"},{"status":"resolved"}]',
                }
            ),
            "api_history_only",
        )

    def test_event_dedupe_keeps_sources_and_conflicts_are_quarantined(self) -> None:
        first = event()
        duplicate = event(sourceRefs=[{"kind": "synthetic", "ref": "two"}])
        cohort = build_cohort([wrapped(first), wrapped(duplicate, 2)], [], set(), seed="s")
        self.assertEqual(cohort["private"], [])
        self.assertEqual(cohort["quarantine"][0]["reason"], "mapping_pending")
        self.assertEqual(len(cohort["quarantine"][0]["records"][0]["sourceRefs"]), 2)
        self.assertEqual(
            cohort["quarantine"][0]["records"][0]["evidenceTier"], "event_confirmed"
        )

        conflict = event(identifier="DIFFERENT_ASSERTION")
        conflicted = build_cohort([wrapped(first), wrapped(conflict, 3)], [], set(), seed="s")
        self.assertEqual(conflicted["private"], [])
        self.assertEqual(conflicted["quarantine"][0]["reason"], "conflicting_event_versions")

    def test_prior_overlap_and_unknown_gamma_are_quarantined(self) -> None:
        gamma = {
            "marketId": "unmapped",
            "question": "Synthetic question?",
            "rules": "Synthetic rules.",
            "outcomeLabels": ["Yes", "No"],
            "sourceRefs": ["synthetic://gamma"],
            "umaResolutionStatus": "resolved",
        }
        cohort = build_cohort(
            [wrapped(event(marketId="reserved-1"))],
            [wrapped(gamma, 2)],
            {"reserved-1"},
            seed="s",
        )
        self.assertEqual(cohort["private"], [])
        self.assertEqual(
            {item["reason"] for item in cohort["quarantine"]},
            {"prior_id_overlap", "no_affirmative_dispute_evidence"},
        )

    def test_repeat_request_timestamps_remain_in_one_connected_group(self) -> None:
        first = event(transactionHash="0xRoundOne", logIndex=1, timestamp="100")
        second = event(transactionHash="0xRoundTwo", logIndex=2, timestamp="200")
        cohort = build_cohort(
            [wrapped(first), wrapped(second, 2)], [], set(), seed="fixed"
        )
        self.assertEqual(len(cohort["quarantine"]), 1)
        self.assertEqual(cohort["quarantine"][0]["reason"], "mapping_pending")
        self.assertEqual(len(cohort["quarantine"][0]["records"]), 2)
        self.assertEqual(
            cohort["quarantine"][0]["records"][0]["requestGroup"],
            cohort["quarantine"][0]["records"][1]["requestGroup"],
        )

    def test_related_markets_share_event_split_and_overlap_quarantine(self) -> None:
        rows = [wrapped({
            "marketId": mid, "questionId": "question-" + mid,
            "eventGroupId": "one-economic-event", "question": "Synthetic threshold?",
            "rules": "Synthetic terms", "outcomeLabels": ["Yes", "No"],
            "sourceRefs": ["synthetic://gamma"], "umaResolutionStatuses": ["disputed"],
        }, i) for i, mid in enumerate(["threshold-a", "threshold-b"], 1)]
        cohort = build_cohort([], rows, set(), seed="fixed")
        self.assertEqual(len(cohort["public"]), 2)
        self.assertEqual(len({r["cohortGroup"] for r in cohort["public"]}), 1)
        self.assertEqual(len({r["split"] for r in cohort["public"]}), 1)
        blocked = build_cohort([], rows, {"threshold-a"}, seed="fixed")
        self.assertEqual(blocked["public"], [])
        self.assertEqual(len(blocked["quarantine"]), 1)
        self.assertEqual(len(blocked["quarantine"][0]["records"]), 2)

    def test_request_group_split_is_stable_and_public_fields_are_allowlisted(self) -> None:
        gamma = {
            "marketId": "synthetic-gamma",
            "question": "Will the synthetic event happen?",
            "rules": "Synthetic rules.",
            "outcomeLabels": ["Yes", "No"],
            "sourceRefs": ["synthetic://gamma"],
            "umaResolutionStatuses": ["proposed", "disputed", "resolved"],
            "outcome": "YES",
        }
        cohort = build_cohort(
            [wrapped(event(marketId="synthetic-gamma"))],
            [wrapped(gamma, 2)],
            set(),
            seed="fixed",
        )
        self.assertEqual(len(cohort["public"]), 1)
        self.assertEqual(len(cohort["private"]), 2)
        self.assertEqual(len({row["split"] for row in cohort["private"]}), 1)
        allowed = {
            "cohortRecordId", "split", "marketId", "questionId",
            "conditionId", "question", "rules", "outcomeLabels", "cohortGroup", "eventGroupId",
        }
        self.assertTrue(all(set(row) == allowed for row in cohort["public"]))
        self.assertEqual(
            deterministic_split(cohort["private"][0]["cohortGroup"], "fixed"),
            cohort["private"][0]["split"],
        )
        gamma_private = next(row for row in cohort["private"] if row["marketId"] == "synthetic-gamma")
        self.assertEqual(gamma_private["outcomeUse"], "private_observation_not_truth_gold")
        with_outcome = next(
            row for row in cohort["private"] if row.get("privateObservations", {}).get("outcome")
        )
        self.assertEqual(with_outcome["privateObservations"]["outcome"], "YES")
        event_private = next(row for row in cohort["private"] if "sourceVerification" in row)
        self.assertFalse(event_private["sourceVerification"]["rpcReceiptVerified"])
        self.assertEqual(
            event_private["sourceVerification"]["basis"],
            "normalized_input_declaration",
        )

    def test_event_evidence_can_supply_dispute_basis_for_unknown_gamma_terms(self) -> None:
        gamma = {
            "marketId": "joined-market",
            "question": "Will the joined synthetic event happen?",
            "rules": "Synthetic joined rules.",
            "outcomeLabels": ["Yes", "No"],
            "sourceRefs": ["synthetic://gamma"],
            "umaResolutionStatus": "resolved",
        }
        cohort = build_cohort(
            [wrapped(event(marketId="joined-market"))],
            [wrapped(gamma, 2)],
            set(),
            seed="fixed",
        )
        self.assertEqual(len(cohort["private"]), 1)
        self.assertEqual(cohort["private"][0]["evidenceTier"], "event_confirmed")
        self.assertEqual(len(cohort["public"]), 1)
        self.assertEqual(cohort["public"][0]["outcomeLabels"], ["Yes", "No"])
        self.assertEqual(
            cohort["quarantine"][0]["reason"],
            "api_status_unknown_linked_to_affirmative_evidence",
        )

    def test_event_conflict_quarantines_connected_gamma_sibling(self) -> None:
        gamma = {
            "marketId": "joined-market",
            "question": "Synthetic question?",
            "rules": "Synthetic rules.",
            "outcomeLabels": ["Yes", "No"],
            "sourceRefs": ["synthetic://gamma"],
            "umaResolutionStatuses": ["disputed"],
        }
        conflicted = build_cohort(
            [
                wrapped(event(marketId="joined-market")),
                wrapped(event(marketId="joined-market", identifier="DIFFERENT"), 2),
            ],
            [wrapped(gamma, 3)],
            set(),
            seed="fixed",
        )
        self.assertEqual(conflicted["private"], [])
        self.assertEqual(conflicted["public"], [])
        self.assertEqual(len(conflicted["quarantine"][0]["records"]), 3)
        self.assertEqual(
            conflicted["quarantine"][0]["reason"], "conflicting_event_versions"
        )

    def test_written_manifest_binds_artifacts_and_disables_training(self) -> None:
        cohort = build_cohort([wrapped(event())], [], set(), seed="fixed")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "cohort"
            manifest = write_cohort(
                output,
                cohort,
                seed="fixed",
                input_bindings=[],
                exclusion_bindings=[],
                curriculum_cap=0.20,
            )
            self.assertFalse(manifest["trainingLaunched"])
            self.assertEqual(manifest["counts"]["reviewedTrainingAdmissions"], 0)
            self.assertEqual(manifest["counts"]["evidencePending"], 0)
            self.assertEqual(manifest["counts"]["quarantinedGroups"], 1)
            self.assertEqual(manifest["counts"]["quarantinedRecords"], 1)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            for artifact in manifest["artifacts"].values():
                path = output / artifact["path"]
                self.assertEqual(digest(path.read_bytes()), artifact["sha256"])
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            curriculum = json.loads((output / "curriculum.json").read_bytes())
            self.assertFalse(curriculum["enabled"])
            self.assertEqual(curriculum["appliesTo"], ["regex", "qwen"])


if __name__ == "__main__":
    unittest.main()
