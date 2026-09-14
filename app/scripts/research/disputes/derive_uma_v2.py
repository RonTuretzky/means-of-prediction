#!/usr/bin/env python3
"""Produce a write-once corrected derivative of a frozen UMA OOv2 export."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


SOURCE = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914"
OUTPUT = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914-derived-v2"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def write_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    if OUTPUT.exists():
        raise SystemExit(f"refusing to overwrite: {OUTPUT}")
    source_events = SOURCE / "normalized-dispute-events.json"
    source_manifest = SOURCE / "manifest.json"
    payload = json.loads(source_events.read_bytes())
    manifest = json.loads(source_manifest.read_bytes())
    indexed = payload.get("indexedBlock")
    events = payload.get("events")
    if not isinstance(indexed, dict) or not isinstance(events, list):
        raise SystemExit("source normalized export has an unexpected schema")

    os.umask(0o077)
    OUTPUT.mkdir(mode=0o700)
    os.chmod(OUTPUT, 0o700)
    code = Path(__file__).read_bytes()
    plan = {
        "schemaVersion": "uma-polygon-oov2-dispute-derivative-v2",
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": "Correct a historical normalization error without altering the frozen source capture.",
        "source": {
            "directory": str(SOURCE),
            "normalizedEvents": {"path": "normalized-dispute-events.json", "sha256": sha256(source_events.read_bytes())},
            "manifest": {"path": "manifest.json", "sha256": sha256(source_manifest.read_bytes())},
            "indexedBlock": indexed,
        },
        "code": {"path": str(Path(__file__)), "sha256": sha256(code)},
        "transformation": {
            "lifecycle.blockHash": "set to null because event-specific block hashes were not included in the source query",
            "lifecycle.indexedBlockHash": "copied from the frozen subgraph snapshot",
            "lifecycle.indexedBlockNumber": "copied from the frozen subgraph snapshot",
            "lifecycle.blockHashBasis": "records why blockHash is null",
        },
    }
    write_once(OUTPUT / "derivation-plan.json", dump(plan))
    write_once(OUTPUT / "derive_uma_v2.py", code)
    corrected = []
    for event in events:
        if not isinstance(event, dict):
            raise SystemExit("source event is not an object")
        event = dict(event)
        lifecycle = dict(event.get("lifecycle") or {})
        lifecycle["blockHash"] = None
        lifecycle["indexedBlockHash"] = indexed.get("hash")
        lifecycle["indexedBlockNumber"] = indexed.get("number")
        lifecycle["blockHashBasis"] = "null: source subgraph response did not expose a per-event block hash"
        event["lifecycle"] = lifecycle
        corrected.append(event)
    output = {"schema_version": "uma-polygon-oov2-dispute-derivative-v2", "sourceSchemaVersion": payload.get("schema_version"), "indexedBlock": indexed, "events": corrected}
    output_bytes = dump(output)
    write_once(OUTPUT / "normalized-dispute-events.json", output_bytes)
    result = {"complete": True, "sourceCaptureUnchanged": True, "eventCount": len(corrected), "output": {"path": "normalized-dispute-events.json", "sha256": sha256(output_bytes), "bytes": len(output_bytes)}, "sourceManifestComplete": manifest.get("complete")}
    write_once(OUTPUT / "manifest.json", dump(result))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
