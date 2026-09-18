from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

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


class WikiLeaksPlusDAdapter:
    """Normalize PlusD/Cablegate-style records into the shared archive model.

    Fetching/search discovery is intentionally kept separate from normalization:
    the public PlusD UI is HTML-oriented and may change, while the evidence-engine
    contract should remain stable. A collector can supply dictionaries parsed
    from search/detail pages, mirrors, or a future bulk export.
    """

    source_id = PLUS_D_SOURCE_ID

    def normalize(self, record: dict[str, Any]) -> SourceItem:
        reference = _text(record.get("reference") or record.get("cable_id") or record.get("id"))
        if not reference:
            raise ValueError("PlusD record requires a formal cable reference")

        source_url = _text(record.get("source_url"))
        if not source_url:
            source_url = f"https://wikileaks.org/plusd/cables/{reference}.html"

        origin = _text(record.get("origin") or record.get("from"))
        destinations = record.get("destinations") or record.get("to")
        title = _text(record.get("subject") or record.get("title"))
        date = _text(record.get("date") or record.get("document_date"))

        metadata = dict(record)
        metadata.setdefault("document_family", "diplomatic_cable")
        metadata.setdefault("formal_reference", reference)

        return SourceItem(
            id=f"{self.source_id}:{reference}",
            source_id=self.source_id,
            source_item_id=reference,
            source_url=source_url,
            title_raw=title,
            description_raw=_text(record.get("body") or record.get("summary")),
            creator_raw=origin,
            date_raw=date,
            archive_added_raw=_text(record.get("release_date") or record.get("published_at")),
            location_raw=_text(record.get("origin_location")),
            rights_raw=_text(record.get("rights")),
            collection_raw=_text(record.get("collection")) or "Cablegate / PlusD",
            media_type_raw="document",
            metadata_raw={
                **metadata,
                "destinations": destinations,
                "classification": record.get("classification") or record.get("original_classification"),
                "tags": record.get("tags") or record.get("traffic_analysis_tags"),
                "references_to": record.get("references_to"),
                "referenced_by": record.get("referenced_by"),
            },
            ingested_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value


class WikiLeaksWarDiariesAdapter:
    """Normalize Iraq/Afghan War Diaries SIGACT records into SourceItem."""

    source_id = WAR_DIARIES_SOURCE_ID

    def normalize(self, record: dict[str, Any]) -> SourceItem:
        tracking = _text(record.get("tracking_number") or record.get("id"))
        if not tracking:
            raise ValueError("War Diaries record requires tracking_number or id")

        public_id = _text(record.get("public_id") or record.get("uuid")) or tracking
        source_url = _text(record.get("source_url"))
        if not source_url:
            source_url = f"https://warlogs.wikileaks.org/id/{public_id}/"

        region = _text(record.get("region"))
        mgrs = _text(record.get("mgrs"))
        location_parts = [value for value in (region, mgrs) if value]

        metadata = dict(record)
        metadata.setdefault("document_family", "sigact")

        return SourceItem(
            id=f"{self.source_id}:{public_id}",
            source_id=self.source_id,
            source_item_id=public_id,
            source_url=source_url,
            title_raw=_text(record.get("title")),
            description_raw=_text(record.get("narrative") or record.get("body")),
            creator_raw=_text(record.get("reporting_unit") or record.get("originator_group")),
            date_raw=_text(record.get("date") or record.get("event_time")),
            location_raw=" | ".join(location_parts) if location_parts else None,
            collection_raw=_text(record.get("release")) or "Iraq/Afghan War Diaries",
            media_type_raw="event_record",
            metadata_raw={
                **metadata,
                "tracking_number": tracking,
                "type": record.get("type"),
                "category": record.get("category"),
                "region": record.get("region"),
                "reporting_unit": record.get("reporting_unit"),
                "unit_name": record.get("unit_name"),
                "unit_type": record.get("unit_type"),
                "casualties": {
                    "total": record.get("total_casualties"),
                    "friendly_wounded": record.get("friendly_wounded"),
                    "friendly_killed": record.get("friendly_killed"),
                    "host_nation_wounded": record.get("host_nation_wounded"),
                    "host_nation_killed": record.get("host_nation_killed"),
                    "civilian_wounded": record.get("civilian_wounded"),
                    "civilian_killed": record.get("civilian_killed"),
                },
                "mgrs": record.get("mgrs"),
                "classification": record.get("classification"),
                "affiliation": record.get("affiliation"),
                "ccir": record.get("ccir"),
                "sigact": record.get("sigact"),
            },
            ingested_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value
