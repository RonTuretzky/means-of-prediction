"""Stream all available local market versions into a private SQLite catalog."""
from __future__ import annotations

import hashlib
import gzip
import itertools
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = "historical-market-catalog-v1"
STATE_NAMES = {
    "outcomes", "outcome", "outcomePrices", "closed", "closedAt", "closedTime",
    "active", "acceptingOrders", "archived", "resolved", "automaticallyResolved",
    "umaResolutionStatus", "umaResolutionStatuses", "umaResolutionStatusHistory",
    "resolution", "winner", "payout", "payouts",
}


def is_state_field(name: str) -> bool:
    lowered = name.casefold()
    return name in STATE_NAMES or any(
        token in lowered
        for token in ("status", "outcome", "price", "payout", "winner", "resolv")
    )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def discover_sources(
    pages: Path, nyt: Path, repair: Path, api_pages: list[Path] | None = None
) -> list[tuple[Path, str]]:
    sources = [(path, "page") for path in pages.glob("*.json") if path.name != "manifest.json"]
    sources.extend(
        [
            (nyt / "topic-markets-partial.json", "array"),
            (nyt / "other-markets-partial.jsonl", "jsonl"),
            (nyt / "residual-markets-partial.jsonl", "jsonl"),
            (nyt / "review-additions/2026-09-10-candidate-markets.json", "array"),
        ]
    )
    sources.extend((path, "object") for path in repair.glob("*.json"))
    for directory in api_pages or []:
        sources.extend((path, "page-gzip") for path in directory.glob("*.json.gz"))
    missing = [str(path) for path, _ in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing catalog inputs: {missing}")
    return sorted(sources, key=lambda item: str(item[0]))


def iter_rows(path: Path, kind: str) -> Iterator[tuple[int, dict[str, Any], bytes]]:
    if kind == "jsonl":
        with path.open("rb") as handle:
            lines = enumerate(handle, 1)
            for line_number, line in lines:
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"{path}:{line_number} is not an object")
                yield line_number, row, line.rstrip(b"\r\n")
        return
    raw = gzip.decompress(path.read_bytes()) if kind == "page-gzip" else path.read_bytes()
    payload = json.loads(raw)
    if kind in {"page", "page-gzip"}:
        payload = payload.get("markets") if isinstance(payload, dict) else None
    elif kind == "object":
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"{path} does not contain the expected market array")
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError(f"{path} row {index} is not an object")
        canonical = json_text(row).encode()
        yield index, row, canonical


def parse_labels(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list) or len(value) < 2 or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        return None
    return json_text(value)


def event_group_ids(value: Any) -> str:
    if not isinstance(value, list):
        return "[]"
    identifiers = sorted(
        {
            str(event["id"])
            for event in value
            if isinstance(event, dict) and event.get("id") is not None
        }
    )
    return json_text(identifiers)


def ids_from(path: Path) -> set[str]:
    value = json.loads(path.read_bytes())
    if isinstance(value, dict) and isinstance(value.get("all"), list):
        value = value["all"]
    if not isinstance(value, list):
        raise ValueError(f"unsupported ID list: {path}")
    result = set()
    for item in value:
        if isinstance(item, dict):
            item = item.get("marketId", item.get("id"))
        if item is not None:
            result.add(str(item))
    return result


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE sources (
          source_id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
          sha256 TEXT NOT NULL, byte_length INTEGER NOT NULL, row_count INTEGER NOT NULL
        );
        CREATE TABLE versions (
          version_id INTEGER PRIMARY KEY, market_id TEXT NOT NULL,
          source_id INTEGER NOT NULL REFERENCES sources(source_id), source_row INTEGER NOT NULL,
          raw_sha256 TEXT NOT NULL, question_id TEXT, condition_id TEXT,
          event_group_ids_json TEXT NOT NULL,
          question TEXT, rules TEXT, labels_json TEXT,
          state_json TEXT NOT NULL, UNIQUE(source_id, source_row)
        );
        CREATE INDEX versions_market ON versions(market_id);
        CREATE INDEX versions_question_id ON versions(question_id);
        CREATE TABLE markets (
          market_id TEXT PRIMARY KEY, version_count INTEGER NOT NULL,
          distinct_raw_versions INTEGER NOT NULL, conflict_fields_json TEXT NOT NULL,
          source_conflict INTEGER NOT NULL, reserved_holdout INTEGER NOT NULL,
          article_sample_holdout INTEGER NOT NULL, training_holdout INTEGER NOT NULL,
          public_candidate_eligible INTEGER NOT NULL
        );
        CREATE TABLE rejections (
          source_id INTEGER NOT NULL, source_row INTEGER NOT NULL, raw_sha256 TEXT NOT NULL,
          reason TEXT NOT NULL, PRIMARY KEY(source_id, source_row)
        );
        """
    )


def build_catalog(
    output: Path,
    sources: list[tuple[Path, str]],
    *,
    reserved_ids: set[str],
    article_sample_ids: set[str],
    exclusion_bindings: list[dict[str, Any]],
    collection_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True)
    output.chmod(0o700)
    database = output / "catalog.sqlite3"
    connection = sqlite3.connect(database)
    _schema(connection)
    source_manifest = []
    version_count = rejected = 0
    for source_id, (path, kind) in enumerate(sources, 1):
        source_hash = file_digest(path)
        source_bytes = path.stat().st_size
        row_count = 0
        connection.execute(
            "INSERT INTO sources VALUES (?,?,?,?,?,?)",
            (source_id, str(path), kind, source_hash, source_bytes, 0),
        )
        for row_index, row, raw_row in iter_rows(path, kind):
            row_count += 1
            raw_hash = digest(raw_row)
            market_id = row.get("id", row.get("marketId"))
            if market_id is None or not str(market_id):
                rejected += 1
                connection.execute(
                    "INSERT INTO rejections VALUES (?,?,?,?)",
                    (source_id, row_index, raw_hash, "missing_market_id"),
                )
                continue
            question = row.get("question") if isinstance(row.get("question"), str) and row["question"].strip() else None
            question_id = row.get("questionID", row.get("questionId"))
            question_id = str(question_id).casefold() if question_id is not None else None
            condition_id = row.get("conditionId")
            condition_id = str(condition_id).casefold() if condition_id is not None else None
            rules_value = row.get("description", row.get("rules"))
            rules = rules_value if isinstance(rules_value, str) and rules_value.strip() else None
            labels = parse_labels(row.get("outcomes", row.get("outcomeLabels")))
            event_ids = event_group_ids(row.get("events"))
            state = {key: row[key] for key in sorted(row) if is_state_field(key)}
            connection.execute(
                "INSERT INTO versions(market_id,source_id,source_row,raw_sha256,question_id,condition_id,event_group_ids_json,question,rules,labels_json,state_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (str(market_id), source_id, row_index, raw_hash, question_id, condition_id, event_ids, question, rules, labels, json_text(state)),
            )
            version_count += 1
        connection.execute("UPDATE sources SET row_count=? WHERE source_id=?", (row_count, source_id))
        source_manifest.append(
            {"path": str(path), "kind": kind, "sha256": source_hash, "bytes": source_bytes, "rows": row_count}
        )
        if source_id % 500 == 0:
            connection.commit()

    connection.commit()

    public_path = output / "candidate-public.jsonl"
    public_descriptor = os.open(public_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    public_hasher = hashlib.sha256()
    public_byte_count = 0
    conflicts = holdouts = eligible = 0
    version_rows = connection.execute(
        "SELECT market_id,question,rules,labels_json,raw_sha256 FROM versions ORDER BY market_id"
    )
    unique_markets = 0
    with os.fdopen(public_descriptor, "wb") as public_handle:
        for market_id, grouped in itertools.groupby(version_rows, key=lambda row: row[0]):
            unique_markets += 1
            values = list(grouped)
            occurrences = len(values)
            raw_versions = len({value[4] for value in values})
            field_sets = [
                {value[index] for value in values if value[index] is not None}
                for index in range(1, 4)
            ]
            conflict_fields = [
                name
                for name, found in zip(("question", "rules", "outcomeLabels"), field_sets)
                if len(found) > 1
            ]
            conflict = bool(conflict_fields)
            reserved = market_id in reserved_ids
            article = market_id in article_sample_ids
            holdout = reserved or article
            candidate = not conflict and all(len(found) == 1 for found in field_sets)
            connection.execute(
                "INSERT INTO markets VALUES (?,?,?,?,?,?,?,?,?)",
                (market_id, occurrences, raw_versions, json_text(conflict_fields), conflict, reserved, article, holdout, candidate),
            )
            conflicts += conflict
            holdouts += holdout
            eligible += candidate
            if candidate:
                line = (
                    json_text(
                        {
                            "marketId": market_id,
                            "question": next(iter(field_sets[0])),
                            "rules": next(iter(field_sets[1])),
                            "outcomeLabels": json.loads(next(iter(field_sets[2]))),
                            "trainingHoldout": holdout,
                        }
                    ).encode()
                    + b"\n"
                )
                public_handle.write(line)
                public_hasher.update(line)
                public_byte_count += len(line)
    connection.commit()
    connection.close()
    database.chmod(0o600)
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "scope": "all available local public captures; not proven all Polymarket markets ever",
        "sources": source_manifest,
        "collectionManifests": collection_bindings or [],
        "exclusionInputs": exclusion_bindings,
        "artifacts": {
            "catalog": {"path": "catalog.sqlite3", "sha256": file_digest(database), "bytes": database.stat().st_size},
            "candidatePublic": {"path": "candidate-public.jsonl", "sha256": public_hasher.hexdigest(), "bytes": public_byte_count},
        },
        "counts": {
            "sourceFiles": len(sources), "sourceRows": version_count + rejected,
            "versions": version_count, "rejectedRows": rejected, "uniqueMarkets": unique_markets,
            "sourceConflicts": conflicts, "trainingHoldouts": holdouts,
            "publicCandidates": eligible,
        },
        "trainingAdmission": "evidence_pending; catalog membership and observed outcomes are not truth labels",
        "disputedCohort": "separate reference only; not joined or modified by this build",
    }
    manifest_bytes = json_bytes(manifest)
    manifest_path = output / "manifest.json"
    descriptor = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(manifest_bytes)
    return manifest
