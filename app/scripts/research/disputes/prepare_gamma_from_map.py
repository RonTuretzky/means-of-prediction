"""Reshape a dispute-to-catalog map into Gamma-style JSONL for the cohort pipeline.

The dispute-catalog map (``dispute-catalog-map-v1``) stores one row per dispute
event with a nested ``catalogVersions`` list.  ``pipeline._normalize_gamma``
reads flat rows with a singular ``eventGroupId`` and a nonempty ``sourceRefs``
list, so the map cannot be passed verbatim.  This module emits one Gamma row per
distinct catalog market version and per ``eventGroupId`` on that version, binds
every row to the mapping artifact, the catalog version, and every dispute event
that mapped to it, and passes through only the private state fields the
classifier reads.  It never manufactures IDs or joins: every mapped event must
exist in the supplied normalized event file with the same raw line hash and the
same ``questionId``.  It also writes coverage observations for unmatched and
unmapped dispute requests; those are observations, not admissions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

from .pipeline import (
    OPTIONAL_IDS,
    PRIVATE_OBSERVATION_FIELDS,
    ValidationError,
    _write_once,
    classify_gamma,
    digest,
    ids_from,
    json_bytes,
)

PLAN_SCHEMA_VERSION = "disputed-cohort-plan-v2"
OBSERVATIONS_SCHEMA_VERSION = "disputed-cohort-coverage-observations-v1"
GAMMA_FILENAME = "gamma-from-catalog-map.jsonl"
PLAN_FILENAME = "plan.json"
OBSERVATIONS_FILENAME = "observations.json"
MAP_SCHEMA_VERSION = "dispute-catalog-map-v1"
VERSION_REF_FIELDS = (
    "versionId",
    "marketId",
    "sourceRow",
    "rawVersionSha256",
    "sourcePath",
    "sourceSha256",
    "marketVersionCount",
    "distinctRawVariants",
    "publicTermsConflict",
    "conflictFields",
    "trainingHoldout",
    "eventGroupIds",
)


def file_digest(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def verify_binding(path: Path, expected: dict[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
        raise ValidationError(f"{label}: manifest binding lacks sha256")
    actual, size = file_digest(path)
    if actual != expected["sha256"]:
        raise ValidationError(f"{label}: sha256 mismatch for {path}")
    if expected.get("bytes") is not None and int(expected["bytes"]) != size:
        raise ValidationError(f"{label}: byte count mismatch for {path}")
    return {"path": str(path), "sha256": actual, "bytes": size}


def iter_jsonl(path: Path) -> Iterator[tuple[int, bytes, dict[str, Any]]]:
    with path.open("rb") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.rstrip(b"\r\n")
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{path}:{line_number} is not valid JSON") from exc
            if not isinstance(row, dict):
                raise ValidationError(f"{path}:{line_number} must be an object")
            yield line_number, line, row


def index_events(path: Path) -> dict[str, dict[str, Any]]:
    """Map union eventKey -> raw line hash and IDs, without retaining ancillary data."""
    index: dict[str, dict[str, Any]] = {}
    for line_number, line, row in iter_jsonl(path):
        key = row.get("eventKey")
        if not isinstance(key, str) or not key:
            raise ValidationError(f"{path}:{line_number} lacks eventKey")
        if key in index:
            raise ValidationError(f"{path}:{line_number} duplicates eventKey")
        index[key] = {
            "rawLineSha256": digest(line),
            "lineNumber": line_number,
            "questionId": row.get("questionId"),
        }
    return index


def _nonempty_string(value: Any, name: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{where}: {name} must be a nonempty string")
    return value


def _version_identity(version: dict[str, Any], where: str) -> tuple[str, str]:
    market_id = version.get("marketId")
    version_id = version.get("versionId")
    if market_id is None or version_id is None:
        raise ValidationError(f"{where}: catalog version lacks marketId/versionId")
    return str(market_id), str(version_id)


def _event_group_ids(version: dict[str, Any], where: str) -> list[str | None]:
    groups = version.get("eventGroupIds")
    if groups is None:
        return [None]
    if not isinstance(groups, list):
        raise ValidationError(f"{where}: eventGroupIds must be a list")
    cleaned = sorted({str(value) for value in groups if value is not None and str(value).strip()})
    return cleaned or [None]


def build_gamma_records(
    map_rows: Iterator[tuple[int, bytes, dict[str, Any]]],
    *,
    map_binding: dict[str, Any],
    events: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collapse map rows into one Gamma row per (marketId, versionId, eventGroupId)."""
    versions: dict[tuple[str, str], dict[str, Any]] = {}
    dispute_refs: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    counts = {
        "mappedRows": 0,
        "catalogVersionRefs": 0,
        "versionsWithoutEventGroupId": 0,
        "versionsWithMultipleEventGroupIds": 0,
        "publicTermsConflictVersions": 0,
        "trainingHoldoutVersions": 0,
    }
    for line_number, line, row in map_rows:
        where = f"{map_binding['path']}:{line_number}"
        counts["mappedRows"] += 1
        if row.get("mappingStatus") != "matched":
            raise ValidationError(f"{where}: mappingStatus is not matched")
        event_key = _nonempty_string(row.get("eventKey"), "eventKey", where)
        question_id = _nonempty_string(row.get("questionId"), "questionId", where)
        raw_sha = _nonempty_string(row.get("disputeRawSha256"), "disputeRawSha256", where)
        event = events.get(event_key)
        if event is None:
            raise ValidationError(f"{where}: eventKey is not in the normalized event input")
        if event["rawLineSha256"] != raw_sha:
            raise ValidationError(f"{where}: disputeRawSha256 does not match the event line")
        if event["questionId"] != question_id:
            raise ValidationError(f"{where}: questionId differs from the event row")
        catalog_versions = row.get("catalogVersions")
        if not isinstance(catalog_versions, list) or not catalog_versions:
            raise ValidationError(f"{where}: matched row lacks catalogVersions")
        dispute_ref = {
            "kind": "dispute_event",
            "eventKey": event_key,
            "disputeRawSha256": raw_sha,
            "questionId": question_id,
            "mappingStatus": row["mappingStatus"],
            "mapLineSha256": digest(line),
            "mapLineNumber": line_number,
            "eventLineNumber": event["lineNumber"],
            "disputeSourceRefs": row.get("disputeSourceRefs"),
        }
        for version in catalog_versions:
            if not isinstance(version, dict):
                raise ValidationError(f"{where}: catalog version must be an object")
            counts["catalogVersionRefs"] += 1
            identity = _version_identity(version, where)
            if str(version.get("questionId")) != question_id:
                raise ValidationError(f"{where}: catalog version questionId differs from row")
            existing = versions.get(identity)
            if existing is None:
                versions[identity] = version
            elif existing.get("rawVersionSha256") != version.get("rawVersionSha256"):
                raise ValidationError(
                    f"{where}: catalog version {identity} has inconsistent rawVersionSha256"
                )
            dispute_refs.setdefault(identity, {})[event_key] = dispute_ref

    records = []
    tiers = {"api_history_only": 0, "unknown": 0}
    for identity in sorted(versions):
        version = versions[identity]
        where = f"catalog version {identity}"
        groups = _event_group_ids(version, where)
        if groups == [None]:
            counts["versionsWithoutEventGroupId"] += 1
        elif len(groups) > 1:
            counts["versionsWithMultipleEventGroupIds"] += 1
        if version.get("publicTermsConflict"):
            counts["publicTermsConflictVersions"] += 1
        if version.get("trainingHoldout"):
            counts["trainingHoldoutVersions"] += 1
        observation = version.get("privateStateObservation")
        observation = observation if isinstance(observation, dict) else {}
        private_fields = {
            key: observation[key] for key in PRIVATE_OBSERVATION_FIELDS if key in observation
        }
        version_ref = {
            "kind": "catalog_market_version",
            **{key: version.get(key) for key in VERSION_REF_FIELDS},
        }
        map_ref = {"kind": "dispute_catalog_map", **map_binding}
        refs = [map_ref, version_ref] + [
            dispute_refs[identity][key] for key in sorted(dispute_refs[identity])
        ]
        for group in groups:
            record = {
                **{key: version.get(key) for key in OPTIONAL_IDS},
                "eventGroupId": group,
                "question": version.get("question"),
                "rules": version.get("rules"),
                "outcomeLabels": version.get("outcomeLabels"),
                **private_fields,
                "publicTermsConflict": bool(version.get("publicTermsConflict")),
                "sourceRefs": refs,
            }
            tiers[classify_gamma(record)] += 1
            records.append(record)
    counts["distinctCatalogVersions"] = len(versions)
    counts["gammaRecords"] = len(records)
    counts["evidenceTierPreview"] = tiers
    return records, counts


def coverage_observations(
    unmatched: Iterator[tuple[int, bytes, dict[str, Any]]],
    unmapped: Iterator[tuple[int, bytes, dict[str, Any]]],
    *,
    unmatched_binding: dict[str, Any],
    unmapped_binding: dict[str, Any],
) -> dict[str, Any]:
    unmatched_rows = []
    for line_number, _line, row in unmatched:
        where = f"{unmatched_binding['path']}:{line_number}"
        if row.get("catalogVersions"):
            raise ValidationError(f"{where}: unmatched row carries catalogVersions")
        unmatched_rows.append(
            {
                "questionId": row.get("questionId"),
                "eventKey": row.get("eventKey"),
                "mappingStatus": row.get("mappingStatus"),
                "disputeRawSha256": row.get("disputeRawSha256"),
            }
        )
    unmapped_rows = []
    for line_number, _line, row in unmapped:
        where = f"{unmapped_binding['path']}:{line_number}"
        lifecycle = row.get("lifecycle")
        if not isinstance(lifecycle, dict):
            raise ValidationError(f"{where}: lifecycle must be an object")
        if row.get("questionId") is not None:
            raise ValidationError(f"{where}: unmapped request carries a questionId")
        unmapped_rows.append(
            {
                "eventKey": row.get("eventKey"),
                "mappingStatus": lifecycle.get("mappingStatus"),
                "adapter": lifecycle.get("adapter"),
                "requester": row.get("requester"),
            }
        )

    def tally(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in rows:
            label = str(row.get(key))
            result[label] = result.get(label, 0) + 1
        return dict(sorted(result.items()))

    return {
        "schemaVersion": OBSERVATIONS_SCHEMA_VERSION,
        "admission": "none; coverage observations are not cohort records",
        "unmatchedCatalogMap": {
            "source": unmatched_binding,
            "count": len(unmatched_rows),
            "distinctQuestionIds": len({row["questionId"] for row in unmatched_rows}),
            "byMappingStatus": tally(unmatched_rows, "mappingStatus"),
            "questionIds": sorted({row["questionId"] for row in unmatched_rows if row["questionId"]}),
            "records": unmatched_rows,
        },
        "unmappedRequests": {
            "source": unmapped_binding,
            "count": len(unmapped_rows),
            "byMappingStatus": tally(unmapped_rows, "mappingStatus"),
            "records": unmapped_rows,
        },
    }


def _binding(path: Path) -> dict[str, Any]:
    sha, size = file_digest(path)
    return {"path": str(path), "sha256": sha, "bytes": size}


def prepare(
    *,
    map_dir: Path,
    events: Path,
    unmapped_requests: Path,
    output_dir: Path,
    exclude_ids: list[Path],
    prior_manifest: Path | None,
    seed: str,
) -> dict[str, Any]:
    manifest_path = map_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("schemaVersion") != MAP_SCHEMA_VERSION:
        raise ValidationError(f"{manifest_path}: unexpected schemaVersion")
    artifacts = manifest.get("artifacts") or {}
    mapped_path = map_dir / str(artifacts.get("mapped", {}).get("path", "mapped-private.jsonl"))
    unmatched_path = map_dir / str(
        artifacts.get("unmatched", {}).get("path", "unmatched-private.jsonl")
    )
    map_binding = {"manifest": _binding(manifest_path)}
    map_binding["mapped"] = verify_binding(mapped_path, artifacts.get("mapped"), "mapped")
    map_binding["unmatched"] = verify_binding(
        unmatched_path, artifacts.get("unmatched"), "unmatched"
    )
    events_binding = _binding(events)
    declared_events = [
        item
        for item in manifest.get("inputs", [])
        if isinstance(item, dict) and item.get("path") == str(events)
    ]
    if not declared_events:
        raise ValidationError("events path is not among the mapping manifest inputs")
    if declared_events[0].get("sha256") != events_binding["sha256"]:
        raise ValidationError("events file sha256 differs from the mapping manifest input")
    unmapped_binding = _binding(unmapped_requests)
    union_manifest_path = unmapped_requests.with_name("manifest.json")
    if union_manifest_path.exists():
        union_manifest = json.loads(union_manifest_path.read_bytes())
        declared = (union_manifest.get("outputs") or {}).get("unmappedRequests") or {}
        if declared.get("sha256") != unmapped_binding["sha256"]:
            raise ValidationError("unmapped-requests sha256 differs from its union manifest")
        unmapped_binding["manifest"] = _binding(union_manifest_path)

    event_index = index_events(events)
    flat_map_binding = {
        "manifestPath": map_binding["manifest"]["path"],
        "manifestSha256": map_binding["manifest"]["sha256"],
        "path": map_binding["mapped"]["path"],
        "sha256": map_binding["mapped"]["sha256"],
    }
    records, counts = build_gamma_records(
        iter_jsonl(mapped_path), map_binding=flat_map_binding, events=event_index
    )
    observations = coverage_observations(
        iter_jsonl(unmatched_path),
        iter_jsonl(unmapped_requests),
        unmatched_binding=map_binding["unmatched"],
        unmapped_binding=unmapped_binding,
    )
    exclusion_bindings = []
    for path in exclude_ids:
        exclusion_bindings.append({**_binding(path), "count": len(ids_from(path))})

    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    gamma_path = output_dir / GAMMA_FILENAME
    gamma_bytes = b"".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for record in records
    )
    _write_once(gamma_path, gamma_bytes)
    observations_bytes = json_bytes(observations)
    _write_once(output_dir / OBSERVATIONS_FILENAME, observations_bytes)
    cohort_dir = output_dir / "cohort"
    command = ["python3", "-m", "app.scripts.research.disputes", "--events", str(events), "--gamma", str(gamma_path)]
    for path in exclude_ids:
        command += ["--exclude-ids", str(path)]
    command += ["--seed", seed, "--output", str(cohort_dir)]
    plan = {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "purpose": (
            "Replace the v1 blanket mapping_pending quarantine with catalog-mapped Gamma "
            "rows; admission remains evidence_pending and label review is still required."
        ),
        "codeHashes": {
            name: digest(Path(__file__).with_name(name).read_bytes())
            for name in ("prepare_gamma_from_map.py", "pipeline.py", "__main__.py")
        },
        "inputs": {
            "disputeCatalogMap": map_binding,
            "events": {**events_binding, "rows": len(event_index)},
            "unmappedRequests": {
                **unmapped_binding,
                "rows": observations["unmappedRequests"]["count"],
            },
            "priorIdExclusions": exclusion_bindings,
            "priorCohortManifest": _binding(prior_manifest) if prior_manifest else None,
        },
        "derived": {
            "gamma": {
                "path": str(gamma_path),
                "sha256": digest(gamma_bytes),
                "bytes": len(gamma_bytes),
                "rows": len(records),
                "recordGrain": "one row per (marketId, versionId, eventGroupId)",
            },
            "observations": {
                "path": str(output_dir / OBSERVATIONS_FILENAME),
                "sha256": digest(observations_bytes),
                "bytes": len(observations_bytes),
                "unmatched": observations["unmatchedCatalogMap"]["count"],
                "unmappedRequests": observations["unmappedRequests"]["count"],
            },
        },
        "counts": {
            **counts,
            "unmatchedRows": observations["unmatchedCatalogMap"]["count"],
            "unmappedRequestRows": observations["unmappedRequests"]["count"],
        },
        "cohortCommand": command,
        "seed": seed,
        "trainingAdmission": "none; derived rows are evidence_pending inputs, not labels",
    }
    _write_once(output_dir / PLAN_FILENAME, json_bytes(plan))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive Gamma-style JSONL and coverage observations from a dispute-catalog map"
    )
    parser.add_argument("--map-dir", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--unmapped-requests", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--exclude-ids", type=Path, action="append", default=[])
    parser.add_argument("--prior-manifest", type=Path, default=None)
    parser.add_argument("--seed", default="disputed-cohort-v2")
    args = parser.parse_args()
    os.umask(0o077)
    plan = prepare(
        map_dir=args.map_dir,
        events=args.events,
        unmapped_requests=args.unmapped_requests,
        output_dir=args.output_dir,
        exclude_ids=args.exclude_ids,
        prior_manifest=args.prior_manifest,
        seed=args.seed,
    )
    print(json.dumps({"counts": plan["counts"], "gamma": plan["derived"]["gamma"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
