#!/usr/bin/env python3
"""Single-writer, resumable Gamma keyset partition collector."""
from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

ENDPOINT = "https://gamma-api.polymarket.com/markets/keyset"
LIMIT = 100
PACE = 0.1
ATTEMPTS = 3


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def write_once(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def atomic(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(encoded(value))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(0o600)
    os.replace(temporary, path)


def page_url(cursor: str | None, closed: bool) -> str:
    query = {"limit": LIMIT, "closed": str(closed).lower()}
    if cursor:
        query["after_cursor"] = cursor
    return ENDPOINT + "?" + urlencode(query)


def retry_after(value: str | None, current: datetime | None = None) -> float:
    if not value:
        return 1.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0.0, (target - (current or datetime.now(timezone.utc))).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 1.0


def writer_lock(output: Path):
    handle = (output / ".writer.lock").open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise
    return handle


def append_log(path: Path, entry: dict) -> None:
    with path.open("ab", buffering=0) as handle:
        handle.write((json.dumps(entry, sort_keys=True) + "\n").encode())


def verify_resume(output: Path, closed: bool) -> tuple[int, int, str | None]:
    plan_raw = (output / "collection-plan.json").read_bytes()
    plan = json.loads(plan_raw)
    snapshot = (output / "collect_partition.py").read_bytes()
    current = Path(__file__).read_bytes()
    if plan.get("query", {}).get("closed") is not closed:
        raise RuntimeError("--closed does not match frozen plan")
    if plan.get("codeSha256") != sha(snapshot) or sha(current) != sha(snapshot):
        raise RuntimeError("collector code does not match frozen compatible snapshot")
    expected_cursor = None
    seen_cursors = set()
    pages = rows = 0
    log_path = output / "request-log.jsonl"
    for line_number, line in enumerate(log_path.read_bytes().splitlines(), 1):
        entry = json.loads(line)
        if entry.get("errorBodyFile"):
            receipt_path = output / entry["errorBodyFile"]
            stored = receipt_path.read_bytes()
            if sha(stored) != entry["storedSha256"]:
                raise RuntimeError(f"error receipt hash mismatch: {receipt_path}")
            if sha(gzip.decompress(stored)) != entry["rawSha256"]:
                raise RuntimeError(f"decoded error receipt hash mismatch: {receipt_path}")
        if entry.get("kind") != "page":
            continue
        if entry.get("page") != pages + 1 or entry.get("cursorBefore") != expected_cursor:
            raise RuntimeError(f"request log cursor chain invalid at line {line_number}")
        stored_path = output / entry["rawFile"]
        stored = stored_path.read_bytes()
        if sha(stored) != entry["storedSha256"]:
            raise RuntimeError(f"stored page hash mismatch: {stored_path}")
        body = gzip.decompress(stored)
        if sha(body) != entry["rawSha256"]:
            raise RuntimeError(f"decoded page hash mismatch: {stored_path}")
        data = json.loads(body)
        markets = data.get("markets")
        if not isinstance(markets, list) or len(markets) != entry["returned"]:
            raise RuntimeError(f"stored page contents mismatch: {stored_path}")
        if data.get("next_cursor") != entry.get("nextCursor"):
            raise RuntimeError(f"stored cursor mismatch: {stored_path}")
        pages += 1
        rows += len(markets)
        expected_cursor = entry.get("nextCursor")
        if expected_cursor and expected_cursor in seen_cursors:
            raise RuntimeError("stored request log contains a cursor cycle")
        if expected_cursor:
            seen_cursors.add(expected_cursor)
    raw_files = sorted((output / "raw-pages").glob("*.json.gz"))
    if len(raw_files) != pages:
        raise RuntimeError("raw page count does not match successful request log")
    return pages, rows, expected_cursor


def initialize(output: Path, closed: bool) -> None:
    os.umask(0o077)
    output.mkdir(mode=0o700)
    (output / "raw-pages").mkdir(mode=0o700)
    (output / "failure-receipts").mkdir(mode=0o700)
    code = Path(__file__).read_bytes()
    write_once(output / "collect_partition.py", code)
    plan = {
        "schemaVersion": "gamma-keyset-partition-v2",
        "createdAt": now(),
        "endpoint": ENDPOINT,
        "query": {"limit": LIMIT, "closed": closed, "after_cursor": "opaque response cursor"},
        "requestPolicy": {
            "attemptsPerPage": ATTEMPTS,
            "retry429": "honor numeric seconds or HTTP-date Retry-After without truncation",
            "stopStatuses": [401, 403],
            "noPageCap": True,
        },
        "codeSha256": sha(code),
    }
    write_once(output / "collection-plan.json", encoded(plan))
    write_once(output / "request-log.jsonl", b"")
    atomic(output / "checkpoint.json", {"complete": False, "closed": closed, "pages": 0, "marketOccurrences": 0, "nextCursor": None})


def archive_error(output: Path, page: int, attempt: int, response) -> dict:
    body = response.content or b""
    stored = gzip.compress(body, compresslevel=1, mtime=0)
    existing = list((output / "failure-receipts").glob(f"page-{page:06d}-attempt-*.http.gz"))
    relative = f"failure-receipts/page-{page:06d}-attempt-{len(existing) + 1:04d}.http.gz"
    write_once(output / relative, stored)
    return {
        "errorBodyFile": relative,
        "rawSha256": sha(body),
        "rawBytes": len(body),
        "storedSha256": sha(stored),
        "storedBytes": len(stored),
    }


def collect(output: Path, closed: bool, *, resume: bool, session, sleep=time.sleep) -> int:
    if resume:
        if not output.is_dir() or (output / "manifest.json").exists():
            raise RuntimeError("no incomplete output to resume")
    else:
        if output.exists():
            raise FileExistsError(f"refusing to overwrite: {output}")
        initialize(output, closed)
    lock = writer_lock(output)
    try:
        pages, rows, cursor = verify_resume(output, closed)
        seen = set()
        reason = "unknown"
        while True:
            if shutil.disk_usage(output).free < 2 * 1024**3:
                reason = "disk_free_guard"
                break
            if cursor and cursor in seen:
                reason = "cursor_cycle"
                break
            if cursor:
                seen.add(cursor)
            target = page_url(cursor, closed)
            response = None
            for attempt in range(1, ATTEMPTS + 1):
                response = None
                error = None
                try:
                    response = session.get(
                        target,
                        headers={"Accept": "application/json", "User-Agent": "means-of-prediction-research/2.0"},
                        timeout=60,
                    )
                except requests.RequestException as exc:
                    error = str(exc)
                receipt = {
                    "kind": "attempt", "page": pages + 1, "attempt": attempt,
                    "closed": closed, "url": target, "cursorBefore": cursor,
                    "completedAt": now(), "httpStatus": response.status_code if response is not None else None,
                    "transportError": error,
                }
                if response is not None and response.status_code != 200:
                    receipt.update(archive_error(output, pages + 1, attempt, response))
                append_log(output / "request-log.jsonl", receipt)
                if response is not None and response.status_code == 429 and attempt < ATTEMPTS:
                    sleep(retry_after(response.headers.get("Retry-After")))
                    continue
                if response is None and attempt < ATTEMPTS:
                    sleep(float(attempt))
                    continue
                break
            if response is None or response.status_code != 200:
                reason = "transport_or_http_error"
                break
            body = response.content
            try:
                data = response.json()
                markets = data.get("markets")
                if not isinstance(markets, list):
                    raise ValueError("markets is not an array")
            except (ValueError, json.JSONDecodeError) as exc:
                parse_receipt = {
                    "kind": "parse-error",
                    "page": pages + 1,
                    "error": str(exc),
                    **archive_error(output, pages + 1, 0, response),
                }
                append_log(output / "request-log.jsonl", parse_receipt)
                reason = "parse_error"
                break
            stored = gzip.compress(body, compresslevel=1, mtime=0)
            relative = f"raw-pages/{pages + 1:06d}-markets.json.gz"
            write_once(output / relative, stored)
            next_cursor = data.get("next_cursor")
            page_entry = {
                "kind": "page", "page": pages + 1, "closed": closed, "url": target,
                "cursorBefore": cursor, "returned": len(markets), "nextCursor": next_cursor,
                "rawFile": relative, "rawSha256": sha(body), "rawBytes": len(body),
                "storedSha256": sha(stored), "storedBytes": len(stored),
            }
            append_log(output / "request-log.jsonl", page_entry)
            pages += 1
            rows += len(markets)
            cursor = next_cursor
            atomic(output / "checkpoint.json", {"complete": False, "closed": closed, "pages": pages, "marketOccurrences": rows, "nextCursor": cursor})
            if pages % 100 == 0:
                print(json.dumps({"closed": closed, "pages": pages, "marketOccurrences": rows}, sort_keys=True), flush=True)
            if not cursor:
                reason = "next_cursor_omitted"
                break
            sleep(PACE)
        complete = reason == "next_cursor_omitted"
        checkpoint = {"complete": complete, "closed": closed, "pages": pages, "marketOccurrences": rows, "nextCursor": None if complete else cursor, "reason": reason}
        atomic(output / "checkpoint.json", checkpoint)
        if complete:
            write_once(output / "manifest.json", encoded({**checkpoint, "planSha256": sha((output / "collection-plan.json").read_bytes()), "rawPagesDirectory": "raw-pages"}))
        else:
            failures = sorted((output / "failure-receipts").glob("run-*.json"))
            write_once(output / "failure-receipts" / f"run-{len(failures) + 1:04d}.json", encoded(checkpoint))
        return 0 if complete else 1
    finally:
        lock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--closed", required=True, choices=["true", "false"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    return collect(args.output.expanduser(), args.closed == "true", resume=args.resume, session=requests.Session())


if __name__ == "__main__":
    raise SystemExit(main())
