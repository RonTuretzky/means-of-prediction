#!/usr/bin/env python3
"""Offline integrity audit for the frozen NYT RSS metadata registry."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_rss import FEEDS, OUTPUT, SCHEMA_VERSION, digest, json_bytes, parse_feed


AUDIT_DIR_NAME = "audit-20260914T0234Z"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def is_mode(path: Path, wanted: int) -> bool:
    return stat.S_IMODE(path.stat().st_mode) == wanted


def write_once(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    if not OUTPUT.is_dir():
        raise RuntimeError(f"missing frozen registry: {OUTPUT}")
    audit_dir = OUTPUT / AUDIT_DIR_NAME
    if audit_dir.exists():
        raise RuntimeError(f"write-once audit path already exists: {audit_dir}")
    audit_dir.mkdir(mode=0o700)
    os.chmod(audit_dir, 0o700)

    collector = Path(__file__).with_name("collect_rss.py")
    collector_snapshot = audit_dir / "collect_rss.py"
    shutil.copyfile(collector, collector_snapshot)
    os.chmod(collector_snapshot, 0o600)
    collector_hash = sha256_path(collector)
    if sha256_path(collector_snapshot) != collector_hash:
        raise RuntimeError("collector snapshot hash mismatch")

    plan_path = OUTPUT / "collection-plan.json"
    manifest_path = OUTPUT / "manifest.json"
    plan = read_json(plan_path)
    manifest = read_json(manifest_path)
    failures: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION or manifest.get("schema_version") != SCHEMA_VERSION:
        failures.append("schema version mismatch")
    if plan.get("call_count") != len(FEEDS) or manifest.get("planned_feed_count") != len(FEEDS):
        failures.append("planned feed count mismatch")
    if not is_mode(OUTPUT, 0o700):
        failures.append("registry directory mode is not 0700")

    raw_bindings: list[dict[str, Any]] = []
    reconstructed: list[dict[str, Any]] = []
    calls = manifest.get("calls", [])
    if len(calls) != len(FEEDS):
        failures.append("manifest call count mismatch")
    for index, feed in enumerate(FEEDS, start=1):
        call = calls[index - 1] if index <= len(calls) else {}
        raw_path = OUTPUT / "raw" / f"{index:02d}-{feed}.xml"
        if not raw_path.exists():
            failures.append(f"missing raw feed: {feed}")
            continue
        raw = raw_path.read_bytes()
        raw_hash = digest(raw)
        if raw_hash != call.get("raw_sha256"):
            failures.append(f"raw SHA-256 mismatch: {feed}")
        if len(raw) != call.get("raw_byte_length"):
            failures.append(f"raw byte length mismatch: {feed}")
        if not is_mode(raw_path, 0o600):
            failures.append(f"raw permission mismatch: {feed}")
        raw_bindings.append({"feed": feed, "path": str(raw_path), "sha256": raw_hash, "byte_length": len(raw), "http_status": call.get("http_status"), "completed_at": call.get("completed_at")})
        if call.get("http_status") == 200 and "parse_error" not in call:
            rebuilt = parse_feed(raw, feed, call.get("url"), raw_hash, call.get("completed_at"))
            if len(rebuilt) != call.get("item_count"):
                failures.append(f"raw parse item count mismatch: {feed}")
            reconstructed.extend(rebuilt)

    stored_paths = sorted((OUTPUT / "records").glob("*.json"))
    stored_by_id: dict[str, dict[str, Any]] = {}
    record_bindings: list[dict[str, Any]] = []
    for path in stored_paths:
        if not is_mode(path, 0o600):
            failures.append(f"record permission mismatch: {path.name}")
        record = read_json(path)
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or path.stem != record_id:
            failures.append(f"record id/filename mismatch: {path.name}")
            continue
        if record_id in stored_by_id:
            failures.append(f"duplicate record id: {record_id}")
        stored_by_id[record_id] = record
        record_bindings.append({"record_id": record_id, "path": str(path), "sha256": sha256_path(path)})
        evidence = record.get("evidence", {})
        if evidence.get("classification") != "metadata_only" or evidence.get("full_text") is not None or evidence.get("eligible_as_full_text") is not False:
            failures.append(f"not metadata-only: {record_id}")

    rebuilt_by_id = {record["record_id"]: record for record in reconstructed}
    if set(stored_by_id) != set(rebuilt_by_id):
        failures.append("stored/reconstructed record ID sets differ")
    for record_id, rebuilt in rebuilt_by_id.items():
        if stored_by_id.get(record_id) != rebuilt:
            failures.append(f"stored/reconstructed record mismatch: {record_id}")
    if len(stored_paths) != manifest.get("metadata_item_count"):
        failures.append("stored record count differs from manifest")

    identity_counts = Counter(record["canonical_identity"] for record in reconstructed)
    if len(identity_counts) != manifest.get("unique_canonical_identity_count"):
        failures.append("canonical identity count differs from manifest")
    if sum(count > 1 for count in identity_counts.values()) != manifest.get("duplicate_canonical_identity_count"):
        failures.append("duplicate canonical identity count differs from manifest")
    if manifest.get("full_text_count") != 0 or manifest.get("article_links_followed") != 0:
        failures.append("manifest reports nonzero full text or article-link following")
    if not is_mode(plan_path, 0o600) or not is_mode(manifest_path, 0o600):
        failures.append("plan or manifest permission mismatch")

    dates = sorted(record["normalized_pub_date"] for record in reconstructed if record.get("normalized_pub_date"))
    report = {
        "audit_schema_version": "nyt-rss-registry-audit-v1",
        "audited_at": utc_now(),
        "offline_only": True,
        "registry_path": str(OUTPUT),
        "collector": {"source_path": str(collector), "snapshot_path": str(collector_snapshot), "sha256": collector_hash},
        "plan": {"path": str(plan_path), "sha256": sha256_path(plan_path)},
        "manifest": {"path": str(manifest_path), "sha256": sha256_path(manifest_path)},
        "raw_feeds": raw_bindings,
        "normalized_records": {"count": len(stored_paths), "bindings": record_bindings},
        "reconstruction": {
            "occurrence_count": len(reconstructed),
            "canonical_identity_count": len(identity_counts),
            "duplicate_canonical_identity_count": sum(count > 1 for count in identity_counts.values()),
            "publication_date_range_utc": {"minimum": dates[0] if dates else None, "maximum": dates[-1] if dates else None, "dated_record_count": len(dates)},
            "metadata_only_record_count": sum(record["evidence"]["classification"] == "metadata_only" for record in reconstructed),
            "full_text_record_count": sum(record["evidence"]["full_text"] is not None for record in reconstructed),
        },
        "permissions": {"registry_directory": "0700", "captured_files": "0600", "verified": not any("permission" in failure or "mode" in failure for failure in failures)},
        "passed": not failures,
        "failures": failures,
    }
    write_once(audit_dir / "audit.json", json_bytes(report))
    print(json.dumps({"audit": str(audit_dir / "audit.json"), "passed": report["passed"], "occurrences": report["reconstruction"]["occurrence_count"], "identities": report["reconstruction"]["canonical_identity_count"]}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"audit_rss failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
