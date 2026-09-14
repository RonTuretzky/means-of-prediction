from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .corpus import import_full_text_jsonl, import_nyt_metadata


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(
        description="Import local article evidence without network or inference access."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    nyt = subparsers.add_parser("import-nyt", help="import NYT API metadata only")
    nyt.add_argument("--input", type=Path, required=True)
    nyt.add_argument("--corpus", type=Path, required=True)
    nyt.add_argument("--api", choices=("archive", "article-search"), required=True)
    nyt.add_argument("--retrieved-at", required=True)

    full_text = subparsers.add_parser(
        "import-full-text", help="import declared user/publisher JSONL exports"
    )
    full_text.add_argument("--input", type=Path, required=True)
    full_text.add_argument("--corpus", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "import-nyt":
        manifest = import_nyt_metadata(
            args.input, args.corpus, api=args.api, retrieved_at=args.retrieved_at
        )
    else:
        manifest = import_full_text_jsonl(args.input, args.corpus)
    print(
        json.dumps(
            {
                "corpus": str(args.corpus),
                "records": manifest["record_count"],
                "sources": manifest["source_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
