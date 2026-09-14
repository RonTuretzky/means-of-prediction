from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.scripts.research.catalog import build_catalog
from app.scripts.research.catalog.map_disputes import map_disputes


class DisputeMapTests(unittest.TestCase):
    def test_join_preserves_every_catalog_version_and_never_admits_training(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "synthetic-a.json", root / "synthetic-b.json"
            first.write_text(json.dumps([{
                "id": "1", "questionID": "0xABC", "question": "Synthetic?",
                "description": "Rules A.", "outcomes": ["Yes", "No"],
                "events": [{"id": "event-9"}],
                "outcomePrices": ["1", "0"], "closed": True,
            }]))
            second.write_text(json.dumps([{
                "id": "1", "questionID": "0xabc", "question": "Synthetic?",
                "description": "Rules B.", "outcomes": ["Yes", "No"],
                "outcomePrices": ["0", "1"], "closed": True,
            }]))
            catalog_dir = root / "catalog"
            build_catalog(
                catalog_dir, [(first, "array"), (second, "array")],
                reserved_ids=set(), article_sample_ids=set(), exclusion_bindings=[],
            )
            disputes = root / "synthetic-disputes.jsonl"
            disputes.write_text(json.dumps({
                "eventKey": "synthetic-event", "questionId": "0xAbC",
                "sourceRefs": ["synthetic://event"],
            }) + "\n")
            mapped, unmatched = root / "mapped.jsonl", root / "unmatched.jsonl"
            counts = map_disputes(catalog_dir / "catalog.sqlite3", disputes, mapped, unmatched)
            row = json.loads(mapped.read_text())
            self.assertEqual(counts["mappedEvents"], 1)
            self.assertEqual(counts["catalogVersionMatches"], 2)
            self.assertEqual(len(row["catalogVersions"]), 2)
            self.assertEqual(row["catalogVersions"][0]["eventGroupIds"], ["event-9"])
            self.assertEqual(row["mappingStatus"], "matched_with_public_terms_conflict")
            self.assertEqual(row["trainingAdmission"], "none_evidence_and_labels_require_review")
            self.assertEqual(
                [version["privateStateObservation"]["outcomePrices"] for version in row["catalogVersions"]],
                [["1", "0"], ["0", "1"]],
            )
            self.assertEqual(unmatched.read_bytes(), b"")
            self.assertEqual(counts["distinctMappedQuestionIds"], 1)
            self.assertEqual(counts["distinctMappedMarketIds"], 1)

    def test_unmatched_question_id_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic.json"
            source.write_text(json.dumps([{
                "id": "1", "questionID": "0xknown", "question": "Synthetic?",
                "description": "Rules.", "outcomes": ["Yes", "No"],
            }]))
            catalog_dir = root / "catalog"
            build_catalog(
                catalog_dir, [(source, "array")], reserved_ids=set(),
                article_sample_ids=set(), exclusion_bindings=[],
            )
            disputes = root / "synthetic-disputes.jsonl"
            disputes.write_text(json.dumps({
                "eventKey": "unmatched", "questionId": "0xmissing", "sourceRefs": []
            }) + "\n")
            mapped, unmatched = root / "mapped.jsonl", root / "unmatched.jsonl"
            counts = map_disputes(catalog_dir / "catalog.sqlite3", disputes, mapped, unmatched)
            self.assertEqual(counts["unmatchedEvents"], 1)
            self.assertEqual(mapped.read_bytes(), b"")
            self.assertEqual(json.loads(unmatched.read_text())["mappingStatus"], "unmatched")


if __name__ == "__main__":
    unittest.main()
