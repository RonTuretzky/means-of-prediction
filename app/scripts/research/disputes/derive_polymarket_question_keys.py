#!/usr/bin/env python3
"""Attach audited Polymarket resolution-subgraph question keys to an OOv2 derivative.

This does not assert a Gamma market join.  The key is the resolution-subgraph's
MarketResolution entity ID (keccak256 of the raw ancillary data) for requests
made by the three adapters explicitly checked by the OOv2 handler.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914-derived-v2"
OUTPUT = Path.home() / ".local/share/means-of-prediction/disputed-markets-20260914-polymarket-question-keys-v1"
CONSTANTS_URL = "https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/src/utils/constants.ts"
HANDLER_URL = "https://raw.githubusercontent.com/Polymarket/resolution-subgraph/main/src/optimistic-oracle-v-2.ts"
ADAPTERS = {
    "0x6a9d222616c90fca5754cd1333cfd9b7fb6a4f74": "UmaCtfAdapterV2",
    "0x157ce2d672854c848c9b79c49a8cc6cc89176a49": "UmaCtfAdapterV3",
    "0x2f5e3684cb1f318ec51b00edba38d79ac2c0aa9d": "NegRiskUmaCtfAdapter",
}

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def dump(value: object) -> bytes: return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
def write_once(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())

def main() -> int:
    if OUTPUT.exists(): raise SystemExit(f"refusing to overwrite: {OUTPUT}")
    src = SOURCE / "normalized-dispute-events.json"
    src_manifest = SOURCE / "manifest.json"
    payload = json.loads(src.read_bytes())
    events = payload.get("events")
    if not isinstance(events, list): raise SystemExit("source schema missing events")
    os.umask(0o077); OUTPUT.mkdir(mode=0o700); os.chmod(OUTPUT, 0o700)
    code = Path(__file__).read_bytes()
    plan = {"schemaVersion":"polymarket-resolution-question-key-derivative-v1","createdAt":datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),"source":{"directory":str(SOURCE),"eventsSha256":sha(src.read_bytes()),"manifestSha256":sha(src_manifest.read_bytes())},"code":{"path":str(Path(__file__)),"sha256":sha(code)},"adapterAllowlist":ADAPTERS,"sourceCode":{"constants":CONSTANTS_URL,"handler":HANDLER_URL},"semantics":"For an allowlisted requester, copy lifecycle.ancillaryDataKeccak256 into questionId because Polymarket resolution-subgraph loads MarketResolution using crypto.keccak256(event.params.ancillaryData). This is a resolution entity key only; marketId and conditionId remain null until an independent market join."}
    write_once(OUTPUT / "derivation-plan.json", dump(plan)); write_once(OUTPUT / "derive_polymarket_question_keys.py", code)
    out=[]; mapped=0; keys=[]; by_adapter=Counter()
    for original in events:
        event=dict(original); lifecycle=dict(event.get("lifecycle") or {}); requester=(event.get("requester") or "").lower()
        adapter=ADAPTERS.get(requester)
        if adapter and isinstance(lifecycle.get("ancillaryDataKeccak256"), str):
            event["questionId"] = lifecycle["ancillaryDataKeccak256"]
            lifecycle["questionIdBasis"] = "Polymarket resolution-subgraph optimistic-oracle-v-2.ts uses crypto.keccak256(event.params.ancillaryData) as MarketResolution key after its three-adapter requester check"
            lifecycle["mappingStatus"] = "allowlisted_polymarket_resolution_question_key"
            event["sourceRefs"] = list(event.get("sourceRefs") or []) + [{"kind":"polymarket_resolution_subgraph_handler","url":HANDLER_URL,"adapter":adapter},{"kind":"polymarket_resolution_subgraph_constants","url":CONSTANTS_URL,"adapter":adapter}]
            mapped+=1; keys.append(event["questionId"]); by_adapter[adapter]+=1
        else:
            lifecycle["mappingStatus"] = "unmapped_requester_or_missing_ancillary_key"
        event["lifecycle"]=lifecycle; out.append(event)
    result={"schema_version":"polymarket-resolution-question-key-derivative-v1","sourceSchemaVersion":payload.get("schema_version"),"indexedBlock":payload.get("indexedBlock"),"events":out}
    raw=dump(result); write_once(OUTPUT / "normalized-dispute-events.json",raw)
    manifest={"complete":True,"sourceCaptureUnchanged":True,"eventCount":len(out),"allowlistedRequestCount":mapped,"uniqueResolutionQuestionKeys":len(set(keys)),"allowlistedRequestsByAdapter":dict(sorted(by_adapter.items())),"unmappedRequestCount":len(out)-mapped,"output":{"path":"normalized-dispute-events.json","sha256":sha(raw),"bytes":len(raw)},"limitations":["questionId is a Polymarket resolution-subgraph key, not a Gamma market id.","The source handler returns early if a MarketResolution entity is absent; this derivative does not query a hosted resolution subgraph, so it does not independently prove the entity existed at its indexed head.","conditionId and marketId remain null pending a separate audited join."]}
    write_once(OUTPUT / "manifest.json", dump(manifest)); print(json.dumps(manifest,sort_keys=True)); return 0
if __name__ == '__main__': raise SystemExit(main())
