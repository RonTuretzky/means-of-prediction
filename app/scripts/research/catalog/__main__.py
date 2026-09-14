from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import build_catalog, digest, discover_sources, ids_from
from .audit import audit_collection

BASE = Path.home() / ".local/share/means-of-prediction"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the all-available offline market catalog")
    parser.add_argument("--pages", type=Path, default=BASE / "polymarket-pages")
    parser.add_argument("--nyt", type=Path, default=BASE / "nyt")
    parser.add_argument("--repair", type=Path, default=BASE / "development-provenance-repair-20260913T222520Z/responses/markets")
    parser.add_argument("--api-pages", type=Path, action="append", default=[])
    parser.add_argument("--reserved", type=Path, default=BASE / "qwen-evaluation-reservation-20260912/provenance/excluded-market-ids.json")
    parser.add_argument("--article-sample", type=Path, default=BASE / "article-market-universe-20260913-v3/sampled-public-inputs.json")
    parser.add_argument("--output", type=Path, default=BASE / "historical-market-catalog-20260914")
    args = parser.parse_args()
    exclusions = []
    for kind, path in (("reserved", args.reserved), ("article_sample", args.article_sample)):
        raw = path.read_bytes()
        exclusions.append({"kind": kind, "path": str(path), "sha256": digest(raw), "bytes": len(raw), "count": len(ids_from(path))})
    base_manifest_path = args.pages / "manifest.json"
    base_manifest_raw = base_manifest_path.read_bytes()
    base_manifest = json.loads(base_manifest_raw)
    if base_manifest.get("publicPaginationComplete") is not True:
        raise SystemExit(f"base page collection is not complete: {base_manifest_path}")
    collection_bindings = [
        {
            "path": str(base_manifest_path),
            "sha256": digest(base_manifest_raw),
            "bytes": len(base_manifest_raw),
            "complete": True,
        }
    ]
    for directory in args.api_pages:
        audit = audit_collection(directory.parent)
        manifest_path = directory.parent / "manifest.json"
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        if manifest.get("complete") is not True:
            raise SystemExit(f"API page collection is not complete: {manifest_path}")
        page_count = len(list(directory.glob("*.json.gz")))
        if manifest.get("pages") != page_count:
            raise SystemExit(
                f"API page count disagrees with manifest: {page_count} != {manifest.get('pages')}"
            )
        collection_bindings.append(
            {
                "path": str(manifest_path), "sha256": digest(raw), "bytes": len(raw),
                "complete": True, "pages": page_count,
                "audit": audit,
            }
        )
    manifest = build_catalog(
        args.output,
        discover_sources(args.pages, args.nyt, args.repair, args.api_pages),
        reserved_ids=ids_from(args.reserved),
        article_sample_ids=ids_from(args.article_sample),
        exclusion_bindings=exclusions,
        collection_bindings=collection_bindings,
    )
    print(json.dumps(manifest["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
