from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from archive.models import SourceItem


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
        location_raw=payload.get("location_raw"),
        rights_raw=payload.get("rights_raw"),
        collection_raw=payload.get("collection_raw"),
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
