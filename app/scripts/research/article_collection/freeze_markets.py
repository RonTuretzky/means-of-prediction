#!/usr/bin/env python3
"""Freeze an offline, article-benchmark market universe from saved pages."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path("/Users/wk/.local/share/means-of-prediction")
PAGES = BASE / "polymarket-pages"
OUT = Path(os.environ.get("MOP_ARTICLE_UNIVERSE_OUT", str(BASE / "article-market-universe-20260913-v3")))
DEV_IDS = BASE / "slides/astra-qwen-nyt-round1-20260912/public-inputs.json"
RESERVED = BASE / "qwen-evaluation-reservation-20260912/provenance/excluded-market-ids.json"
FOLLOWUP = BASE / "dataset-expansion-followup-20260912-2054/provenance/excluded-market-ids.json"
SEED = "article-universe-v3-20260913"
START = "2026-08-29T13:38:08.478Z"
END = "2026-09-12T13:38:08.478Z"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def ids_from(path: Path) -> set[str]:
    obj = json.loads(path.read_bytes())
    if isinstance(obj, list):
        values = obj
    elif isinstance(obj, dict) and isinstance(obj.get("all"), list):
        values = obj["all"]
    else:
        raise ValueError(f"unsupported exclusion ID shape: {path}")
    result = set()
    for value in values:
        if isinstance(value, dict):
            value = value.get("marketId", value.get("id"))
        if value is not None and str(value):
            result.add(str(value))
    return result


def explicit_event_keys(row: dict[str, Any]) -> list[str]:
    keys = set()
    events = row.get("events")
    if not isinstance(events, list):
        return []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id, slug = event.get("id"), event.get("slug")
        if event_id is not None and str(event_id):
            keys.add(f"event-id:{event_id}")
        elif slug is not None and str(slug):
            keys.add(f"event-slug:{slug}")
    return sorted(keys)


def group_key(row: dict[str, Any]) -> tuple[str, bool] | None:
    keys = explicit_event_keys(row)
    if len(keys) > 1:
        return None
    if keys:
        return keys[0], True
    return f"market-id:{row['id']}", False


def is_one_hot(labels: Any, prices: Any) -> bool:
    if not (isinstance(labels, list) and len(labels) == 2 and isinstance(prices, list) and len(prices) == 2):
        return False
    try:
        return sorted(float(x) for x in prices) == [0.0, 1.0]
    except (TypeError, ValueError):
        return False


def closed_state(value: object) -> str:
    if value is True:
        return "closed"
    if value is False:
        return "open"
    return "unknown"


def version_reference(path: Path | str, page_hash: str, row: dict[str, Any]) -> dict[str, Any]:
    return {"page": str(path), "pageSha256": page_hash, "rowSha256": digest(json_bytes(row))}


def register_version(
    first: dict[str, dict[str, Any]],
    conflicts: dict[str, list[dict[str, Any]]],
    *, market_id: str, row: dict[str, Any], page: Path | str, page_hash: str,
) -> None:
    reference = version_reference(page, page_hash, row)
    prior = first.get(market_id)
    if prior is None:
        first[market_id] = {"row": row, "reference": reference}
        return
    if prior["reference"]["rowSha256"] == reference["rowSha256"]:
        return
    versions = conflicts.setdefault(market_id, [prior["reference"]])
    if all(item["rowSha256"] != reference["rowSha256"] for item in versions):
        versions.append(reference)


def artifact_entry(filename: str, data: bytes, count: int) -> dict[str, Any]:
    return {"path": filename, "sha256": digest(data), "bytes": len(data), "count": count}


def write_private(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    os.umask(0o077)
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite existing frozen output: {OUT}")
    pages = sorted(path for path in PAGES.glob("*.json") if path.name != "manifest.json")
    if len(pages) != 4289:
        raise SystemExit(f"expected 4289 cache pages, found {len(pages)}")
    source_manifest_raw = (PAGES / "manifest.json").read_bytes()
    if not json.loads(source_manifest_raw).get("publicPaginationComplete"):
        raise SystemExit("cache manifest is not marked publicPaginationComplete")

    exclusion_inputs = {"development": DEV_IDS, "reserved": RESERVED, "followup": FOLLOWUP}
    exclusion_sets = {name: ids_from(path) for name, path in exclusion_inputs.items()}
    expected_counts = {"development": 241, "reserved": 253, "followup": 250}
    actual_counts = {name: len(values) for name, values in exclusion_sets.items()}
    if actual_counts != expected_counts:
        raise SystemExit(f"unexpected exclusion counts: expected={expected_counts} actual={actual_counts}")
    excluded = set().union(*exclusion_sets.values())

    start, end = parse_time(START), parse_time(END)
    assert start is not None and end is not None
    first: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, list[dict[str, Any]]] = {}
    page_hashes = []
    scanned = missing_market_id = 0
    for path in pages:
        raw = path.read_bytes()
        page_hash = digest(raw)
        page_hashes.append({"path": str(path), "sha256": page_hash, "bytes": len(raw)})
        payload = json.loads(raw)
        markets = payload.get("markets", [])
        if not isinstance(markets, list):
            raise SystemExit(f"page markets is not an array: {path}")
        for row in markets:
            scanned += 1
            if not isinstance(row, dict):
                missing_market_id += 1
                continue
            market_id = str(row.get("id")) if row.get("id") is not None else ""
            if not market_id:
                missing_market_id += 1
                continue
            register_version(first, conflicts, market_id=market_id, row=row, page=path, page_hash=page_hash)

    in_window = outside_window = invalid_closed_time = excluded_count = 0
    missing_rules = closed_false = closed_unknown = uncertain_binary = 0
    ambiguous_multi_event = 0
    eligible: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for market_id in sorted(first):
        if market_id in conflicts:
            continue
        row = first[market_id]["row"]
        closed_time = parse_time(row.get("closedTime"))
        if closed_time is None:
            invalid_closed_time += 1
            continue
        if not start <= closed_time <= end:
            outside_window += 1
            continue
        in_window += 1
        if market_id in excluded:
            excluded_count += 1
            continue
        rules, question = row.get("description"), row.get("question")
        if not isinstance(rules, str) or not rules.strip() or not isinstance(question, str) or not question.strip():
            missing_rules += 1
            continue
        state = closed_state(row.get("closed"))
        if state == "open":
            closed_false += 1
            continue
        if state == "unknown":
            closed_unknown += 1
            continue
        labels, prices = json_value(row.get("outcomes")), json_value(row.get("outcomePrices"))
        if not is_one_hot(labels, prices):
            uncertain_binary += 1
            continue
        grouping = group_key(row)
        if grouping is None:
            ambiguous_multi_event += 1
            continue
        key, explicit = grouping
        eligible[market_id] = row
        groups.setdefault(key, []).append({"row": row, "explicit": explicit})

    ranked = sorted(groups, key=lambda key: hashlib.sha256(f"{SEED}:{key}".encode()).hexdigest())
    selected = []
    for key in ranked[:1000]:
        item = sorted(groups[key], key=lambda candidate: str(candidate["row"]["id"]))[0]
        row = item["row"]
        selected.append({
            "marketId": str(row["id"]), "question": row.get("question"),
            "rules": row.get("description"), "outcomeLabels": json_value(row["outcomes"]),
            "slug": row.get("slug"), "resolutionSource": row.get("resolutionSource"),
            "eventGroupId": key, "eventGroupExplicit": item["explicit"],
            "endDate": row.get("endDate"), "gameStartTime": row.get("gameStartTime"),
            "eventStartTime": row.get("eventStartTime"), "declaredTimezone": row.get("timezone"),
            "createdAt": row.get("createdAt"),
        })

    source_entries = {}
    for name, path in exclusion_inputs.items():
        raw = path.read_bytes()
        source_entries[name] = {"path": str(path), "count": len(exclusion_sets[name]), "sha256": digest(raw), "bytes": len(raw)}
    exclusion_sources = {
        "sources": source_entries,
        "union": {"count": len(excluded), "sha256": digest(("\n".join(sorted(excluded)) + "\n").encode()), "ids": sorted(excluded)},
    }
    sample_bytes = json_bytes(selected)
    eligible_bytes = json_bytes(sorted(eligible))
    exclusion_bytes = json_bytes(exclusion_sources)
    output_artifacts = {
        "sample": artifact_entry("sampled-public-inputs.json", sample_bytes, len(selected)),
        "eligibleIds": artifact_entry("eligible-market-ids.json", eligible_bytes, len(eligible)),
        "exclusions": artifact_entry("exclusion-sources.json", exclusion_bytes, len(excluded)),
    }
    manifest = {
        "schemaVersion": "article-market-universe-v3", "seed": SEED,
        "window": {"start": START, "end": END, "field": "closedTime", "timezone": "UTC"},
        "sourceDirectory": str(PAGES), "sourceManifest": str(PAGES / "manifest.json"),
        "sourceManifestSha256": digest(source_manifest_raw), "collectorSha256": digest(Path(__file__).read_bytes()),
        "pageCount": len(pages), "pageHashes": page_hashes, "scannedRows": scanned,
        "uniqueMarketIdsScanned": len(first), "missingMarketIdRows": missing_market_id,
        "conflictingVersions": conflicts, "conflictedIdsExcludedBeforeEligibility": len(conflicts),
        "inWindowUniqueMarkets": in_window, "outsideWindowUniqueMarkets": outside_window,
        "invalidOrMissingClosedTime": invalid_closed_time,
        "excludedDevelopmentIds": len(exclusion_sets["development"]),
        "excludedReservedIds": len(exclusion_sets["reserved"]),
        "excludedFollowupIds": len(exclusion_sets["followup"]), "excludedUnionIds": len(excluded),
        "excludedMarketsInWindow": excluded_count, "missingRulesOrQuestion": missing_rules,
        "closedFalse": closed_false, "closedStatusUnknown": closed_unknown,
        "uncertainBinarySettlement": uncertain_binary,
        "ambiguousMultipleExplicitEvents": ambiguous_multi_event,
        "eligibleUniqueMarkets": len(eligible), "eventGroups": len(groups),
        "unknownEventGroups": sum(not any(item["explicit"] for item in group) for group in groups.values()),
        "sampleCount": len(selected), "outputArtifacts": output_artifacts, "judgeFieldsOnly": True,
        "outcomesAndPrices": "used only for eligibility audit; never written to sample",
        "eventPolicy": "one explicit event ID (preferred) or slug; multiple explicit events excluded; absent event grouped by market ID and flagged unknown",
    }

    OUT.mkdir(mode=0o700)
    write_private(OUT / "sampled-public-inputs.json", sample_bytes)
    write_private(OUT / "eligible-market-ids.json", eligible_bytes)
    write_private(OUT / "exclusion-sources.json", exclusion_bytes)
    write_private(OUT / "manifest.json", json_bytes(manifest))
    keys = ("pageCount", "scannedRows", "uniqueMarketIdsScanned", "inWindowUniqueMarkets", "eligibleUniqueMarkets", "excludedUnionIds", "closedFalse", "closedStatusUnknown", "ambiguousMultipleExplicitEvents", "sampleCount")
    print(json.dumps({key: manifest[key] for key in keys}, sort_keys=True))


if __name__ == "__main__":
    main()
