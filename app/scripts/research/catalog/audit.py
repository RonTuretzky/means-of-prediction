"""Verify completed Gamma captures, including explicitly recorded duplicate requests."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def audit_collection(directory: Path) -> dict:
    manifest_raw = (directory / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get('complete') is not True:
        raise ValueError('collection has not exhausted pagination')
    plan_raw = (directory / 'collection-plan.json').read_bytes()
    plan = json.loads(plan_raw)
    if manifest.get('planSha256') != sha(plan_raw):
        raise ValueError('collection plan hash mismatch')
    closed = plan.get('query', {}).get('closed')
    scope = None
    if closed is None:
        scope_raw = (directory / 'scope-correction.json').read_bytes()
        scope = {'sha256': sha(scope_raw), 'value': json.loads(scope_raw)}
        if scope['value'].get('scope') != 'open/default partition only':
            raise ValueError('default partition requires explicit scope correction')
        closed = False
    snapshot_name = 'collect_partition.py' if 'codeSha256' in plan else 'collect_all.py'
    code_hash = plan.get('codeSha256', plan.get('code', {}).get('sha256'))
    if sha((directory / snapshot_name).read_bytes()) != code_hash:
        raise ValueError('collector snapshot hash mismatch')
    log_raw = (directory / 'request-log.jsonl').read_bytes()
    cursor = None
    previous = None
    seen_files = set()
    seen_cursors = set()
    rows = duplicates = 0
    earliest = latest = None
    for line in log_raw.splitlines():
        entry = json.loads(line)
        if not entry.get('rawFile'):
            continue
        relative = entry['rawFile']
        if relative in seen_files or not relative.startswith('raw-pages/'):
            raise ValueError('duplicate or invalid logged raw file')
        if entry['page'] != len(seen_files) + 1:
            raise ValueError('page sequence gap')
        stored = (directory / relative).read_bytes()
        body = gzip.decompress(stored)
        if sha(stored) != entry['storedSha256'] or sha(body) != entry['rawSha256']:
            raise ValueError(f'raw response hash mismatch: {relative}')
        payload = json.loads(body)
        markets = payload['markets']
        if len(markets) != entry['returned'] or payload.get('next_cursor') != entry.get('nextCursor'):
            raise ValueError('response/log mismatch')
        ids = [str(m['id']) for m in markets]
        retry = previous is not None and (
            entry.get('cursorBefore') == previous['before']
            and entry.get('nextCursor') == previous['after']
            and ids == previous['ids']
        )
        if entry.get('cursorBefore') != cursor and not retry:
            raise ValueError('cursor chain has an unaccounted gap')
        if retry:
            duplicates += 1
        else:
            cursor = entry.get('nextCursor')
            if cursor and cursor in seen_cursors:
                raise ValueError('cursor cycle')
            if cursor:
                seen_cursors.add(cursor)
        for market in markets:
            if market.get('closed') is not closed:
                raise ValueError('market does not match captured partition')
            created = market.get('createdAt')
            if created:
                earliest = min(earliest, created) if earliest else created
                latest = max(latest, created) if latest else created
        previous = {'before': entry.get('cursorBefore'), 'after': entry.get('nextCursor'), 'ids': ids}
        seen_files.add(relative)
        rows += len(markets)
    actual_files = {'raw-pages/' + p.name for p in (directory / 'raw-pages').glob('*.json.gz')}
    if seen_files != actual_files or manifest.get('pages') != len(seen_files):
        raise ValueError('manifest, request log, and raw page inventory disagree')
    if not seen_files or cursor is not None:
        raise ValueError('cursor was not exhausted')
    return {
        'schemaVersion': 'gamma-capture-audit-v1', 'complete': True,
        'closed': closed, 'pages': len(seen_files), 'rawMarketOccurrences': rows,
        'duplicateRequests': duplicates,
        'originalManifestOccurrences': manifest.get('marketOccurrences'),
        'manifestOccurrenceCorrection': rows - manifest.get('marketOccurrences', rows),
        'earliestCreatedAt': earliest, 'latestCreatedAt': latest,
        'manifestSha256': sha(manifest_raw), 'planSha256': sha(plan_raw),
        'requestLogSha256': sha(log_raw), 'scopeCorrection': scope,
        'coverage': 'cursor exhaustion of this public API partition during collection; not a transactional snapshot or proof of deleted/private record coverage',
    }
