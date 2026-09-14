#!/usr/bin/env python3
"""Write-once metadata audit for the frozen UMA Polygon OOv2 capture."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

ENDPOINT = "https://api.studio.thegraph.com/query/1057/polygon-optimistic-oracle-v2/1.2.0"
SOURCE = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914"
OUTPUT = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914-meta-audit-v1"
QUERY = "query { _meta { block { number hash } deployment hasIndexingErrors } }"

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def dumped(value: object) -> bytes: return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
def write_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())

def main() -> int:
    if OUTPUT.exists(): raise SystemExit(f"refusing to overwrite: {OUTPUT}")
    source_plan = SOURCE / "collection-plan.json"
    source_probe = SOURCE / "probe.json"
    original_probe = json.loads(source_probe.read_bytes())
    os.umask(0o077); OUTPUT.mkdir(mode=0o700); os.chmod(OUTPUT, 0o700)
    code = Path(__file__).read_bytes()
    plan = {"schemaVersion":"uma-polygon-oov2-meta-audit-v1", "createdAt":datetime.now(timezone.utc).isoformat().replace('+00:00','Z'), "endpoint":ENDPOINT, "requestPolicy":{"attempts":1,"retries":0,"purpose":"record current subgraph deployment/indexing metadata; no collection page rerun"}, "query":QUERY, "sourceCapture":{"collectionPlanSha256":sha(source_plan.read_bytes()),"probeSha256":sha(source_probe.read_bytes()),"frozenIndexedBlock":original_probe.get("indexedBlock")}, "code":{"path":str(Path(__file__)),"sha256":sha(code)}}
    write_once(OUTPUT / "audit-plan.json", dumped(plan)); write_once(OUTPUT / "audit_uma_meta.py", code)
    payload = json.dumps({"query":QUERY}, separators=(',', ':')).encode()
    req = Request(ENDPOINT, data=payload, method='POST', headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'means-of-prediction-uma-meta-audit/1.0'})
    status = None; raw = None; error = None
    try:
        with build_opener().open(req, timeout=45) as response: status, raw = response.status, response.read()
    except HTTPError as exc: status, raw, error = exc.code, exc.read(), f"HTTP {exc.code}"
    except (URLError, TimeoutError, ValueError) as exc: error = str(exc)
    if raw is not None: write_once(OUTPUT / "raw-meta.json", raw)
    result = {"completedAt":datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),"httpStatus":status,"error":error,"raw":{"path":"raw-meta.json","sha256":sha(raw),"bytes":len(raw)} if raw is not None else None}
    if raw is not None:
        try: result['response'] = json.loads(raw)
        except (ValueError, UnicodeDecodeError): result['parseError'] = 'invalid JSON'
    write_once(OUTPUT / "manifest.json", dumped(result)); print(json.dumps(result, sort_keys=True)); return 0 if status == 200 else 1
if __name__ == '__main__': raise SystemExit(main())
