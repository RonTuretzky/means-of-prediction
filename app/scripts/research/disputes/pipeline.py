"""Normalize dispute evidence into a separate, review-gated training cohort."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "disputed-market-cohort-v1"
EVENT_REQUIRED = (
    "chainId",
    "oracleAddress",
    "transactionHash",
    "logIndex",
    "requester",
    "identifier",
    "timestamp",
    "ancillaryData",
    "sourceRefs",
)
OPTIONAL_IDS = ("questionId", "conditionId", "marketId")
PRIVATE_OBSERVATION_FIELDS = (
    "outcome",
    "resolvedOutcome",
    "resolution",
    "umaResolutionStatus",
    "umaResolutionStatuses",
    "umaResolutionStatusHistory",
)


class ValidationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        + b"\n"
    )


def _string(value: Any, name: str) -> str:
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise ValidationError(f"{name} must be a nonempty string or integer")
    return str(value)


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _source_refs(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{name} must be a nonempty list")
    for ref in value:
        if not isinstance(ref, (str, dict)):
            raise ValidationError(f"{name} entries must be strings or objects")
    return value


def _status_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in {"[", "{"}:
            try:
                yield from _status_strings(json.loads(stripped))
                return
            except json.JSONDecodeError:
                pass
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _status_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if "status" in key.casefold() or key in {"state", "event"}:
                yield from _status_strings(item)


def classify_gamma(row: dict[str, Any]) -> str:
    historical = []
    for field in ("umaResolutionStatuses", "umaResolutionStatusHistory"):
        historical.extend(_status_strings(row.get(field)))
    if any(value.strip().casefold() == "disputed" for value in historical):
        return "api_history_only"
    # A current resolved state is not evidence that no dispute occurred.
    return "unknown"


def _event_key(row: dict[str, Any]) -> str:
    return ":".join(
        (
            str(row["chainId"]),
            str(row["oracleAddress"]).casefold(),
            str(row["transactionHash"]).casefold(),
            str(row["logIndex"]),
        )
    )


def _request_group(row: dict[str, Any], kind: str) -> str:
    if kind == "event":
        material = {
            key: str(row[key]).casefold()
            for key in (
                "chainId",
                "oracleAddress",
                "requester",
                "identifier",
                "ancillaryData",
            )
        }
        return "oracle-request:" + digest(json_bytes(material))
    for key in ("conditionId", "questionId", "marketId"):
        if row.get(key) is not None:
            return f"gamma-{key}:{str(row[key]).casefold()}"
    identity = {
        "question": row.get("question"),
        "slug": row.get("slug"),
        "sourceRefs": row.get("sourceRefs"),
    }
    return "gamma-unknown:" + digest(json_bytes(identity))


def deterministic_split(group: str, seed: str) -> str:
    bucket = int(digest(f"{seed}:{group}".encode())[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "dev"
    return "test"


def load_jsonl(path: Path, kind: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = path.read_bytes()
    try:
        container = json.loads(raw)
    except json.JSONDecodeError:
        container = None
    if isinstance(container, list):
        source_rows = [(index, json_bytes(row).rstrip(b"\n")) for index, row in enumerate(container, 1)]
    elif isinstance(container, dict) and isinstance(container.get("events"), list):
        source_rows = [
            (index, json_bytes(row).rstrip(b"\n"))
            for index, row in enumerate(container["events"], 1)
        ]
    else:
        source_rows = list(enumerate(raw.splitlines(), start=1))
    rows = []
    for line_number, line in source_rows:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{path}:{line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValidationError(f"{path}:{line_number} must be an object")
        rows.append(
            {
                "row": row,
                "rawLineSha256": digest(line),
                "inputPath": str(path),
                "lineNumber": line_number,
                "kind": kind,
            }
        )
    return rows, {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def ids_from(path: Path) -> set[str]:
    obj = json.loads(path.read_bytes())
    if isinstance(obj, list):
        values = obj
    elif isinstance(obj, dict) and isinstance(obj.get("all"), list):
        values = obj["all"]
    else:
        raise ValidationError(f"unsupported exclusion list shape: {path}")
    result = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("marketId", value.get("id"))
        if value is not None:
            result.add(str(value).casefold())
    return result


def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    for field in EVENT_REQUIRED:
        if field not in row:
            raise ValidationError(f"event missing {field}")
    normalized = {
        "chainId": _string(row["chainId"], "chainId"),
        "oracleAddress": _string(row["oracleAddress"], "oracleAddress").casefold(),
        "transactionHash": _string(row["transactionHash"], "transactionHash").casefold(),
        "logIndex": int(row["logIndex"]),
        "requester": _string(row["requester"], "requester").casefold(),
        "identifier": _string(row["identifier"], "identifier"),
        "timestamp": _string(row["timestamp"], "timestamp"),
        "ancillaryData": _string(row["ancillaryData"], "ancillaryData"),
        "sourceRefs": _source_refs(row["sourceRefs"], "sourceRefs"),
        **{key: _optional_string(row.get(key), key) for key in OPTIONAL_IDS},
        "eventGroupId": _optional_string(row.get("eventGroupId"), "eventGroupId"),
    }
    lifecycle = row.get("lifecycle")
    if not isinstance(lifecycle, dict):
        raise ValidationError("event lifecycle must be an object")
    if lifecycle.get("eventName") != "DisputePrice" or lifecycle.get("blockNumber") is None:
        raise ValidationError("event lifecycle requires DisputePrice eventName and blockNumber")
    normalized["lifecycle"] = lifecycle
    declared_subgraph = any(
        isinstance(ref, dict) and ref.get("kind") == "uma_polygon_oov2_subgraph"
        for ref in normalized["sourceRefs"]
    )
    normalized["sourceVerification"] = {
        "basis": (
            "indexed_subgraph_event"
            if declared_subgraph
            else "normalized_input_declaration"
        ),
        "eventName": lifecycle["eventName"],
        "blockNumber": lifecycle["blockNumber"],
        "rpcReceiptVerified": lifecycle.get("rpcReceiptVerified") is True,
        "removedStatusKnown": isinstance(lifecycle.get("removed"), bool),
    }
    normalized["eventKey"] = _event_key(normalized)
    normalized["requestGroup"] = _request_group(normalized, "event")
    normalized["rawLineSha256"] = item["rawLineSha256"]
    normalized["inputRef"] = {
        "path": item["inputPath"],
        "lineNumber": item["lineNumber"],
    }
    return normalized


def _normalize_gamma(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    labels = row.get("outcomeLabels")
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except json.JSONDecodeError:
            labels = None
    if not isinstance(labels, list) or not all(isinstance(value, str) for value in labels):
        labels = None
    normalized = {
        **{key: _optional_string(row.get(key), key) for key in OPTIONAL_IDS},
        "eventGroupId": _optional_string(row.get("eventGroupId"), "eventGroupId"),
        "question": row.get("question") if isinstance(row.get("question"), str) else None,
        "rules": row.get("rules") if isinstance(row.get("rules"), str) else None,
        "slug": row.get("slug") if isinstance(row.get("slug"), str) else None,
        "outcomeLabels": labels,
        "sourceRefs": _source_refs(row.get("sourceRefs"), "sourceRefs"),
        "rawLineSha256": item["rawLineSha256"],
        "inputRef": {"path": item["inputPath"], "lineNumber": item["lineNumber"]},
    }
    normalized["requestGroup"] = _request_group(normalized, "gamma")
    normalized["evidenceTier"] = classify_gamma(row)
    normalized["privateObservations"] = {
        key: row[key] for key in PRIVATE_OBSERVATION_FIELDS if key in row
    }
    return normalized


def _overlaps(record: dict[str, Any], exclusions: set[str]) -> list[str]:
    return sorted(
        str(record[key])
        for key in OPTIONAL_IDS
        if record.get(key) is not None and str(record[key]).casefold() in exclusions
    )


def _group_links(record: dict[str, Any]) -> list[str]:
    links = [record["requestGroup"]]
    if record.get("eventConflictKey"):
        links.append(f"event-conflict:{record['eventConflictKey']}")
    for key in (*OPTIONAL_IDS, "eventGroupId"):
        if record.get(key) is not None:
            links.append(f"{key}:{str(record[key]).casefold()}")
    return sorted(set(links))


def _connected_components(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    parents = list(range(len(records)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    first_for_link: dict[str, int] = {}
    for index, record in enumerate(records):
        for link in _group_links(record):
            if link in first_for_link:
                union(index, first_for_link[link])
            else:
                first_for_link[link] = index
    components: dict[int, list[dict[str, Any]]] = {}
    for index, record in enumerate(records):
        components.setdefault(find(index), []).append(record)
    return [components[key] for key in sorted(components)]


def build_cohort(
    event_items: list[dict[str, Any]],
    gamma_items: list[dict[str, Any]],
    exclusions: set[str],
    *,
    seed: str,
) -> dict[str, Any]:
    quarantined = []
    event_groups: dict[str, list[dict[str, Any]]] = {}
    for item in event_items:
        event = _normalize_event(item)
        event_groups.setdefault(event["eventKey"], []).append(event)

    records = []
    for event_key in sorted(event_groups):
        versions = event_groups[event_key]
        comparable = [
            {key: value for key, value in version.items() if key not in {"sourceRefs", "rawLineSha256", "inputRef"}}
            for version in versions
        ]
        if len({digest(json_bytes(value)) for value in comparable}) > 1:
            for version in versions:
                version["eventConflictKey"] = event_key
                version["conflictBlocked"] = True
                version["evidenceTier"] = "event_confirmed"
                records.append(version)
            continue
        record = dict(versions[0])
        record["sourceRefs"] = sorted(
            {json.dumps(ref, sort_keys=True) for version in versions for ref in version["sourceRefs"]}
        )
        record["sourceRefs"] = [json.loads(ref) for ref in record["sourceRefs"]]
        record["rawLineSha256s"] = sorted(version["rawLineSha256"] for version in versions)
        record["evidenceTier"] = "event_confirmed"
        records.append(record)

    records.extend(_normalize_gamma(item) for item in gamma_items)
    private_rows, public_rows = [], []
    for component in _connected_components(records):
        links = sorted({link for record in component for link in _group_links(record)})
        cohort_group = "connected:" + digest(json_bytes(links))
        overlap_ids = sorted(
            {value for record in component for value in _overlaps(record, exclusions)}
        )
        if any(record.get("conflictBlocked") for record in component):
            quarantined.append(
                {
                    "reason": "conflicting_event_versions",
                    "cohortGroup": cohort_group,
                    "records": component,
                }
            )
            continue
        if overlap_ids:
            quarantined.append(
                {
                    "reason": "prior_id_overlap",
                    "overlapIds": overlap_ids,
                    "cohortGroup": cohort_group,
                    "records": component,
                }
            )
            continue
        affirmative = any(
            record["evidenceTier"] in {"event_confirmed", "api_history_only"}
            for record in component
        )
        if not affirmative:
            quarantined.append(
                {
                    "reason": "no_affirmative_dispute_evidence",
                    "cohortGroup": cohort_group,
                    "records": component,
                }
            )
            continue
        mapping_ready = any(
            isinstance(record.get("question"), str)
            and record["question"].strip()
            and isinstance(record.get("rules"), str)
            and record["rules"].strip()
            for record in component
        )
        if not mapping_ready:
            quarantined.append(
                {
                    "reason": "mapping_pending",
                    "cohortGroup": cohort_group,
                    "records": component,
                }
            )
            continue
        public_packet_ready = any(
            isinstance(record.get("question"), str)
            and record["question"].strip()
            and isinstance(record.get("rules"), str)
            and record["rules"].strip()
            and isinstance(record.get("outcomeLabels"), list)
            and len(record["outcomeLabels"]) >= 2
            and all(
                isinstance(label, str) and label.strip()
                for label in record["outcomeLabels"]
            )
            for record in component
        )
        if not public_packet_ready:
            quarantined.append(
                {
                    "reason": "public_packet_ineligible",
                    "cohortGroup": cohort_group,
                    "records": component,
                }
            )
            continue
        split = deterministic_split(cohort_group, seed)
        for record in sorted(
            component,
            key=lambda value: value.get("rawLineSha256s", [value["rawLineSha256"]]),
        ):
            if record["evidenceTier"] == "unknown":
                quarantined.append(
                    {
                        "reason": "api_status_unknown_linked_to_affirmative_evidence",
                        "cohortGroup": cohort_group,
                        "record": record,
                    }
                )
                continue
            record_id = digest(
                json_bytes(
                    {
                        "tier": record["evidenceTier"],
                        "group": cohort_group,
                        "raw": record.get("rawLineSha256s", [record["rawLineSha256"]]),
                    }
                )
            )
            private_rows.append(
                {
                    "cohortRecordId": record_id,
                    "cohortGroup": cohort_group,
                    "split": split,
                    "admission": "evidence_pending",
                    "labelReview": "required",
                    "outcomeUse": "private_observation_not_truth_gold",
                    **record,
                }
            )
        packets = {}
        for record in component:
            if not (
                isinstance(record.get("question"), str)
                and record["question"].strip()
                and isinstance(record.get("rules"), str)
                and record["rules"].strip()
                and isinstance(record.get("outcomeLabels"), list)
                and len(record["outcomeLabels"]) >= 2
                and all(isinstance(label, str) and label.strip() for label in record["outcomeLabels"])
            ):
                continue
            packet = {
                "split": split,
                "cohortGroup": cohort_group,
                "eventGroupId": record.get("eventGroupId"),
                "marketId": record.get("marketId"),
                "questionId": record.get("questionId"),
                "conditionId": record.get("conditionId"),
                "question": record["question"],
                "rules": record["rules"],
                "outcomeLabels": record["outcomeLabels"],
            }
            packet_key = digest(json_bytes(packet))
            packets[packet_key] = {
                "cohortRecordId": digest(
                    json_bytes({"group": cohort_group, "publicTerms": packet})
                ),
                **packet,
            }
        public_rows.extend(packets[key] for key in sorted(packets))
    return {
        "public": public_rows,
        "private": private_rows,
        "quarantine": quarantined,
    }


def _write_once(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def write_cohort(
    output: Path,
    cohort: dict[str, Any],
    *,
    seed: str,
    input_bindings: list[dict[str, Any]],
    exclusion_bindings: list[dict[str, Any]],
    curriculum_cap: float,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.mkdir(mode=0o700, parents=True)
    output.chmod(0o700)
    artifacts = {
        "publicJudgeInputs": json_bytes(
            {"schemaVersion": "market-judge-input-v1", "records": cohort["public"]}
        ),
        "privateAdmission": json_bytes(
            {"schemaVersion": SCHEMA_VERSION, "records": cohort["private"]}
        ),
        "quarantine": json_bytes(
            {"schemaVersion": SCHEMA_VERSION, "records": cohort["quarantine"]}
        ),
    }
    filenames = {
        "publicJudgeInputs": "public-judge-inputs.json",
        "privateAdmission": "private-admission.json",
        "quarantine": "quarantine.json",
    }
    artifact_manifest = {}
    for key, data in artifacts.items():
        _write_once(output / filenames[key], data)
        artifact_manifest[key] = {
            "path": filenames[key],
            "sha256": digest(data),
            "bytes": len(data),
        }
    split_counts = {
        split: sum(row["split"] == split for row in cohort["private"])
        for split in ("train", "dev", "test")
    }
    tier_counts = {
        tier: sum(row["evidenceTier"] == tier for row in cohort["private"])
        for tier in ("event_confirmed", "api_history_only")
    }
    quarantined_records = sum(
        len(item["records"]) if isinstance(item.get("records"), list) else 1
        for item in cohort["quarantine"]
    )
    curriculum = {
        "schemaVersion": "disputed-curriculum-v1",
        "enabled": False,
        "activationRequirement": "independently reviewed evidence and labels",
        "appliesTo": ["regex", "qwen"],
        "sharedCaseAndRequestSplits": True,
        "proposedMaximumReviewedDisputedFraction": curriculum_cap,
        "capBasis": "configuration default, not a measured optimum",
        "hardCasePurposes": ["false_positive", "ambiguity", "source_timing"],
        "payoutPolicy": "private observation, never automatic truth gold",
        "heldOutMetricsReportedSeparately": True,
        "automaticTraining": False,
        "admittedReviewedTrainingCases": 0,
    }
    curriculum_bytes = json_bytes(curriculum)
    _write_once(output / "curriculum.json", curriculum_bytes)
    artifact_manifest["curriculum"] = {
        "path": "curriculum.json",
        "sha256": digest(curriculum_bytes),
        "bytes": len(curriculum_bytes),
    }
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "seed": seed,
        "codeHashes": {name: digest(Path(__file__).with_name(name).read_bytes()) for name in ("pipeline.py", "__main__.py")},
        "inputs": input_bindings,
        "priorIdExclusions": exclusion_bindings,
        "artifacts": artifact_manifest,
        "counts": {
            "evidencePending": len(cohort["private"]),
            "publicJudgeInputs": len(cohort["public"]),
            "quarantinedGroups": len(cohort["quarantine"]),
            "quarantinedRecords": quarantined_records,
            "tiers": tier_counts,
            "splits": split_counts,
            "reviewedTrainingAdmissions": 0,
        },
        "trainingLaunched": False,
    }
    _write_once(output / "manifest.json", json_bytes(manifest))
    return manifest
