from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from app.scripts.research.disputes.pipeline import ValidationError, build_cohort, digest
from app.scripts.research.disputes.prepare_gamma_from_map import (
    GAMMA_FILENAME,
    OBSERVATIONS_FILENAME,
    PLAN_FILENAME,
    build_gamma_records,
    coverage_observations,
    index_events,
    iter_jsonl,
    prepare,
)

MAP_BINDING = {
    "manifestPath": "synthetic/manifest.json",
    "manifestSha256": "0" * 64,
    "path": "synthetic/mapped.jsonl",
    "sha256": "1" * 64,
}


def event_row(key: str, question_id: str) -> dict:
    chain, oracle, tx, log_index = key.split(":")
    return {
        "chainId": chain,
        "oracleAddress": oracle,
        "transactionHash": tx,
        "logIndex": log_index,
        "requester": "0xrequester",
        "identifier": "ASSERT_TRUTH",
        "timestamp": "100",
        "ancillaryData": "0x1234",
        "questionId": question_id,
        "conditionId": None,
        "marketId": None,
        "eventKey": key,
        "sourceRefs": [{"kind": "synthetic", "ref": key}],
        "lifecycle": {"eventName": "DisputePrice", "blockNumber": 5, "removed": None},
    }


def version(market: str, version_id: int, question_id: str, **changes) -> dict:
    row = {
        "versionId": version_id,
        "marketId": market,
        "sourceRow": 10 + version_id,
        "rawVersionSha256": digest(f"{market}:{version_id}".encode()),
        "questionId": question_id,
        "conditionId": "cond-" + market,
        "eventGroupIds": ["group-" + market],
        "question": "Synthetic question for " + market + "?",
        "rules": "Synthetic rules for " + market + ".",
        "outcomeLabels": ["Yes", "No"],
        "privateStateObservation": {
            "umaResolutionStatus": "resolved",
            "umaResolutionStatuses": '["proposed","disputed","resolved"]',
            "outcomePrices": "[\"1\",\"0\"]",
        },
        "sourcePath": "synthetic/catalog.jsonl",
        "sourceSha256": "2" * 64,
        "marketVersionCount": 1,
        "distinctRawVariants": 1,
        "publicTermsConflict": False,
        "conflictFields": [],
        "trainingHoldout": False,
    }
    row.update(changes)
    return row


def map_row(key: str, question_id: str, raw_sha: str, versions: list[dict]) -> dict:
    return {
        "eventKey": key,
        "questionId": question_id,
        "disputeRawSha256": raw_sha,
        "disputeSourceRefs": [{"kind": "synthetic", "ref": key}],
        "mappingStatus": "matched",
        "catalogVersions": versions,
        "trainingAdmission": "none_evidence_and_labels_require_review",
    }


def jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(row, sort_keys=True).encode() + b"\n" for row in rows)


def lines(rows: list[dict]):
    for index, row in enumerate(rows, 1):
        line = json.dumps(row, sort_keys=True).encode()
        yield index, line, json.loads(line)


class Fixture:
    def __init__(self) -> None:
        self.key_a = "1:0xoracle:0xtx-a:1"
        self.key_b = "1:0xoracle:0xtx-b:2"
        self.key_c = "1:0xoracle:0xtx-c:3"
        self.events = [
            event_row(self.key_a, "q-alpha"),
            event_row(self.key_b, "q-alpha"),
            event_row(self.key_c, "q-beta"),
        ]
        self.event_bytes = jsonl_bytes(self.events)
        self.hashes = {
            row["eventKey"]: digest(json.dumps(row, sort_keys=True).encode())
            for row in self.events
        }

    def index(self) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_bytes(self.event_bytes)
            return index_events(path)


class BuildGammaRecordsTests(unittest.TestCase):
    def test_one_row_per_version_and_event_group_with_aggregated_dispute_refs(self) -> None:
        fixture = Fixture()
        alpha = version("m-alpha", 1, "q-alpha", eventGroupIds=["group-x", "group-y"])
        beta = version("m-beta", 2, "q-beta", eventGroupIds=[])
        rows = [
            map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [alpha]),
            map_row(fixture.key_b, "q-alpha", fixture.hashes[fixture.key_b], [alpha]),
            map_row(fixture.key_c, "q-beta", fixture.hashes[fixture.key_c], [beta]),
        ]
        records, counts = build_gamma_records(
            lines(rows), map_binding=MAP_BINDING, events=fixture.index()
        )
        self.assertEqual(counts["mappedRows"], 3)
        self.assertEqual(counts["catalogVersionRefs"], 3)
        self.assertEqual(counts["distinctCatalogVersions"], 2)
        self.assertEqual(counts["gammaRecords"], 3)
        self.assertEqual(counts["versionsWithMultipleEventGroupIds"], 1)
        self.assertEqual(counts["versionsWithoutEventGroupId"], 1)
        self.assertEqual(counts["evidenceTierPreview"], {"api_history_only": 3, "unknown": 0})
        alpha_records = [row for row in records if row["marketId"] == "m-alpha"]
        self.assertEqual([row["eventGroupId"] for row in alpha_records], ["group-x", "group-y"])
        beta_record = next(row for row in records if row["marketId"] == "m-beta")
        self.assertIsNone(beta_record["eventGroupId"])
        kinds = [ref["kind"] for ref in alpha_records[0]["sourceRefs"]]
        self.assertEqual(kinds, ["dispute_catalog_map", "catalog_market_version", "dispute_event", "dispute_event"])
        self.assertEqual(alpha_records[0]["sourceRefs"][0]["manifestSha256"], "0" * 64)
        self.assertEqual(alpha_records[0]["sourceRefs"][1]["rawVersionSha256"], alpha["rawVersionSha256"])
        self.assertEqual(
            {ref["eventKey"] for ref in alpha_records[0]["sourceRefs"][2:]},
            {fixture.key_a, fixture.key_b},
        )
        self.assertEqual(
            {ref["disputeRawSha256"] for ref in alpha_records[0]["sourceRefs"][2:]},
            {fixture.hashes[fixture.key_a], fixture.hashes[fixture.key_b]},
        )
        self.assertEqual(alpha_records[0]["umaResolutionStatuses"], '["proposed","disputed","resolved"]')
        self.assertNotIn("outcomePrices", alpha_records[0])
        self.assertEqual(alpha_records[0]["conditionId"], "cond-m-alpha")

    def test_conflicting_versions_are_still_emitted_and_counted(self) -> None:
        fixture = Fixture()
        first = version("m-alpha", 1, "q-alpha", publicTermsConflict=True, conflictFields=["rules"])
        second = version(
            "m-alpha", 2, "q-alpha", rules="Different rules.", publicTermsConflict=True,
            conflictFields=["rules"], trainingHoldout=True,
        )
        rows = [map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [first, second])]
        records, counts = build_gamma_records(
            lines(rows), map_binding=MAP_BINDING, events=fixture.index()
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(counts["publicTermsConflictVersions"], 2)
        self.assertEqual(counts["trainingHoldoutVersions"], 1)
        self.assertTrue(all(row["publicTermsConflict"] for row in records))
        self.assertEqual({row["rules"] for row in records}, {first["rules"], second["rules"]})

    def test_rejects_unbound_or_mismatched_dispute_rows(self) -> None:
        fixture = Fixture()
        good = version("m-alpha", 1, "q-alpha")
        cases = [
            map_row("1:0xoracle:0xmissing:9", "q-alpha", "f" * 64, [good]),
            map_row(fixture.key_a, "q-alpha", "f" * 64, [good]),
            map_row(fixture.key_a, "q-other", fixture.hashes[fixture.key_a], [version("m", 1, "q-other")]),
            map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [version("m", 1, "q-zeta")]),
            map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], []),
            {**map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [good]), "mappingStatus": "unmatched"},
        ]
        for row in cases:
            with self.assertRaises(ValidationError):
                build_gamma_records(lines([row]), map_binding=MAP_BINDING, events=fixture.index())
        inconsistent = [
            map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [good]),
            map_row(
                fixture.key_b, "q-alpha", fixture.hashes[fixture.key_b],
                [version("m-alpha", 1, "q-alpha", rawVersionSha256="e" * 64)],
            ),
        ]
        with self.assertRaises(ValidationError):
            build_gamma_records(lines(inconsistent), map_binding=MAP_BINDING, events=fixture.index())

    def test_derived_rows_feed_the_cohort_pipeline(self) -> None:
        fixture = Fixture()
        alpha = version("m-alpha", 1, "q-alpha")
        rows = [map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [alpha])]
        records, _ = build_gamma_records(lines(rows), map_binding=MAP_BINDING, events=fixture.index())
        gamma_items = [
            {
                "row": record,
                "rawLineSha256": digest(json.dumps(record, sort_keys=True).encode()),
                "inputPath": "derived.jsonl",
                "lineNumber": index,
                "kind": "gamma",
            }
            for index, record in enumerate(records, 1)
        ]
        event_items = [
            {
                "row": row,
                "rawLineSha256": fixture.hashes[row["eventKey"]],
                "inputPath": "events.jsonl",
                "lineNumber": index,
                "kind": "event",
            }
            for index, row in enumerate(fixture.events[:1], 1)
        ]
        cohort = build_cohort(event_items, gamma_items, set(), seed="fixed")
        self.assertEqual(len(cohort["public"]), 1)
        self.assertEqual(cohort["public"][0]["eventGroupId"], "group-m-alpha")
        self.assertEqual({row["evidenceTier"] for row in cohort["private"]}, {"event_confirmed", "api_history_only"})
        self.assertTrue(all(row["admission"] == "evidence_pending" for row in cohort["private"]))
        self.assertEqual(cohort["quarantine"], [])
        blocked = build_cohort(event_items, gamma_items, {"m-alpha"}, seed="fixed")
        self.assertEqual(blocked["public"], [])
        self.assertEqual(blocked["quarantine"][0]["reason"], "prior_id_overlap")
        self.assertEqual(len(blocked["quarantine"][0]["records"]), 2)


class CoverageObservationTests(unittest.TestCase):
    def test_observations_retain_unmatched_and_unmapped_without_admission(self) -> None:
        unmatched = [
            {"eventKey": "k1", "questionId": "q-1", "mappingStatus": "unmatched", "catalogVersions": [], "disputeRawSha256": "a" * 64},
            {"eventKey": "k2", "questionId": "q-1", "mappingStatus": "unmatched", "catalogVersions": [], "disputeRawSha256": "b" * 64},
        ]
        unmapped = [
            {"eventKey": "k3", "questionId": None, "requester": "0xr", "lifecycle": {"mappingStatus": "unmapped_requester", "adapter": None}},
        ]
        result = coverage_observations(
            lines(unmatched), lines(unmapped),
            unmatched_binding={"path": "u.jsonl", "sha256": "c" * 64, "bytes": 1},
            unmapped_binding={"path": "r.jsonl", "sha256": "d" * 64, "bytes": 1},
        )
        self.assertEqual(result["unmatchedCatalogMap"]["count"], 2)
        self.assertEqual(result["unmatchedCatalogMap"]["distinctQuestionIds"], 1)
        self.assertEqual(result["unmatchedCatalogMap"]["questionIds"], ["q-1"])
        self.assertEqual(result["unmatchedCatalogMap"]["byMappingStatus"], {"unmatched": 2})
        self.assertEqual(result["unmappedRequests"]["count"], 1)
        self.assertEqual(result["unmappedRequests"]["records"][0]["mappingStatus"], "unmapped_requester")
        self.assertEqual(result["unmappedRequests"]["records"][0]["requester"], "0xr")
        self.assertIn("not cohort records", result["admission"])
        with self.assertRaises(ValidationError):
            coverage_observations(
                lines([{**unmatched[0], "catalogVersions": [{"versionId": 1}]}]), lines([]),
                unmatched_binding={"path": "u", "sha256": "", "bytes": 0},
                unmapped_binding={"path": "r", "sha256": "", "bytes": 0},
            )


class PrepareEndToEndTests(unittest.TestCase):
    def _write_fixture(self, root: Path, *, corrupt_mapped: bool = False) -> dict:
        fixture = Fixture()
        map_dir = root / "map"
        union_dir = root / "union"
        map_dir.mkdir()
        union_dir.mkdir()
        events_path = union_dir / "known-adapter-question-keys.jsonl"
        events_path.write_bytes(fixture.event_bytes)
        unmapped_rows = [
            {"eventKey": "1:0xoracle:0xtx-u:4", "questionId": None, "requester": "0xr", "lifecycle": {"mappingStatus": "unmapped_requester", "adapter": None}}
        ]
        unmapped_path = union_dir / "unmapped-requests.jsonl"
        unmapped_bytes = jsonl_bytes(unmapped_rows)
        unmapped_path.write_bytes(unmapped_bytes)
        (union_dir / "manifest.json").write_bytes(
            json.dumps({"outputs": {"unmappedRequests": {"sha256": digest(unmapped_bytes)}}}).encode()
        )
        mapped_rows = [
            map_row(fixture.key_a, "q-alpha", fixture.hashes[fixture.key_a], [version("m-alpha", 1, "q-alpha")]),
        ]
        unmatched_rows = [
            {"eventKey": fixture.key_c, "questionId": "q-beta", "mappingStatus": "unmatched", "catalogVersions": [], "disputeRawSha256": fixture.hashes[fixture.key_c]},
        ]
        mapped_bytes = jsonl_bytes(mapped_rows)
        unmatched_bytes = jsonl_bytes(unmatched_rows)
        (map_dir / "mapped-private.jsonl").write_bytes(mapped_bytes)
        (map_dir / "unmatched-private.jsonl").write_bytes(unmatched_bytes)
        manifest = {
            "schemaVersion": "dispute-catalog-map-v1",
            "artifacts": {
                "mapped": {"path": "mapped-private.jsonl", "sha256": digest(mapped_bytes), "bytes": len(mapped_bytes)},
                "unmatched": {"path": "unmatched-private.jsonl", "sha256": digest(unmatched_bytes), "bytes": len(unmatched_bytes)},
            },
            "inputs": [{"path": str(events_path), "sha256": digest(fixture.event_bytes)}],
        }
        if corrupt_mapped:
            manifest["artifacts"]["mapped"]["sha256"] = "0" * 64
        (map_dir / "manifest.json").write_bytes(json.dumps(manifest).encode())
        exclusions = root / "exclude.json"
        exclusions.write_bytes(json.dumps(["unrelated-market"]).encode())
        return {"map_dir": map_dir, "events": events_path, "unmapped": unmapped_path, "exclusions": exclusions}

    def test_prepare_writes_bound_artifacts_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._write_fixture(root)
            output = root / "v2"
            plan = prepare(
                map_dir=paths["map_dir"], events=paths["events"], unmapped_requests=paths["unmapped"],
                output_dir=output, exclude_ids=[paths["exclusions"]], prior_manifest=None, seed="s",
            )
            gamma_path = output / GAMMA_FILENAME
            self.assertEqual(digest(gamma_path.read_bytes()), plan["derived"]["gamma"]["sha256"])
            self.assertEqual(plan["derived"]["gamma"]["rows"], 1)
            self.assertEqual(plan["counts"]["unmatchedRows"], 1)
            self.assertEqual(plan["counts"]["unmappedRequestRows"], 1)
            self.assertEqual(plan["inputs"]["priorIdExclusions"][0]["count"], 1)
            self.assertIn("--gamma", plan["cohortCommand"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            for name in (GAMMA_FILENAME, PLAN_FILENAME, OBSERVATIONS_FILENAME):
                self.assertEqual(stat.S_IMODE((output / name).stat().st_mode), 0o600)
            observations = json.loads((output / OBSERVATIONS_FILENAME).read_bytes())
            self.assertEqual(observations["unmatchedCatalogMap"]["questionIds"], ["q-beta"])
            rows = [row for _, _, row in iter_jsonl(gamma_path)]
            self.assertEqual(rows[0]["questionId"], "q-alpha")
            with self.assertRaises(FileExistsError):
                prepare(
                    map_dir=paths["map_dir"], events=paths["events"], unmapped_requests=paths["unmapped"],
                    output_dir=output, exclude_ids=[], prior_manifest=None, seed="s",
                )

    def test_prepare_refuses_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._write_fixture(root, corrupt_mapped=True)
            with self.assertRaises(ValidationError):
                prepare(
                    map_dir=paths["map_dir"], events=paths["events"], unmapped_requests=paths["unmapped"],
                    output_dir=root / "v2", exclude_ids=[], prior_manifest=None, seed="s",
                )
            self.assertFalse((root / "v2").exists())


if __name__ == "__main__":
    unittest.main()
