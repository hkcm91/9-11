from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from archive.models import SourceItem


PLUS_D_SOURCE_ID = "wikileaks-plusd"
WAR_DIARIES_SOURCE_ID = "wikileaks-war-diaries"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        rendered = str(value).strip()
        return rendered or None
    if isinstance(value, list):
        rendered = "; ".join(str(item).strip() for item in value if str(item).strip())
        return rendered or None
    return None


def _key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _lookup(record: dict[str, Any], *names: str) -> Any:
    index = {_key(str(key)): value for key, value in record.items()}
    for name in names:
        wanted = _key(name)
        if wanted in index and index[wanted] not in (None, ""):
            return index[wanted]
    return None


def _split_multi(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
        return values or None
    rendered = str(value).strip()
    if not rendered:
        return None
    for separator in ("|", ";", ","):
        if separator in rendered:
            values = [part.strip() for part in rendered.split(separator) if part.strip()]
            return values or None
    return [rendered]


def load_tabular_records(path: Path | str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Load CSV, JSON, JSONL, or NDJSON records without discarding unknown fields."""

    path = Path(path)
    suffix = path.suffix.lower()
    records: list[dict[str, Any]] = []

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                records.append(dict(row))
                if limit is not None and len(records) >= limit:
                    break
        return records

    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number}: expected object")
                records.append(value)
                if limit is not None and len(records) >= limit:
                    break
        return records

    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            for key in ("records", "items", "documents", "results"):
                candidate = value.get(key)
                if isinstance(candidate, list):
                    value = candidate
                    break
        if not isinstance(value, list):
            raise ValueError(f"{path}: expected a JSON list or an object containing records/items")
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValueError(f"{path}: item {index} is not an object")
            records.append(item)
            if limit is not None and len(records) >= limit:
                break
        return records

    raise ValueError(f"unsupported WikiLeaks import format: {path.suffix}")


class WikiLeaksPlusDAdapter:
    """Normalize PlusD/Cablegate records into the shared evidence-engine model.

    The adapter intentionally accepts multiple common field spellings because
    Cablegate exports and mirrors use different CSV/header conventions. Unknown
    fields are preserved verbatim in metadata_raw.
    """

    source_id = PLUS_D_SOURCE_ID

    def normalize(self, record: dict[str, Any]) -> SourceItem:
        reference = _text(
            _lookup(
                record,
                "reference",
                "cable_id",
                "cableid",
                "mrn",
                "message_reference_number",
                "message reference number",
                "id",
            )
        )
        if not reference:
            raise ValueError("PlusD record requires a formal cable reference/MRN")

        source_url = _text(_lookup(record, "source_url", "url"))
        if not source_url:
            source_url = f"https://wikileaks.org/plusd/cables/{reference}.html"

        origin = _text(_lookup(record, "origin", "from", "sender", "office"))
        destinations = _split_multi(_lookup(record, "destinations", "destination", "to", "recipients"))
        title = _text(_lookup(record, "subject", "title", "caption"))
        date = _text(_lookup(record, "date", "document_date", "datetime", "sent_at"))
        body = _text(_lookup(record, "body", "content", "text", "cable", "document", "summary"))
        tags = _split_multi(_lookup(record, "tags", "traffic_analysis_tags", "traffic analysis by geography and subject"))
        references_to = _split_multi(_lookup(record, "references_to", "references", "ref", "refs"))
        referenced_by = _split_multi(_lookup(record, "referenced_by", "cited_by"))

        metadata = dict(record)
        metadata.setdefault("document_family", "diplomatic_cable")
        metadata.setdefault("formal_reference", reference)

        return SourceItem(
            id=f"{self.source_id}:{reference}",
            source_id=self.source_id,
            source_item_id=reference,
            source_url=source_url,
            title_raw=title,
            description_raw=body,
            creator_raw=origin,
            date_raw=date,
            archive_added_raw=_text(_lookup(record, "release_date", "published_at", "publicdate")),
            location_raw=_text(_lookup(record, "origin_location", "location")),
            rights_raw=_text(_lookup(record, "rights", "license")),
            collection_raw=_text(_lookup(record, "collection", "dataset")) or "Cablegate / PlusD",
            media_type_raw="document",
            metadata_raw={
                **metadata,
                "destinations": destinations,
                "classification": _lookup(
                    record,
                    "classification",
                    "original_classification",
                    "original classification",
                    "current_classification",
                ),
                "tags": tags,
                "references_to": references_to,
                "referenced_by": referenced_by,
            },
            ingested_at=datetime.now(timezone.utc),
        )

    def import_file(self, path: Path | str, *, limit: int | None = None) -> list[SourceItem]:
        return [self.normalize(record) for record in load_tabular_records(path, limit=limit)]

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value


class WikiLeaksWarDiariesAdapter:
    """Normalize Iraq/Afghan War Diaries SIGACT records into SourceItem.

    Supports normalized field names as well as common headings used by the
    original Afghan/Iraq CSV releases and later mirrors.
    """

    source_id = WAR_DIARIES_SOURCE_ID

    def normalize(self, record: dict[str, Any]) -> SourceItem:
        tracking = _text(
            _lookup(
                record,
                "tracking_number",
                "tracking number",
                "trackingnumber",
                "reportkey",
                "report_key",
                "id",
            )
        )
        if not tracking:
            raise ValueError("War Diaries record requires tracking number/report key")

        public_id = _text(_lookup(record, "public_id", "public id", "uuid", "reportkey")) or tracking
        source_url = _text(_lookup(record, "source_url", "url"))
        if not source_url:
            source_url = f"https://warlogs.wikileaks.org/id/{public_id}/"

        region = _text(_lookup(record, "region"))
        mgrs = _text(_lookup(record, "mgrs", "mgrs coordinate", "mgrs_coordinate"))
        location_parts = [value for value in (region, mgrs) if value]

        metadata = dict(record)
        metadata.setdefault("document_family", "sigact")

        casualties = {
            "total": _lookup(record, "total_casualties", "total casualties", "totalcasualties"),
            "friendly_wounded": _lookup(record, "friendly_wounded", "friendly wia", "friendlywia"),
            "friendly_killed": _lookup(record, "friendly_killed", "friendly kia", "friendlykia"),
            "host_nation_wounded": _lookup(record, "host_nation_wounded", "host nation wia", "hostnationwia"),
            "host_nation_killed": _lookup(record, "host_nation_killed", "host nation kia", "hostnationkia"),
            "civilian_wounded": _lookup(record, "civilian_wounded", "civilian wia", "civilianwia"),
            "civilian_killed": _lookup(record, "civilian_killed", "civilian kia", "civiliankia"),
            "enemy_wounded": _lookup(record, "enemy_wounded", "enemy wia", "enemywia"),
            "enemy_killed": _lookup(record, "enemy_killed", "enemy kia", "enemykia"),
            "enemy_detained": _lookup(record, "enemy_detained", "enemy detained", "enemydetained"),
        }

        return SourceItem(
            id=f"{self.source_id}:{public_id}",
            source_id=self.source_id,
            source_item_id=public_id,
            source_url=source_url,
            title_raw=_text(_lookup(record, "title")),
            description_raw=_text(_lookup(record, "narrative", "summary", "body", "description")),
            creator_raw=_text(_lookup(record, "reporting_unit", "reporting unit", "originator_group", "originator group")),
            date_raw=_text(_lookup(record, "date", "event_time", "event time", "datetime", "timestamp")),
            location_raw=" | ".join(location_parts) if location_parts else None,
            collection_raw=_text(_lookup(record, "release", "collection", "dataset")) or "Iraq/Afghan War Diaries",
            media_type_raw="event_record",
            metadata_raw={
                **metadata,
                "tracking_number": tracking,
                "type": _lookup(record, "type"),
                "category": _lookup(record, "category"),
                "region": _lookup(record, "region"),
                "reporting_unit": _lookup(record, "reporting_unit", "reporting unit"),
                "unit_name": _lookup(record, "unit_name", "unit name"),
                "unit_type": _lookup(record, "unit_type", "type_of_unit", "type of unit"),
                "casualties": casualties,
                "mgrs": mgrs,
                "classification": _lookup(record, "classification"),
                "affiliation": _lookup(record, "affiliation", "attack_on", "attack on"),
                "ccir": _lookup(record, "ccir"),
                "sigact": _lookup(record, "sigact"),
            },
            ingested_at=datetime.now(timezone.utc),
        )

    def import_file(self, path: Path | str, *, limit: int | None = None) -> list[SourceItem]:
        return [self.normalize(record) for record in load_tabular_records(path, limit=limit)]

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value
