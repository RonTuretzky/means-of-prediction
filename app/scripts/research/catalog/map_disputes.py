#!/usr/bin/env python3
"""Join dispute question IDs to cataloged public Gamma market versions offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()


def bind(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": file_digest(path), "bytes": path.stat().st_size}


def validate_inputs(catalog: Path, catalog_manifest: Path, disputes: Path, dispute_manifest: Path) -> None:
    catalog_meta = json.loads(catalog_manifest.read_bytes())
    catalog_binding = catalog_meta.get("artifacts", {}).get("catalog", {})
    if catalog_binding.get("sha256") != file_digest(catalog):
        raise ValueError("catalog hash does not match its manifest")
    dispute_meta = json.loads(dispute_manifest.read_bytes())
    if dispute_meta.get("complete") is not True:
        raise ValueError("dispute union manifest is not complete")
    expected = dispute_meta.get("outputs", {}).get("knownAdapterQuestionKeys", {})
    if expected.get("sha256") != file_digest(disputes):
        raise ValueError("dispute input hash does not match its manifest")


def map_disputes(
    catalog: Path,
    disputes: Path,
    mapped_path: Path,
    unmatched_path: Path,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    query = """
      SELECT v.version_id,v.market_id,v.source_row,v.raw_sha256,v.question_id,
             v.condition_id,v.event_group_ids_json,v.question,v.rules,v.labels_json,v.state_json,
             s.path,s.sha256,m.version_count,m.distinct_raw_versions,
             m.source_conflict,m.conflict_fields_json,m.training_holdout
      FROM versions v JOIN sources s ON s.source_id=v.source_id
      JOIN markets m ON m.market_id=v.market_id
      WHERE v.question_id=? ORDER BY v.market_id,v.source_id,v.source_row
    """
    mapped = unmatched = events = matches = conflict_events = 0
    dispute_question_ids: set[str] = set()
    mapped_question_ids: set[str] = set()
    mapped_market_ids: set[str] = set()
    mapped_hasher = hashlib.sha256()
    unmatched_hasher = hashlib.sha256()
    mapped_bytes = unmatched_bytes = 0
    mapped_handle = mapped_path.open("xb")
    unmatched_handle = unmatched_path.open("xb")
    os.chmod(mapped_path, 0o600)
    os.chmod(unmatched_path, 0o600)
    try:
        with disputes.open("rb") as input_handle:
            for line_number, line in enumerate(input_handle, 1):
                if not line.strip():
                    continue
                event = json.loads(line)
                question_id = event.get("questionId")
                if not isinstance(question_id, str) or not question_id:
                    raise ValueError(f"dispute row {line_number} lacks questionId")
                rows = connection.execute(query, (question_id.casefold(),)).fetchall()
                events += 1
                dispute_question_ids.add(question_id.casefold())
                base = {
                    "eventKey": event.get("eventKey"),
                    "questionId": question_id,
                    "disputeRawSha256": digest(line.rstrip(b"\r\n")),
                    "disputeSourceRefs": event.get("sourceRefs"),
                    "trainingAdmission": "none_evidence_and_labels_require_review",
                }
                if not rows:
                    output = encoded({**base, "mappingStatus": "unmatched", "catalogVersions": []})
                    unmatched_handle.write(output)
                    unmatched_hasher.update(output)
                    unmatched_bytes += len(output)
                    unmatched += 1
                    continue
                versions = []
                has_conflict = False
                mapped_question_ids.add(question_id.casefold())
                for row in rows:
                    conflict = bool(row[15])
                    has_conflict |= conflict
                    mapped_market_ids.add(row[1])
                    versions.append(
                        {
                            "versionId": row[0], "marketId": row[1], "sourceRow": row[2],
                            "rawVersionSha256": row[3], "questionId": row[4], "conditionId": row[5],
                            "eventGroupIds": json.loads(row[6]),
                            "question": row[7], "rules": row[8],
                            "outcomeLabels": json.loads(row[9]) if row[9] else None,
                            "privateStateObservation": json.loads(row[10]),
                            "sourcePath": row[11], "sourceSha256": row[12],
                            "marketVersionCount": row[13], "distinctRawVariants": row[14],
                            "publicTermsConflict": conflict,
                            "conflictFields": json.loads(row[16]), "trainingHoldout": bool(row[17]),
                        }
                    )
                output = encoded(
                    {
                        **base,
                        "mappingStatus": "matched_with_public_terms_conflict" if has_conflict else "matched",
                        "catalogVersions": versions,
                    }
                )
                mapped_handle.write(output)
                mapped_hasher.update(output)
                mapped_bytes += len(output)
                mapped += 1
                matches += len(versions)
                conflict_events += has_conflict
    finally:
        mapped_handle.close()
        unmatched_handle.close()
        connection.close()
    return {
        "disputeEvents": events,
        "mappedEvents": mapped,
        "unmatchedEvents": unmatched,
        "catalogVersionMatches": matches,
        "mappedEventsWithPublicTermsConflict": conflict_events,
        "distinctDisputeQuestionIds": len(dispute_question_ids),
        "distinctMappedQuestionIds": len(mapped_question_ids),
        "distinctMappedMarketIds": len(mapped_market_ids),
        "mappedSha256": mapped_hasher.hexdigest(),
        "mappedBytes": mapped_bytes,
        "unmatchedSha256": unmatched_hasher.hexdigest(),
        "unmatchedBytes": unmatched_bytes,
    }


def main() -> int:
    base = Path.home() / ".local/share/means-of-prediction"
    parser = argparse.ArgumentParser(description="Map dispute question IDs to private catalog versions")
    parser.add_argument("--catalog-dir", type=Path, default=base / "historical-market-catalog-20260914")
    parser.add_argument("--dispute-dir", type=Path, default=base / "disputed-markets-20260914-union-v3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = args.catalog_dir / "catalog.sqlite3"
    catalog_manifest = args.catalog_dir / "manifest.json"
    disputes = args.dispute_dir / "known-adapter-question-keys.jsonl"
    dispute_manifest = args.dispute_dir / "manifest.json"
    validate_inputs(catalog, catalog_manifest, disputes, dispute_manifest)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True)
    counts = map_disputes(
        catalog, disputes, args.output / "mapped-private.jsonl", args.output / "unmatched-private.jsonl"
    )
    manifest = {
        "schemaVersion": "dispute-catalog-map-v1",
        "inputs": [bind(catalog), bind(catalog_manifest), bind(disputes), bind(dispute_manifest)],
        "counts": {key: value for key, value in counts.items() if not key.endswith(("Sha256", "Bytes"))},
        "artifacts": {
            "mapped": {"path": "mapped-private.jsonl", "sha256": counts["mappedSha256"], "bytes": counts["mappedBytes"]},
            "unmatched": {"path": "unmatched-private.jsonl", "sha256": counts["unmatchedSha256"], "bytes": counts["unmatchedBytes"]},
        },
        "trainingAdmission": "none; mapping is not evidence or label review",
    }
    manifest_path = args.output / "manifest.json"
    manifest_path.write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")
    manifest_path.chmod(0o600)
    print(json.dumps(manifest["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
