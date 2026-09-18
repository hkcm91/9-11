"""Backward-compatible enrichment-prioritisation facade.

Scoring is generic and lives in ``historical_engine.quality``. How much each
custodial source is worth — and which metadata shapes are worth flagging to a
researcher — belongs to the collection.
"""

from __future__ import annotations

from typing import Iterable

from archive.collections_compat import resolve_collection
from historical_engine.collection import Collection
from historical_engine.quality import (
    DEFAULT_SOURCE_VALUE,
    WEIGHTS,
    EnrichmentPriority,
)
from historical_engine.quality import prioritize_item as _prioritize_item
from historical_engine.records import SourceRecord

__all__ = [
    "DEFAULT_SOURCE_VALUE",
    "EnrichmentPriority",
    "SOURCE_VALUE",
    "WEIGHTS",
    "prioritize_item",
    "prioritize_records",
]


def _source_value_table() -> dict[str, float]:
    from evidence_collections.september11.rules import SOURCE_VALUE as table

    return dict(table)


def __getattr__(name: str):
    # ``archive.quality.SOURCE_VALUE`` was the 9/11 per-source value table. It
    # now belongs to the September 11 collection; the name is kept as a
    # deprecated read-only view so existing imports keep working.
    if name == "SOURCE_VALUE":
        return _source_value_table()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def prioritize_item(
    item: SourceRecord,
    *,
    collection: Collection | str | None = None,
) -> EnrichmentPriority:
    active = resolve_collection(collection)
    return _prioritize_item(
        item,
        source_value=active.source_value(item.source_id),
        extra_reasons=active.hooks.priority_reasons,
    )


def prioritize_records(
    records: Iterable[SourceRecord],
    *,
    collection: Collection | str | None = None,
) -> list[EnrichmentPriority]:
    active = resolve_collection(collection)
    priorities = [prioritize_item(item, collection=active) for item in records]
    return sorted(priorities, key=lambda row: (-row.enrichment_priority, row.item_id))
