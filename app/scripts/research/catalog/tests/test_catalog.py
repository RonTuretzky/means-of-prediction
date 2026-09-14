from __future__ import annotations

import json
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from app.scripts.research.catalog import build_catalog
from app.scripts.research.catalog.catalog import digest


def write_fixture(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows), encoding="utf-8")


class CatalogTests(unittest.TestCase):
    def build(self, root: Path):
        first = root / "synthetic-first.json"
        second = root / "synthetic-second.json"
        write_fixture(
            first,
            [
                {
                    "id": "1", "question": "Synthetic question?", "description": "Synthetic rules.",
                    "outcomes": ["Yes", "No"], "outcome": "Yes", "outcomePrices": ["1", "0"],
                    "closed": True, "umaResolutionStatus": "resolved",
                },
                {
                    "id": "2", "question": "Conflicting synthetic question?", "description": "Rules A.",
                    "outcomes": ["Up", "Down"], "closed": False, "active": True,
                },
            ],
        )
        write_fixture(
            second,
            [
                {
                    "id": "1", "question": "Synthetic question?", "description": "Synthetic rules.",
                    "outcomes": ["Yes", "No"], "outcome": "Yes", "closed": True,
                    "umaResolutionStatusHistory": ["disputed", "resolved"],
                },
                {
                    "id": "2", "question": "Conflicting synthetic question?", "description": "Rules B.",
                    "outcomes": ["Down", "Up"], "closed": True, "active": False,
                },
            ],
        )
        output = root / "catalog"
        manifest = build_catalog(
            output,
            [(first, "array"), (second, "array")],
            reserved_ids={"1"},
            article_sample_ids=set(),
            exclusion_bindings=[],
        )
        return output, manifest, first, second

    def test_duplicate_versions_and_conflicts_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, manifest, _, _ = self.build(Path(temporary))
            connection = sqlite3.connect(output / "catalog.sqlite3")
            one = connection.execute(
                "SELECT version_count,distinct_raw_versions,source_conflict,training_holdout FROM markets WHERE market_id='1'"
            ).fetchone()
            two = connection.execute(
                "SELECT version_count,source_conflict,conflict_fields_json FROM markets WHERE market_id='2'"
            ).fetchone()
            connection.close()
            self.assertEqual(one, (2, 2, 0, 1))
            self.assertEqual(two[:2], (2, 1))
            self.assertEqual(json.loads(two[2]), ["rules", "outcomeLabels"])
            self.assertEqual(manifest["counts"]["versions"], 4)
            self.assertEqual(manifest["counts"]["sourceConflicts"], 1)

    def test_private_state_retains_open_closed_status_and_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _, _, _ = self.build(Path(temporary))
            connection = sqlite3.connect(output / "catalog.sqlite3")
            states = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT state_json FROM versions WHERE market_id='1' ORDER BY version_id"
                )
            ]
            connection.close()
            self.assertTrue(states[0]["closed"])
            self.assertEqual(states[0]["outcome"], "Yes")
            self.assertEqual(states[0]["outcomePrices"], ["1", "0"])
            self.assertEqual(states[0]["umaResolutionStatus"], "resolved")
            self.assertEqual(states[1]["umaResolutionStatusHistory"], ["disputed", "resolved"])

    def test_public_projection_has_no_result_status_or_price_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, manifest, first, second = self.build(Path(temporary))
            rows = [json.loads(line) for line in (output / "candidate-public.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(
                set(rows[0]),
                {"marketId", "question", "rules", "outcomeLabels", "trainingHoldout"},
            )
            self.assertEqual(rows[0]["outcomeLabels"], ["Yes", "No"])
            self.assertTrue(rows[0]["trainingHoldout"])
            self.assertNotIn("2", {row["marketId"] for row in rows})
            self.assertEqual(manifest["sources"][0]["sha256"], digest(first.read_bytes()))
            self.assertEqual(manifest["sources"][1]["sha256"], digest(second.read_bytes()))
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in output.iterdir()))


if __name__ == "__main__":
    unittest.main()
