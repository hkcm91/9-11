from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from archive.query import ArchiveQuery

# These claim kinds can position an item on the historical timeline. Administrative
# dates and broad document coverage remain visible in record details but do not
# masquerade as a capture/recording time in the Explorer.
_TIMELINE_KIND_PRIORITY = {
    "capture_time": 0,
    "recording_time": 1,
    "event_time": 2,
    "interview_time": 3,
    "publication_time": 4,
}

_LOCATION_KIND_PRIORITY = {
    "capture_location": 0,
    "event_location": 1,
    "testimony_location": 2,
    "subject_location": 3,
    "document_coverage_location": 4,
    "unknown": 5,
}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _intersects(claim: dict[str, Any], start: datetime, end: datetime) -> bool:
    claim_start = _parse_datetime(claim.get("start_time"))
    claim_end = _parse_datetime(claim.get("end_time"))
    if claim_start is None and claim_end is None:
        return False
    if claim_start is not None and claim_start > end:
        return False
    if claim_end is not None and claim_end < start:
        return False
    return True


def _choose_temporal(
    claims: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    min_confidence: float,
) -> dict[str, Any] | None:
    eligible = [
        claim
        for claim in claims
        if claim.get("time_kind") in _TIMELINE_KIND_PRIORITY
        and float(claim.get("confidence") or 0.0) >= min_confidence
        and _intersects(claim, start, end)
    ]
    eligible.sort(
        key=lambda claim: (
            _TIMELINE_KIND_PRIORITY.get(str(claim.get("time_kind")), 99),
            -float(claim.get("confidence") or 0.0),
            str(claim.get("start_time") or claim.get("end_time") or ""),
        )
    )
    return eligible[0] if eligible else None


def _choose_spatial(
    claims: list[dict[str, Any]],
    *,
    min_confidence: float,
) -> dict[str, Any] | None:
    eligible = [
        claim
        for claim in claims
        if float(claim.get("confidence") or 0.0) >= min_confidence
    ]
    eligible.sort(
        key=lambda claim: (
            _LOCATION_KIND_PRIORITY.get(str(claim.get("location_kind")), 99),
            -float(claim.get("confidence") or 0.0),
        )
    )
    return eligible[0] if eligible else None


def _claim_summary(
    claim: dict[str, Any] | None, fields: tuple[str, ...]
) -> dict[str, Any] | None:
    if claim is None:
        return None
    return {field: claim.get(field) for field in fields if claim.get(field) is not None}


def build_explorer_payload(
    database: Path | str,
    *,
    start: datetime,
    end: datetime,
    min_confidence: float = 0.0,
    limit: int = 5000,
) -> dict[str, Any]:
    """Build a provenance-preserving read model for the public Explorer.

    The exporter never upgrades a claim's review status. It chooses one display
    claim for time and place so the UI can position a marker, while preserving
    confidence, method, and status alongside that position.
    """

    if end < start:
        raise ValueError("end must be on or after start")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    items: list[dict[str, Any]] = []
    with ArchiveQuery(database) as query:
        record_ids = [
            row["id"]
            for row in query.connection.execute(
                "SELECT id FROM source_records ORDER BY source_id, source_item_id LIMIT ?",
                (limit,),
            ).fetchall()
        ]

        for record_id in record_ids:
            bundle = query.item_bundle(record_id)
            if bundle is None:
                continue
            record = bundle["record"]
            temporal = _choose_temporal(
                bundle["temporal_claims"],
                start=start,
                end=end,
                min_confidence=min_confidence,
            )
            spatial = _choose_spatial(
                bundle["spatial_claims"],
                min_confidence=min_confidence,
            )

            # The MVP is intentionally reconstruction-oriented: an item needs a
            # useful historical time or a mappable location to enter the read model.
            if temporal is None and spatial is None:
                continue

            entity_claims = [
                {
                    key: claim.get(key)
                    for key in (
                        "entity_kind",
                        "role",
                        "name_raw",
                        "normalized_name",
                        "confidence",
                        "status",
                        "method",
                    )
                    if claim.get(key) is not None
                }
                for claim in bundle["entity_claims"][:8]
                if float(claim.get("confidence") or 0.0) >= min_confidence
            ]

            items.append(
                {
                    "id": record["id"],
                    "source_id": record["source_id"],
                    "source_item_id": record["source_item_id"],
                    "source_url": record["source_url"],
                    "title": record.get("title_raw"),
                    "description": record.get("description_raw"),
                    "creator": record.get("creator_raw"),
                    "collection": record.get("collection_raw"),
                    "media_type": record.get("media_type_raw"),
                    "rights": record.get("rights_raw"),
                    "time": _claim_summary(
                        temporal,
                        (
                            "time_kind",
                            "start_time",
                            "end_time",
                            "uncertainty_before_ms",
                            "uncertainty_after_ms",
                            "confidence",
                            "status",
                            "method",
                            "created_by_agent",
                        ),
                    ),
                    "location": _claim_summary(
                        spatial,
                        (
                            "location_kind",
                            "latitude",
                            "longitude",
                            "accuracy_radius_m",
                            "heading_deg",
                            "heading_uncertainty_deg",
                            "confidence",
                            "status",
                            "method",
                            "created_by_agent",
                        ),
                    ),
                    "entities": entity_claims,
                    "observation_count": len(bundle["observations"]),
                }
            )

    items.sort(
        key=lambda item: (
            str(
                (item.get("time") or {}).get("start_time")
                or (item.get("time") or {}).get("end_time")
                or "9999"
            ),
            item["source_id"],
            item["source_item_id"],
        )
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "min_confidence": min_confidence,
        "item_count": len(items),
        "items": items,
    }


def write_explorer_payload(
    database: Path | str,
    output: Path | str,
    *,
    start: datetime,
    end: datetime,
    min_confidence: float = 0.0,
    limit: int = 5000,
) -> dict[str, Any]:
    payload = build_explorer_payload(
        database,
        start=start,
        end=end,
        min_confidence=min_confidence,
        limit=limit,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a static Explorer read model from the evidence SQLite store."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--start",
        default="2001-09-11T08:00:00-04:00",
        help="Inclusive ISO-8601 historical window start.",
    )
    parser.add_argument(
        "--end",
        default="2001-09-11T12:00:00-04:00",
        help="Inclusive ISO-8601 historical window end.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=5000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    payload = write_explorer_payload(
        args.database,
        args.output,
        start=start,
        end=end,
        min_confidence=args.min_confidence,
        limit=args.limit,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "item_count": payload["item_count"],
                "window": payload["window"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
