#!/usr/bin/env python3
"""Build a deterministic offline RSS-metadata retrieval queue for markets.

This is candidate retrieval only. It reads no network data, never opens article
URLs, and uses only a market question plus RSS title/description metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "nyt-rss-market-retrieval-v1"
DEFAULT_REGISTRY = Path.home() / ".local/share/means-of-prediction/nyt-article-registry-20260913"
DEFAULT_MARKETS = Path.home() / ".local/share/means-of-prediction/article-market-universe-20260913-v3/sampled-public-inputs.json"
DEFAULT_OUTPUT = Path.home() / ".local/share/means-of-prediction/nyt-rss-market-retrieval-20260914"
WINDOW_START = "2026-08-29T13:38:08.478Z"
WINDOW_END = "2026-09-12T13:38:08.478Z"
STOPWORDS = frozenset("a an and are as at be been by for from has have if in into is it its of on or that the their this to was were will with would yes no will be market markets does did do after before during than then when where which who why how what whether according based price prices up down".split())
TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def normalized_words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return [token for token in TOKEN.findall(normalized) if token not in STOPWORDS]


def input_binding(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def write_once(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def private_dir(path: Path) -> None:
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)


def load_registry(registry: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = registry / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("full_text_count") != 0 or manifest.get("article_links_followed") != 0:
        raise ValueError("registry is not declared metadata-only")
    paths = sorted((registry / "records").glob("*.json"))
    if len(paths) != manifest.get("metadata_item_count"):
        raise ValueError("registry record count disagrees with manifest")
    bindings = [input_binding(manifest_path)] + [input_binding(path) for path in paths]
    records: list[dict[str, Any]] = []
    for path in paths:
        record = json.loads(path.read_bytes())
        evidence = record.get("evidence")
        metadata = record.get("metadata")
        if not isinstance(evidence, dict) or evidence.get("classification") != "metadata_only" or evidence.get("full_text") is not None or evidence.get("eligible_as_full_text") is not False:
            raise ValueError(f"record is not metadata-only: {path}")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("title"), (str, type(None))) or not isinstance(metadata.get("description"), (str, type(None))):
            raise ValueError(f"RSS metadata malformed: {path}")
        if path.stem != record.get("record_id"):
            raise ValueError(f"record ID does not match filename: {path}")
        records.append(record)
    return records, bindings


def dedupe_identities(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        identity = record.get("canonical_identity")
        if not isinstance(identity, str) or not identity:
            raise ValueError("RSS record lacks canonical_identity")
        groups.setdefault(identity, []).append(record)
    documents: list[dict[str, Any]] = []
    for identity in sorted(groups):
        occurrences = sorted(groups[identity], key=lambda record: record["record_id"])
        representative = occurrences[0]
        metadata = representative["metadata"]
        title = metadata.get("title") or ""
        description = metadata.get("description") or ""
        if not isinstance(title, str) or not isinstance(description, str):
            raise ValueError(f"RSS title/description invalid for {identity}")
        documents.append(
            {
                "canonical_identity": identity,
                "canonical_url": representative.get("canonical_url"),
                "occurrence_ids": [record["record_id"] for record in occurrences],
                "title": title,
                "description": description,
                "normalized_pub_date": representative.get("normalized_pub_date"),
                "tokens": normalized_words(title + " " + description),
            }
        )
    return documents


def document_weights(documents: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document["tokens"]))
    count = len(documents)
    idf = {term: math.log((count + 1) / (frequency + 1)) + 1.0 for term, frequency in document_frequency.items()}
    weighted: list[dict[str, Any]] = []
    for document in documents:
        frequency = Counter(document["tokens"])
        weights = {term: value * idf[term] for term, value in frequency.items()}
        norm = math.sqrt(sum(value * value for value in weights.values()))
        weighted.append({**document, "term_frequency": frequency, "weights": weights, "norm": norm})
    return idf, weighted


def retrieve(question: str, idf: dict[str, float], documents: list[dict[str, Any]], top_k: int = 3, min_shared: int = 2) -> list[dict[str, Any]]:
    query_frequency = Counter(normalized_words(question))
    query_weights = {term: value * idf[term] for term, value in query_frequency.items() if term in idf}
    query_norm = math.sqrt(sum(value * value for value in query_weights.values()))
    if not query_weights or query_norm == 0:
        return []
    candidates: list[dict[str, Any]] = []
    for document in documents:
        shared = sorted(set(query_weights).intersection(document["weights"]))
        if len(shared) < min_shared or document["norm"] == 0:
            continue
        numerator = sum(query_weights[term] * document["weights"][term] for term in shared)
        score = numerator / (query_norm * document["norm"])
        candidates.append(
            {
                "canonical_identity": document["canonical_identity"],
                "canonical_url": document["canonical_url"],
                "occurrence_ids": document["occurrence_ids"],
                "title": document["title"],
                "description": document["description"],
                "normalized_pub_date": document["normalized_pub_date"],
                "shared_nonstopwords": shared,
                "score": round(score, 12),
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["canonical_identity"]))[:top_k]


def load_markets(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("market sample must be a JSON array")
    markets: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise ValueError(f"market row {index} is not an object")
        market_id, question = row.get("marketId"), row.get("question")
        if not isinstance(market_id, str) or not market_id or not isinstance(question, str) or not question.strip():
            raise ValueError(f"market row {index} lacks marketId/question")
        if market_id in seen:
            raise ValueError(f"duplicate marketId: {market_id}")
        seen.add(market_id)
        markets.append({"market_id": market_id, "question": question})
    return markets, {"path": str(path), "sha256": digest(raw), "bytes": len(raw), "market_count": len(markets)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline deterministic NYT RSS metadata candidate retrieval")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--markets", type=Path, default=DEFAULT_MARKETS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    registry, markets_path, output = args.registry.expanduser(), args.markets.expanduser(), args.output_dir.expanduser()
    if output.exists():
        raise SystemExit(f"refusing to overwrite output: {output}")
    if not registry.is_dir() or not markets_path.is_file():
        raise SystemExit("registry or market sample path is unavailable")
    os.umask(0o077)
    private_dir(output)

    collector = Path(__file__)
    records, registry_bindings = load_registry(registry)
    markets, market_binding = load_markets(markets_path)
    options = {"algorithm": "normalized-word tf-idf cosine", "document_fields": ["title", "description"], "query_field": "question", "top_k": 3, "minimum_shared_nonstopwords": 2, "stopword_set": sorted(STOPWORDS), "publication_window_utc": {"start": WINDOW_START, "end": WINDOW_END}, "network_access": False, "inference": False, "article_urls_fetched": 0}
    plan = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "purpose": "candidate retrieval only; no labels, outcomes, article bodies, or article URL retrieval",
        "code": input_binding(collector),
        "registry": {"path": str(registry), "record_count": len(records), "input_bindings": registry_bindings},
        "markets": market_binding,
        "options": options,
    }
    write_once(output / "collection-plan.json", json_bytes(plan))
    snapshot = output / "match_metadata.py"
    shutil.copyfile(collector, snapshot)
    os.chmod(snapshot, 0o600)
    if digest(snapshot.read_bytes()) != plan["code"]["sha256"]:
        raise RuntimeError("code snapshot does not match frozen plan")

    documents = dedupe_identities(records)
    idf, weighted_documents = document_weights(documents)
    rows = [{"market_id": market["market_id"], "question": market["question"], "candidates": retrieve(market["question"], idf, weighted_documents)} for market in markets]
    candidates_bytes = json_bytes({"schema_version": SCHEMA_VERSION, "markets": rows})
    write_once(output / "retrieval-candidates.json", candidates_bytes)
    matched = sum(bool(row["candidates"]) for row in rows)
    window_start, window_end = parse_utc(WINDOW_START), parse_utc(WINDOW_END)
    assert window_start is not None and window_end is not None
    def temporal_count(items: list[dict[str, Any]]) -> dict[str, int]:
        values = [parse_utc(item.get("normalized_pub_date")) for item in items]
        return {
            "within_window": sum(value is not None and window_start <= value <= window_end for value in values),
            "post_window_discovery": sum(value is not None and value > window_end for value in values),
            "pre_window": sum(value is not None and value < window_start for value in values),
            "unknown_publication_time": sum(value is None for value in values),
        }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "completed_at": utc_now(),
        "plan": input_binding(output / "collection-plan.json"),
        "code_snapshot": input_binding(snapshot),
        "outputs": {"retrieval_candidates": {"path": "retrieval-candidates.json", "sha256": digest(candidates_bytes), "bytes": len(candidates_bytes)}},
        "counts": {"market_count": len(rows), "market_count_with_candidates": matched, "market_count_without_candidates": len(rows) - matched, "rss_occurrence_count": len(records), "rss_canonical_identity_count": len(documents), "rss_occurrence_publication_timing": temporal_count(records), "rss_canonical_identity_publication_timing": temporal_count(documents), "candidate_count": sum(len(row["candidates"]) for row in rows), "full_text_count": 0, "article_urls_fetched": 0},
        "notes": "Candidates are deterministic metadata-retrieval results, not relevance labels, outcomes, or article text. Post-window publication records are retained and explicitly reported as post-window discovery, not excluded.",
    }
    write_once(output / "manifest.json", json_bytes(manifest))
    print(json.dumps(manifest["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"match_metadata failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
