from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from app.scripts.research.articles import (
    CorpusIntegrityError,
    ValidationError,
    import_full_text_jsonl,
    import_nyt_metadata,
)


FIXTURES = Path(__file__).parent / "fixtures"


class CorpusTests(unittest.TestCase):
    def test_nyt_abstracts_snippets_and_leads_remain_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for api, expected_kind in (
                ("archive", "nyt_archive_api_metadata"),
                ("article-search", "nyt_article_search_api_metadata"),
            ):
                with self.subTest(api=api):
                    corpus = Path(temporary) / api
                    manifest = import_nyt_metadata(
                        FIXTURES / "nyt_archive.synthetic.json",
                        corpus,
                        api=api,
                        retrieved_at="2026-09-13T14:00:00-04:00",
                    )
                    record = json.loads(next((corpus / "records").iterdir()).read_bytes())
                    self.assertEqual(record["source"]["source_kind"], expected_kind)
                    self.assertEqual(record["evidence"]["classification"], "metadata_only")
                    self.assertIsNone(record["evidence"]["text"])
                    self.assertFalse(record["evidence"]["eligible_as_full_text"])
                    self.assertIn("abstract", record["evidence"]["metadata_fields"])
                    self.assertIn("snippet", record["evidence"]["metadata_fields"])
                    self.assertIn("lead_paragraph", record["evidence"]["metadata_fields"])
                    self.assertEqual(manifest["records"][0]["evidence_classification"], "metadata_only")
                    self.assertEqual(stat.S_IMODE(corpus.stat().st_mode), 0o700)
                    self.assertEqual(
                        stat.S_IMODE((corpus / "manifest.json").stat().st_mode), 0o600
                    )

    def test_duplicates_and_conflicting_versions_are_all_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            manifest = import_full_text_jsonl(
                FIXTURES / "full_text_versions.synthetic.jsonl", corpus
            )

            self.assertEqual(manifest["record_count"], 3)
            stored = [json.loads(path.read_bytes()) for path in (corpus / "records").iterdir()]
            by_id = {record["record_id"]: record for record in stored}
            records = manifest["records"]
            alpha = [r for r in records if by_id[r["record_id"]]["evidence"]["text"].endswith("alpha.")]
            beta = [r for r in records if by_id[r["record_id"]]["evidence"]["text"].endswith("beta.")]
            self.assertEqual(len(alpha), 2)
            self.assertEqual(len(beta), 1)
            self.assertEqual(sum(r["version_relations"]["duplicate_of"] is not None for r in alpha), 1)
            self.assertTrue(all(r["version_relations"]["has_conflict"] for r in records))
            self.assertFalse(beta[0]["eligible_as_full_text"])
            self.assertEqual(
                by_id[alpha[0]["record_id"]]["evidence"]["completeness_basis"],
                "submitter_declaration_unverified",
            )

    def test_full_text_requires_explicit_provenance_and_completeness(self) -> None:
        invalid = {
            "schema_version": "article-full-text-v1",
            "source_kind": "user_full_text_export",
            "article_id": "synthetic-invalid",
            "canonical_url": "https://example.test/invalid",
            "publication_date": "2026-09-01",
            "retrieved_at": "2026-09-02T10:00:00Z",
            "text_completeness": "complete",
            "provenance": {
                "declared_by": "synthetic-test-author",
                "acquisition_method": "constructed test fixture"
            },
            "text": "Synthetic invalid article text."
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "invalid.synthetic.jsonl"
            input_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
            corpus = root / "corpus"
            with self.assertRaisesRegex(ValidationError, "source_reference"):
                import_full_text_jsonl(input_path, corpus)
            self.assertFalse(corpus.exists())

    def test_idempotence_is_deterministic_and_tampering_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            source = FIXTURES / "nyt_archive.synthetic.json"
            import_nyt_metadata(
                source,
                corpus,
                api="archive",
                retrieved_at="2026-09-13T14:00:00-04:00",
            )
            first_manifest = (corpus / "manifest.json").read_bytes()
            import_nyt_metadata(
                source,
                corpus,
                api="archive",
                retrieved_at="2026-09-13T14:00:00-04:00",
            )
            self.assertEqual(first_manifest, (corpus / "manifest.json").read_bytes())

            second_corpus = Path(temporary) / "second-corpus"
            import_nyt_metadata(
                source,
                second_corpus,
                api="archive",
                retrieved_at="2026-09-13T14:00:00-04:00",
            )
            self.assertEqual(
                first_manifest, (second_corpus / "manifest.json").read_bytes()
            )

            record_path = next((second_corpus / "records").iterdir())
            tampered_record = json.loads(record_path.read_bytes())
            tampered_record["evidence"]["metadata_fields"]["abstract"] = (
                "Synthetic altered evidence with the old evidence hash retained."
            )
            record_path.write_text(
                json.dumps(tampered_record, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CorpusIntegrityError, "evidence hash"):
                import_nyt_metadata(
                    source,
                    second_corpus,
                    api="archive",
                    retrieved_at="2026-09-13T14:00:00-04:00",
                )

            source_path = next((corpus / "sources").iterdir())
            source_path.write_bytes(b"synthetic tampering")
            with self.assertRaisesRegex(CorpusIntegrityError, "source bytes"):
                import_nyt_metadata(
                    source,
                    corpus,
                    api="archive",
                    retrieved_at="2026-09-13T14:00:00-04:00",
                )

    def test_retrieval_time_and_declared_api_kind_make_distinct_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus = Path(temporary) / "corpus"
            source = FIXTURES / "nyt_archive.synthetic.json"
            first = import_nyt_metadata(
                source,
                corpus,
                api="archive",
                retrieved_at="2026-09-13T14:00:00-04:00",
            )
            later = import_nyt_metadata(
                source,
                corpus,
                api="archive",
                retrieved_at="2026-09-14T14:00:00-04:00",
            )
            other_api = import_nyt_metadata(
                source,
                corpus,
                api="article-search",
                retrieved_at="2026-09-14T14:00:00-04:00",
            )
            repeated = import_nyt_metadata(
                source,
                corpus,
                api="article-search",
                retrieved_at="2026-09-14T14:00:00-04:00",
            )

            self.assertEqual(first["record_count"], 1)
            self.assertEqual(later["record_count"], 2)
            self.assertEqual(other_api["record_count"], 3)
            self.assertEqual(repeated["record_count"], 3)
            self.assertEqual(len({row["record_id"] for row in repeated["records"]}), 3)
            archive_receipts = [
                row
                for row in repeated["records"]
                if row["source"]["source_kind"] == "nyt_archive_api_metadata"
            ]
            self.assertEqual(
                sum(
                    row["version_relations"]["duplicate_of"] is not None
                    for row in archive_receipts
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
