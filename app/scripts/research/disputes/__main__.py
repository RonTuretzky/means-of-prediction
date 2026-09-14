from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .pipeline import build_cohort, digest, ids_from, load_jsonl, write_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an offline, review-gated dispute cohort")
    parser.add_argument("--events", type=Path, action="append", default=[])
    parser.add_argument("--gamma", type=Path, action="append", default=[])
    parser.add_argument("--exclude-ids", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", default="disputed-cohort-v1")
    parser.add_argument("--curriculum-cap", type=float, default=0.20)
    args = parser.parse_args()
    if not args.events and not args.gamma:
        parser.error("at least one --events or --gamma input is required")
    if not 0 <= args.curriculum_cap <= 1:
        parser.error("--curriculum-cap must be between 0 and 1")
    os.umask(0o077)
    event_items, gamma_items, bindings = [], [], []
    for kind, paths, target in (("event", args.events, event_items), ("gamma", args.gamma, gamma_items)):
        for path in paths:
            rows, binding = load_jsonl(path, kind)
            target.extend(rows)
            bindings.append({"kind": kind, **binding})
    exclusions, exclusion_bindings = set(), []
    for path in args.exclude_ids:
        raw = path.read_bytes()
        values = ids_from(path)
        exclusions.update(values)
        exclusion_bindings.append(
            {"path": str(path), "sha256": digest(raw), "bytes": len(raw), "count": len(values)}
        )
    cohort = build_cohort(event_items, gamma_items, exclusions, seed=args.seed)
    manifest = write_cohort(
        args.output,
        cohort,
        seed=args.seed,
        input_bindings=bindings,
        exclusion_bindings=exclusion_bindings,
        curriculum_cap=args.curriculum_cap,
    )
    print(json.dumps(manifest["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
