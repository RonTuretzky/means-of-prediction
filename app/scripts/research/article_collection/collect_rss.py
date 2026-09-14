#!/usr/bin/env python3
"""Collect a write-once NYT RSS metadata registry without opening article URLs.

This program performs only the eight explicit RSS feed GETs in FEEDS.  It does
not follow redirects, retrieve item links, or parse article pages.  Raw feed
bytes remain in the private output directory; normalized records contain only
RSS metadata fields.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import xml.etree.ElementTree as element_tree
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPResponse
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


OUTPUT = Path.home() / ".local/share/means-of-prediction/nyt-article-registry-20260913"
BASE_URL = "https://rss.nytimes.com/services/xml/rss/nyt"
FEEDS = ("World", "US", "Politics", "Business", "Technology", "Science", "Sports", "HomePage")
MAX_BYTES = 2 * 1024 * 1024
PACE_SECONDS = 0.5
SCHEMA_VERSION = "nyt-rss-metadata-registry-v1"


class NoRedirect(HTTPRedirectHandler):
    """Turn any redirect into an error; a feed call must have no redirect."""

    def redirect_request(self, request: Request, fp: HTTPResponse, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise RuntimeError(f"redirect refused: HTTP {code} to {newurl}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, mode=0o700)
    os.chmod(path, 0o700)


def write_once(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value.strip()
    # Preserve query-string variants; only fragment is not an HTTP resource.
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def text_of(item: element_tree.Element, name: str) -> str | None:
    node = item.find(name)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value if value else None


def parse_pub_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_feed(raw: bytes, feed: str, source_url: str, source_sha256: str, retrieved_at: str) -> list[dict[str, Any]]:
    # ElementTree does not resolve external entities; reject declarations before
    # parsing so they are neither accepted nor silently ignored.
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("DOCTYPE/entity declaration refused")
    root = element_tree.fromstring(raw)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS channel missing")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(channel.findall("item")):
        link = text_of(item, "link")
        guid = text_of(item, "guid")
        original_urls = [value for value in (link, guid) if value]
        identity = canonical_url(link) or guid or f"{feed}:{index}"
        metadata = {
            "title": text_of(item, "title"),
            "link": link,
            "guid": guid,
            "pubDate": text_of(item, "pubDate"),
            "description": text_of(item, "description"),
        }
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "record_id": digest(json_bytes({"feed": feed, "index": index, "source_sha256": source_sha256})),
                "canonical_identity": identity,
                "canonical_url": canonical_url(link),
                "original_urls": original_urls,
                "source": {
                    "source_kind": "nyt_rss_metadata_only",
                    "feed": feed,
                    "feed_url": source_url,
                    "feed_item_index": index,
                    "raw_feed_sha256": source_sha256,
                },
                "retrieval": {"retrieved_at": retrieved_at},
                "metadata": metadata,
                "normalized_pub_date": parse_pub_date(metadata["pubDate"]),
                "evidence": {
                    "classification": "metadata_only",
                    "full_text": None,
                    "eligible_as_full_text": False,
                    "metadata_fields": ["title", "link", "guid", "pubDate", "description"],
                },
            }
        )
    return records


def fetch_once(url: str) -> tuple[int | None, bytes | None, str | None]:
    request = Request(url, headers={"User-Agent": "means-of-prediction-rss-metadata/1.0", "Accept": "application/rss+xml, application/xml, text/xml"})
    opener = build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            status = response.status
            if status != 200:
                return status, None, f"unexpected HTTP status {status}"
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_BYTES:
                return status, None, f"declared content length exceeds {MAX_BYTES} bytes"
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return status, None, f"response exceeds {MAX_BYTES} bytes"
            return status, raw, None
    except HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except (URLError, RuntimeError, socket.timeout, TimeoutError, ValueError) as exc:
        return None, None, str(exc)


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError(f"write-once output already exists: {OUTPUT}")
    private_directory(OUTPUT)
    raw_dir = OUTPUT / "raw"
    records_dir = OUTPUT / "records"
    private_directory(raw_dir)
    private_directory(records_dir)

    plan = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "purpose": "public NYT RSS metadata registry; not an article-text collection",
        "planned_calls": [f"{BASE_URL}/{name}.xml" for name in FEEDS],
        "call_count": len(FEEDS),
        "request_policy": {"attempts_per_feed": 1, "serial": True, "pace_seconds": PACE_SECONDS, "follow_redirects": False, "max_response_bytes": MAX_BYTES},
        "stop_statuses": [401, 403, 429],
        "article_link_policy": "never follow RSS item links or fetch www.nytimes.com",
        "preliminary_world_probe": {"status": "unarchived_excluded", "url": f"{BASE_URL}/World.xml", "reported_status": 200, "reported_bytes": 120403, "reported_items": 54},
    }
    write_once(OUTPUT / "collection-plan.json", json_bytes(plan))

    calls: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    stopped = False
    for position, feed in enumerate(FEEDS):
        url = f"{BASE_URL}/{feed}.xml"
        if stopped:
            calls.append({"feed": feed, "url": url, "attempted": False, "reason": "not attempted after stop status"})
            continue
        started_at = utc_now()
        status, raw, error = fetch_once(url)
        completed_at = utc_now()
        call: dict[str, Any] = {"feed": feed, "url": url, "attempted": True, "started_at": started_at, "completed_at": completed_at, "http_status": status, "error": error, "followed_article_links": 0}
        if raw is not None:
            raw_hash = digest(raw)
            raw_file = raw_dir / f"{position + 1:02d}-{feed}.xml"
            write_once(raw_file, raw)
            call.update({"raw_file": str(raw_file), "raw_byte_length": len(raw), "raw_sha256": raw_hash})
            try:
                records = parse_feed(raw, feed, url, raw_hash, completed_at)
            except (ValueError, element_tree.ParseError) as exc:
                call["parse_error"] = str(exc)
            else:
                call["item_count"] = len(records)
                for record in records:
                    record_path = records_dir / f"{record['record_id']}.json"
                    write_once(record_path, json_bytes(record))
                all_records.extend(records)
        calls.append(call)
        if status in {401, 403, 429}:
            stopped = True
        if position + 1 < len(FEEDS) and not stopped:
            time.sleep(PACE_SECONDS)

    identities: dict[str, list[str]] = {}
    for record in all_records:
        identities.setdefault(record["canonical_identity"], []).append(record["record_id"])
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "completed_at": utc_now(),
        "plan_file": "collection-plan.json",
        "calls": calls,
        "planned_feed_count": len(FEEDS),
        "attempted_feed_count": sum(1 for call in calls if call["attempted"]),
        "successful_feed_count": sum(1 for call in calls if call.get("http_status") == 200 and not call.get("error") and "item_count" in call and "parse_error" not in call),
        "metadata_item_count": len(all_records),
        "unique_canonical_identity_count": len(identities),
        "duplicate_canonical_identity_count": sum(1 for values in identities.values() if len(values) > 1),
        "full_text_count": 0,
        "article_links_followed": 0,
        "dedupe_policy": "Canonical identities are counted for audit only; every feed item/version remains as its own record with original URLs and source feed.",
    }
    write_once(OUTPUT / "manifest.json", json_bytes(manifest))
    print(json.dumps({key: manifest[key] for key in ("attempted_feed_count", "successful_feed_count", "metadata_item_count", "unique_canonical_identity_count", "full_text_count", "article_links_followed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"collect_rss failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
