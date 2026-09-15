from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from archive.adapters import InternetArchiveAdapter, NistWtcRepositoryAdapter, September11DigitalArchiveAdapter
from archive.corpus import load_jsonl
from archive.dedupe import find_candidates
from archive.derived import derive_temporal_claims, serialize_temporal_claim
from archive.profiling import profile_records
from archive.quality import prioritize_records
from archive.registry import enabled_sources
from archive.work_queue import build_work_queue


def _add_output_args(parser: argparse.ArgumentParser, *, default_delay: float) -> None:
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=default_delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-ingest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample_911da = subparsers.add_parser("sample-911da", help="Sample metadata from the September 11 Digital Archive")
    _add_output_args(sample_911da, default_delay=1.0)
    sample_911da.add_argument("--collection", type=int, default=None)
    sample_911da.add_argument("--details", action="store_true", help="Enrich each record with Dublin Core XML metadata")

    sample_ia = subparsers.add_parser("sample-internet-archive", help="Sample Internet Archive Understanding 9/11 metadata")
    _add_output_args(sample_ia, default_delay=0.5)
    sample_ia.add_argument("--collection", default="911")
    sample_ia.add_argument("--details", action="store_true", help="Fetch full item metadata and summarize files")

    sample_nist = subparsers.add_parser("sample-nist", help="Inventory public NIST WTC repository entry points")
    sample_nist.add_argument("--output", type=Path, required=True)
    sample_nist.add_argument("--delay", type=float, default=0.5)

    sources = subparsers.add_parser("list-sources", help="List enabled Phase 0 sources")
    sources.add_argument("--registry", type=Path, default=Path("config/sources.phase0.yaml"))

    profile = subparsers.add_parser("profile-jsonl", help="Profile metadata coverage in one or more JSONL corpora")
    profile.add_argument("inputs", nargs="+", type=Path)
    profile.add_argument("--output", type=Path, default=None)

    dedupe = subparsers.add_parser("dedupe-jsonl", help="Propose likely duplicate records without merging them")
    dedupe.add_argument("inputs", nargs="+", type=Path)
    dedupe.add_argument("--threshold", type=float, default=0.86)
    dedupe.add_argument("--output", type=Path, required=True)

    prioritize = subparsers.add_parser("prioritize-jsonl", help="Rank records for metadata enrichment work")
    prioritize.add_argument("inputs", nargs="+", type=Path)
    prioritize.add_argument("--output", type=Path, required=True)

    claims = subparsers.add_parser("derive-temporal-claims", help="Create deterministic evidence-backed temporal claims")
    claims.add_argument("inputs", nargs="+", type=Path)
    claims.add_argument("--output", type=Path, required=True)

    work_queue = subparsers.add_parser("build-work-queue", help="Create evidence-focused AI enrichment tasks")
    work_queue.add_argument("inputs", nargs="+", type=Path)
    work_queue.add_argument("--output", type=Path, required=True)
    return parser


def _write_jsonl(output: Path, records: list, serializer) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(serializer(record), ensure_ascii=False))
            handle.write("\n")


def _load_many(paths: list[Path]):
    records = []
    for path in paths:
        records.extend(load_jsonl(path))
    return records


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "sample-911da":
        adapter = September11DigitalArchiveAdapter(request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit, collection_id=args.collection, enrich=args.details)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    if args.command == "sample-internet-archive":
        adapter = InternetArchiveAdapter(collection=args.collection, request_delay_s=args.delay)
        records = adapter.sample(limit=args.limit, enrich=args.details)
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} metadata records to {args.output}")
        return 0

    if args.command == "sample-nist":
        adapter = NistWtcRepositoryAdapter(request_delay_s=args.delay)
        records = adapter.sample()
        _write_jsonl(args.output, records, adapter.serialize_source_item)
        print(f"wrote {len(records)} NIST repository records to {args.output}")
        return 0

    if args.command == "list-sources":
        sources = enabled_sources(args.registry)
        for source in sources:
            print(f"{source.priority.upper():8} {source.id:40} {source.name}")
        print(f"{len(sources)} enabled sources")
        return 0

    if args.command == "profile-jsonl":
        records = _load_many(args.inputs)
        payload = profile_records(records).to_dict()
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"wrote profile for {len(records)} records to {args.output}")
        else:
            print(rendered)
        return 0

    if args.command == "dedupe-jsonl":
        records = _load_many(args.inputs)
        candidates = find_candidates(records, threshold=args.threshold)
        _write_jsonl(args.output, candidates, asdict)
        print(f"wrote {len(candidates)} duplicate candidates to {args.output}")
        return 0

    if args.command == "prioritize-jsonl":
        records = _load_many(args.inputs)
        priorities = prioritize_records(records)
        _write_jsonl(args.output, priorities, asdict)
        print(f"wrote {len(priorities)} enrichment priorities to {args.output}")
        return 0

    if args.command == "derive-temporal-claims":
        records = _load_many(args.inputs)
        temporal_claims = derive_temporal_claims(records)
        _write_jsonl(args.output, temporal_claims, serialize_temporal_claim)
        print(f"wrote {len(temporal_claims)} deterministic temporal claims to {args.output}")
        return 0

    if args.command == "build-work-queue":
        records = _load_many(args.inputs)
        tasks = build_work_queue(records)
        _write_jsonl(args.output, tasks, asdict)
        print(f"wrote {len(tasks)} enrichment tasks to {args.output}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
