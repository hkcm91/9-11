from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from archive.models import SourceItem

_NORMALIZED_FIELDS = (
    "title_raw",
    "description_raw",
    "creator_raw",
    "date_raw",
    "archive_added_raw",
    "location_raw",
    "rights_raw",
    "collection_raw",
    "media_type_raw",
)


def source_item_from_dict(payload: dict) -> SourceItem:
    ingested_at = payload.get("ingested_at")
    if isinstance(ingested_at, str):
        ingested_at = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    elif not isinstance(ingested_at, datetime):
        ingested_at = datetime.utcnow()

    return SourceItem(
        id=str(payload["id"]),
        source_id=str(payload["source_id"]),
        source_item_id=str(payload["source_item_id"]),
        source_url=str(payload["source_url"]),
        title_raw=payload.get("title_raw"),
        description_raw=payload.get("description_raw"),
        creator_raw=payload.get("creator_raw"),
        date_raw=payload.get("date_raw"),
        archive_added_raw=payload.get("archive_added_raw"),
        location_raw=payload.get("location_raw"),
        rights_raw=payload.get("rights_raw"),
        collection_raw=payload.get("collection_raw"),
        media_type_raw=payload.get("media_type_raw"),
        metadata_raw=payload.get("metadata_raw") or {},
        ingested_at=ingested_at,
    )


def load_jsonl(path: Path) -> list[SourceItem]:
    records: list[SourceItem] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            records.append(source_item_from_dict(payload))
    return records


def _record_richness(item: SourceItem) -> tuple[int, int, int, float]:
    """Rank snapshots of the same source record without altering either one.

    Phase 0 can intentionally collect both a cheap search snapshot and a richer
    detail snapshot for the same source identifier. Downstream analysis should
    count that historical source item once, using the richest observed snapshot.
    Raw JSONL inputs remain untouched for audit/reproducibility.
    """

    populated = sum(1 for field in _NORMALIZED_FIELDS if getattr(item, field) not in (None, "", [], {}))
    raw_key_count = len(item.metadata_raw)
    nested_detail_bonus = sum(
        1 for key in ("_archive_metadata", "_file_summary", "_dcmes", "_nist_normalized")
        if item.metadata_raw.get(key) not in (None, "", [], {})
    )
    try:
        timestamp = item.ingested_at.timestamp()
    except (ValueError, OSError):
        timestamp = 0.0
    return populated, nested_detail_bonus, raw_key_count, timestamp


def reconcile_source_snapshots(records: Iterable[SourceItem]) -> list[SourceItem]:
    """Return one richest processing snapshot per stable SourceItem.id.

    This is an analysis/read-model reconciliation step, not archival mutation.
    Multiple raw observations remain available in their original ingestion files.
    """

    selected: dict[str, SourceItem] = {}
    order: list[str] = []
    for item in records:
        existing = selected.get(item.id)
        if existing is None:
            selected[item.id] = item
            order.append(item.id)
            continue
        if _record_richness(item) > _record_richness(existing):
            selected[item.id] = item
    return [selected[item_id] for item_id in order]
