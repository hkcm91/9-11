from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from archive.query import ArchiveQuery


def _parse_csv_set(value: str | None) -> set[str] | None:
    if not value:
        return None
    values = {part.strip() for part in value.split(",") if part.strip()}
    return values or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-query")
    parser.add_argument("--database", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    item = subparsers.add_parser("item", help="Show one record with all claims and observation history")
    item.add_argument("record_id")

    timeline = subparsers.add_parser("timeline", help="Query claims intersecting a time window")
    timeline.add_argument("--start", required=True, help="ISO-8601 start timestamp")
    timeline.add_argument("--end", required=True, help="ISO-8601 end timestamp")
    timeline.add_argument("--kinds", default=None, help="Comma-separated time kinds, e.g. capture_time,recording_time")
    timeline.add_argument("--statuses", default=None, help="Comma-separated review statuses")
    timeline.add_argument("--min-confidence", type=float, default=0.0)
    timeline.add_argument("--limit", type=int, default=500)

    nearby = subparsers.add_parser("nearby", help="Query spatial claims near a map point")
    nearby.add_argument("--latitude", type=float, required=True)
    nearby.add_argument("--longitude", type=float, required=True)
    nearby.add_argument("--radius-m", type=float, required=True)
    nearby.add_argument("--kinds", default="capture_location", help="Comma-separated location kinds")
    nearby.add_argument("--statuses", default=None, help="Comma-separated review statuses")
    nearby.add_argument("--min-confidence", type=float, default=0.0)
    nearby.add_argument("--limit", type=int, default=200)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with ArchiveQuery(args.database) as query:
        if args.command == "item":
            payload = query.item_bundle(args.record_id)
            if payload is None:
                print(json.dumps({"error": "not_found", "record_id": args.record_id}, indent=2))
                return 1
        elif args.command == "timeline":
            start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
            payload = query.timeline(
                start,
                end,
                kinds=_parse_csv_set(args.kinds),
                statuses=_parse_csv_set(args.statuses),
                min_confidence=args.min_confidence,
                limit=args.limit,
            )
        elif args.command == "nearby":
            results = query.nearby(
                args.latitude,
                args.longitude,
                args.radius_m,
                kinds=_parse_csv_set(args.kinds),
                statuses=_parse_csv_set(args.statuses),
                min_confidence=args.min_confidence,
                limit=args.limit,
            )
            payload = [asdict(result) for result in results]
        else:
            return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
