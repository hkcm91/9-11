"""Structural view of a source record.

The engine deliberately does not import any concrete record class. It reads
records through this protocol so that a collection may supply its own record
type, and so that the engine carries no dependency on whichever collection
package happens to define the first implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SourceRecord(Protocol):
    """One immutable observation of one item in one custodial source."""

    id: str
    source_id: str
    source_item_id: str
    source_url: str
    title_raw: str | None
    description_raw: str | None
    creator_raw: str | None
    date_raw: str | None
    archive_added_raw: str | None
    location_raw: str | None
    rights_raw: str | None
    collection_raw: str | None
    media_type_raw: str | None
    metadata_raw: dict[str, Any]


def media_text(record: SourceRecord) -> str:
    return (record.media_type_raw or "").lower()


def title_text(record: SourceRecord) -> str:
    return (record.title_raw or "").lower()


def collection_text(record: SourceRecord) -> str:
    return (record.collection_raw or "").lower()


def metadata_int(record: SourceRecord, key: str) -> int | None:
    """Read an integer-ish metadata value without raising on junk input."""

    value = record.metadata_raw.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
