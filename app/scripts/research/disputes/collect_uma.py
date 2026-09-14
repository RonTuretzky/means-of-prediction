#!/usr/bin/env python3
"""Bounded, write-once collector for disputed Polygon UMA OOv2 requests.

This collector is deliberately limited to the official UMA Polygon OOv2
subgraph. It retains all returned dispute requests, including ones no longer in
the Disputed state, and does not claim all Polymarket disputes or all UMA data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from Crypto.Hash import keccak


OUTPUT = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914"
ENDPOINT = "https://api.studio.thegraph.com/query/1057/polygon-optimistic-oracle-v2/1.2.0"
ORACLE_ADDRESS = "0xee3afe347d5c74317041e2618c49534daf887c24"
DEPLOYMENT_SOURCE = "https://raw.githubusercontent.com/UMAprotocol/subgraphs/master/packages/optimistic-oracle-v2/manifest/data/polygon.json"
ADAPTER_SOURCE = "https://docs.polymarket.com/concepts/resolution"
ADAPTER_V2 = "0x6a9d222616c90fca5754cd1333cfd9b7fb6a4f74"
PAGE_SIZE = 1000
MAX_PAGES = 100
SCHEMA_VERSION = "uma-polygon-oov2-dispute-collection-v1"

META_QUERY = "query { _meta { block { number hash } } }"
REQUEST_QUERY = """query($first: Int!, $after: String!, $block: Int!) {
  optimisticPriceRequests(
    first: $first,
    where: { id_gt: $after, disputeTimestamp_not: null },
    orderBy: id,
    orderDirection: asc,
    block: { number: $block }
  ) {
    id requester identifier ancillaryData time currency reward finalFee proposer
    proposedPrice proposalExpirationTimestamp disputer settlementPrice
    settlementPayout settlementRecipient state requestTimestamp requestBlockNumber
    requestHash requestLogIndex proposalTimestamp proposalBlockNumber proposalHash
    proposalLogIndex disputeTimestamp disputeBlockNumber disputeHash disputeLogIndex
    settlementTimestamp settlementBlockNumber settlementHash settlementLogIndex
    customLiveness bond eventBased
  }
}"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_once(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def private_dir(path: Path) -> None:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)


def graph_post(payload: dict[str, Any]) -> tuple[int | None, bytes | None, str | None]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(ENDPOINT, data=body, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "means-of-prediction-uma-dispute-collector/1.0"}, method="POST")
    try:
        with build_opener().open(request, timeout=45) as response:
            return response.status, response.read(), None
    except HTTPError as exc:
        return exc.code, exc.read(), f"HTTP {exc.code}"
    except (URLError, TimeoutError, ValueError) as exc:
        return None, None, str(exc)


def ancillary_keccak(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        raw = bytes.fromhex(value[2:] if value.startswith("0x") else value)
    except ValueError:
        return None
    value_hash = keccak.new(digest_bits=256)
    value_hash.update(raw)
    return "0x" + value_hash.hexdigest()


def normalize(row: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
    requester = row.get("requester")
    requester_lower = requester.lower() if isinstance(requester, str) else None
    mapping_status = "allowlisted_polymarket_adapter_v2" if requester_lower == ADAPTER_V2 else "unmapped_requester"
    ancillary = row.get("ancillaryData")
    return {
        "chainId": 137,
        "oracleAddress": ORACLE_ADDRESS,
        "transactionHash": row.get("disputeHash"),
        "logIndex": row.get("disputeLogIndex"),
        "requester": requester,
        "identifier": row.get("identifier"),
        "timestamp": row.get("time"),
        "ancillaryData": ancillary,
        "questionId": None,
        "conditionId": None,
        "marketId": None,
        "sourceRefs": [
            {"kind": "uma_polygon_oov2_subgraph", "endpoint": ENDPOINT, "requestId": row.get("id")},
            {"kind": "uma_deployment_manifest", "url": DEPLOYMENT_SOURCE, "oracleAddress": ORACLE_ADDRESS},
        ],
        "lifecycle": {
            "eventName": "DisputePrice",
            "blockNumber": row.get("disputeBlockNumber"),
            "blockHash": block.get("hash"),
            "removed": None,
            "finality": "subgraph indexed block snapshot",
            "scanBounds": {"indexedBlock": block.get("number"), "pageSize": PAGE_SIZE, "maxPages": MAX_PAGES},
            "requestId": row.get("id"),
            "stateAtIndexedBlock": row.get("state"),
            "settlementPrice": row.get("settlementPrice"),
            "settlementTimestamp": row.get("settlementTimestamp"),
            "settlementBlockNumber": row.get("settlementBlockNumber"),
            "settlementHash": row.get("settlementHash"),
            "ancillaryDataKeccak256": ancillary_keccak(ancillary),
            "ancillaryDataKeccak256Basis": "Ethereum Keccak-256 of decoded hex ancillaryData; derived request-data fingerprint only, not an audited market questionId",
            "mappingStatus": mapping_status,
        },
    }


def parse_graph(raw: bytes) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "response is not an object"
    if payload.get("errors"):
        return None, f"GraphQL errors: {payload['errors']}"
    data = payload.get("data")
    return (data, None) if isinstance(data, dict) else (None, "missing data")


def finish_existing(output: Path) -> int:
    """Continue an interrupted capture from its archived cursor without replaying a page."""
    plan = json.loads((output / "collection-plan.json").read_bytes())
    probe = json.loads((output / "probe.json").read_bytes())
    indexed_block = probe.get("indexedBlock")
    if plan.get("schema_version") != SCHEMA_VERSION or not isinstance(indexed_block, dict) or not isinstance(indexed_block.get("number"), int):
        raise RuntimeError("existing capture lacks a valid frozen plan/probe")
    if (output / "manifest.json").exists() or (output / "normalized-dispute-events.json").exists():
        raise RuntimeError("existing capture has already been finalized")
    snapshot = output / "resume-code-snapshot.py"
    write_once(snapshot, Path(__file__).read_bytes())
    page_files = sorted((output / "raw").glob("[0-9][0-9][0-9]-requests.json"))
    if not page_files:
        raise RuntimeError("no archived request page to resume")
    rows: list[dict[str, Any]] = []
    page_log: list[dict[str, Any]] = []
    after = ""
    for page_number, path in enumerate(page_files, start=1):
        raw = path.read_bytes()
        data, parse_error = parse_graph(raw)
        batch = data.get("optimisticPriceRequests") if data else None
        if parse_error or not isinstance(batch, list) or not batch:
            raise RuntimeError(f"cannot resume from {path}: {parse_error or 'empty/missing batch'}")
        if batch != sorted(batch, key=lambda item: item.get("id", "")):
            raise RuntimeError(f"cannot resume from unordered {path}")
        rows.extend(normalize(item, indexed_block) for item in batch)
        after = batch[-1]["id"]
        page_log.append({"page": page_number, "after": "" if page_number == 1 else "archived", "httpStatus": 200, "rawFile": f"raw/{path.name}", "rawSha256": digest(raw), "rawBytes": len(raw), "returned": len(batch), "resumeSource": "archived prior response"})
    complete = True
    for page_number in range(len(page_files) + 1, MAX_PAGES + 1):
        status, raw, error = graph_post({"query": REQUEST_QUERY, "variables": {"first": PAGE_SIZE, "after": after, "block": indexed_block["number"]}})
        page = {"page": page_number, "after": after, "httpStatus": status, "error": error, "startedAt": utc_now()}
        if raw is not None:
            raw_name = f"{page_number:03d}-requests.json"
            write_once(output / "raw" / raw_name, raw)
            page.update({"rawFile": f"raw/{raw_name}", "rawSha256": digest(raw), "rawBytes": len(raw)})
        data, parse_error = parse_graph(raw) if raw is not None else (None, error)
        batch = data.get("optimisticPriceRequests") if data else None
        if parse_error or not isinstance(batch, list):
            page["parseError"] = parse_error or "missing optimisticPriceRequests list"
            page_log.append(page)
            complete = False
            break
        if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in batch) or batch != sorted(batch, key=lambda item: item["id"]):
            page["parseError"] = "invalid or unordered request rows"
            page_log.append(page)
            complete = False
            break
        rows.extend(normalize(item, indexed_block) for item in batch)
        page["returned"] = len(batch)
        page_log.append(page)
        if len(batch) < PAGE_SIZE:
            break
        next_after = batch[-1]["id"]
        if next_after <= after:
            page["parseError"] = "non-advancing cursor"
            complete = False
            break
        after = next_after
    else:
        complete = False
        page_log.append({"page": MAX_PAGES, "stopReason": "maximum page cap reached"})
    events_bytes = json_bytes({"schema_version": SCHEMA_VERSION, "indexedBlock": indexed_block, "events": rows})
    write_once(output / "normalized-dispute-events.json", events_bytes)
    mapped = sum(event["lifecycle"]["mappingStatus"].startswith("allowlisted") for event in rows)
    manifest = {"schema_version": SCHEMA_VERSION, "completedAt": utc_now(), "indexedBlock": indexed_block, "probe": probe, "pages": page_log, "resumeCode": {"path": str(snapshot), "sha256": digest(snapshot.read_bytes())}, "outputs": {"normalizedDisputeEvents": {"path": "normalized-dispute-events.json", "sha256": digest(events_bytes), "bytes": len(events_bytes)}}, "counts": {"rawPages": sum("rawFile" in page for page in page_log) + 1, "disputeRequests": len(rows), "allowlistedAdapterRequester": mapped, "unmappedRequester": len(rows) - mapped, "requestsResolvedOrSettledAtIndexedBlock": sum(event["lifecycle"]["stateAtIndexedBlock"] in {"Resolved", "Settled", "Expired"} for event in rows)}, "complete": complete, "coverage": plan["coverage"], "limitations": ["No Gamma/current-market snapshot was collected.", "questionId, conditionId, and marketId are intentionally null until an audited join.", "A dispute record proves an UMA OOv2 dispute request, not that it maps to a Polymarket market.", "Other OO versions and adapter deployments remain a known coverage gap."]}
    write_once(output / "manifest.json", json_bytes(manifest))
    print(json.dumps({"complete": complete, **manifest["counts"]}, sort_keys=True))
    return 0 if complete else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="bounded UMA Polygon OOv2 disputed-request collector")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--resume", action="store_true", help="continue a prior archived cursor without replaying it")
    args = parser.parse_args()
    output = args.output.expanduser()
    if output.exists() and not args.resume:
        raise SystemExit(f"refusing to overwrite output: {output}")
    if args.resume:
        return finish_existing(output)
    os.umask(0o077)
    private_dir(output)
    raw_dir = output / "raw"
    private_dir(raw_dir)
    code_path = Path(__file__)
    plan = {
        "schema_version": SCHEMA_VERSION,
        "createdAt": utc_now(),
        "source": {"endpoint": ENDPOINT, "network": "Polygon", "chainId": 137, "oracleAddress": ORACLE_ADDRESS, "deploymentSource": DEPLOYMENT_SOURCE, "polymarketAdapterSource": ADAPTER_SOURCE, "auditedRequesterAllowlist": {ADAPTER_V2: "UmaCtfAdapterV2"}},
        "code": {"path": str(code_path), "sha256": digest(code_path.read_bytes())},
        "requestPolicy": {"pageSize": PAGE_SIZE, "maximumPages": MAX_PAGES, "retries": 0, "oneEndpoint": True, "pagination": "id_gt ascending at pinned indexed block", "stopOnError": True},
        "coverage": "bounded Polygon Optimistic Oracle V2 subgraph only; all returned UMA disputes, not all Polymarket disputes",
        "queries": {"meta": META_QUERY, "requests": REQUEST_QUERY},
    }
    write_once(output / "collection-plan.json", json_bytes(plan))
    status, raw, error = graph_post({"query": META_QUERY})
    probe = {"startedAt": utc_now(), "httpStatus": status, "error": error, "endpoint": ENDPOINT}
    if raw is not None:
        write_once(raw_dir / "000-meta.json", raw)
        probe.update({"rawFile": "raw/000-meta.json", "rawSha256": digest(raw), "rawBytes": len(raw)})
    data, parse_error = parse_graph(raw) if raw is not None else (None, error)
    if parse_error:
        probe["parseError"] = parse_error
    indexed_block = data.get("_meta", {}).get("block") if data else None
    if not isinstance(indexed_block, dict) or not isinstance(indexed_block.get("number"), int):
        probe["result"] = "blocked_or_invalid_meta"
        write_once(output / "probe.json", json_bytes(probe))
        manifest = {"schema_version": SCHEMA_VERSION, "completedAt": utc_now(), "probe": probe, "counts": {"rawPages": 1 if raw else 0, "disputeRequests": 0}, "coverage": plan["coverage"], "complete": False}
        write_once(output / "manifest.json", json_bytes(manifest))
        print(json.dumps({"probe": probe["result"], "httpStatus": status}, sort_keys=True))
        return 1
    probe["result"] = "indexed_block_frozen"
    probe["indexedBlock"] = indexed_block
    write_once(output / "probe.json", json_bytes(probe))
    print(json.dumps({"probe": probe["result"], "indexedBlock": indexed_block["number"], "blockHash": indexed_block.get("hash")}, sort_keys=True), flush=True)

    after = ""
    rows: list[dict[str, Any]] = []
    page_log: list[dict[str, Any]] = []
    complete = True
    for page_number in range(1, MAX_PAGES + 1):
        status, raw, error = graph_post({"query": REQUEST_QUERY, "variables": {"first": PAGE_SIZE, "after": after, "block": indexed_block["number"]}})
        page = {"page": page_number, "after": after, "httpStatus": status, "error": error, "startedAt": utc_now()}
        if raw is not None:
            raw_name = f"{page_number:03d}-requests.json"
            write_once(raw_dir / raw_name, raw)
            page.update({"rawFile": f"raw/{raw_name}", "rawSha256": digest(raw), "rawBytes": len(raw)})
        data, parse_error = parse_graph(raw) if raw is not None else (None, error)
        if parse_error:
            page["parseError"] = parse_error
            page_log.append(page)
            complete = False
            break
        batch = data.get("optimisticPriceRequests")
        if not isinstance(batch, list):
            page["parseError"] = "missing optimisticPriceRequests list"
            page_log.append(page)
            complete = False
            break
        if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in batch):
            page["parseError"] = "invalid request row"
            page_log.append(page)
            complete = False
            break
        if batch != sorted(batch, key=lambda item: item["id"]):
            page["parseError"] = "response IDs not ascending"
            page_log.append(page)
            complete = False
            break
        rows.extend(normalize(item, indexed_block) for item in batch)
        page["returned"] = len(batch)
        page_log.append(page)
        if len(batch) < PAGE_SIZE:
            break
        next_after = batch[-1]["id"]
        if next_after <= after:
            page["parseError"] = "non-advancing cursor"
            complete = False
            break
        after = next_after
    else:
        complete = False
        page_log.append({"page": MAX_PAGES, "stopReason": "maximum page cap reached"})
    events_bytes = json_bytes({"schema_version": SCHEMA_VERSION, "indexedBlock": indexed_block, "events": rows})
    write_once(output / "normalized-dispute-events.json", events_bytes)
    mapped = sum(event["lifecycle"]["mappingStatus"].startswith("allowlisted") for event in rows)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "completedAt": utc_now(),
        "indexedBlock": indexed_block,
        "probe": probe,
        "pages": page_log,
        "outputs": {"normalizedDisputeEvents": {"path": "normalized-dispute-events.json", "sha256": digest(events_bytes), "bytes": len(events_bytes)}},
        "counts": {"rawPages": sum("rawFile" in page for page in page_log) + 1, "disputeRequests": len(rows), "allowlistedAdapterRequester": mapped, "unmappedRequester": len(rows) - mapped, "requestsResolvedOrSettledAtIndexedBlock": sum(event["lifecycle"]["stateAtIndexedBlock"] in {"Resolved", "Settled", "Expired"} for event in rows)},
        "complete": complete,
        "coverage": plan["coverage"],
        "limitations": ["No Gamma/current-market snapshot was collected.", "questionId, conditionId, and marketId are intentionally null until an audited join.", "A dispute record proves an UMA OOv2 dispute request, not that it maps to a Polymarket market.", "Other OO versions and adapter deployments remain a known coverage gap."],
    }
    write_once(output / "manifest.json", json_bytes(manifest))
    print(json.dumps({"complete": complete, **manifest["counts"]}, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"collect_uma failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
