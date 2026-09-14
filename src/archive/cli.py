from __future__ import annotations

import argparse
import json
from pathlib import Path

from archive.adapters import InternetArchiveAdapter, September11DigitalArchiveAdapter
from archive.registry import enabled_sources


def _add_output_args(parser: argparse.ArgumentParser, *, default_delay: float) -> None:
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=default_delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample_911da = subparsers.add_parser(
        "sample-911da",
        help="Sample metadata from the September 11 Digital Archive",
    )
    _add_output_args(sample_911da, default_delay=1.0)
    sample_911da.add_argument("--collection", type=int, default=None)

    sample_ia = subparsers.add_parser(
        "sample-internet-archive",
        help="Sample metadata from the Internet Archive Understanding 9/11 collection",
    )
    _add_output_args(sample_ia, default_delay=0.5)
    sample_ia.add_argument("--collection", default="911")

    sources = subparsers.add_parser("list-sources", help="List enabled Phase 0 sources")
    sources.add_argument("--registry", type=Path, default=Path("config/sources.phase0.yaml"))
    return parser


def _write_jsonl(output: Path, records: list, serializer) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(serializer(record), ensure_ascii=False))
            handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sample-911da":
        adapter = September11DigitalArchiveAdapter(request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit, collection_id=args.collection)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    if args.command == "sample-internet-archive":
        adapter = InternetArchiveAdapter(collection=args.collection, request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    if args.command == "list-sources":
        sources = enabled_sources(args.registry)
        for source in sources:
            print(f"{source.priority.upper():8} {source.id:40} {source.name}")
        print(f"{len(sources)} enabled sources")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
