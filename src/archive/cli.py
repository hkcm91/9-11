from __future__ import annotations

import argparse
import json
from pathlib import Path

from archive.adapters import September11DigitalArchiveAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser(
        "sample-911da",
        help="Sample metadata from the September 11 Digital Archive",
    )
    sample.add_argument("--limit", type=int, default=50)
    sample.add_argument("--collection", type=int, default=None)
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--delay", type=float, default=1.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sample-911da":
        adapter = September11DigitalArchiveAdapter(request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit, collection_id=args.collection)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(adapter.serialize_source_item(record), ensure_ascii=False))
                handle.write("\n")
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
