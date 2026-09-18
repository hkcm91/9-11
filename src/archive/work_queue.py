"""Backward-compatible work-queue facade.

The queue engine itself is generic and lives in
``historical_engine.work_queue``. Record roles, task applicability, priority
multipliers, expected claim kinds and instructions now come from the active
collection instead of from hardcoded source ids.

These wrappers keep the original signatures: call them without a collection and
they use the transitional default (see ``archive.collections_compat``).
"""

from __future__ import annotations

from typing import Iterable

from archive.collections_compat import resolve_collection
from historical_engine.collection import Collection
from historical_engine.quality import EnrichmentPriority
from historical_engine.records import SourceRecord
from historical_engine.work_queue import EnrichmentTask
from historical_engine.work_queue import build_rights_queue as _build_rights_queue
from historical_engine.work_queue import build_work_queue as _build_work_queue
from historical_engine.work_queue import tasks_for_item as _tasks_for_item
from historical_engine.work_rules import TASK_FOR_FIELD, TASK_WEIGHT

__all__ = [
    "EnrichmentTask",
    "TASK_FOR_FIELD",
    "TASK_WEIGHT",
    "build_rights_queue",
    "build_work_queue",
    "tasks_for_item",
]


def tasks_for_item(
    item: SourceRecord,
    priority: EnrichmentPriority | None = None,
    *,
    include_rights: bool = False,
    collection: Collection | str | None = None,
) -> list[EnrichmentTask]:
    return _tasks_for_item(
        item,
        resolve_collection(collection),
        priority,
        include_rights=include_rights,
    )


def build_work_queue(
    records: Iterable[SourceRecord],
    *,
    include_rights: bool = False,
    collection: Collection | str | None = None,
) -> list[EnrichmentTask]:
    return _build_work_queue(
        records,
        resolve_collection(collection),
        include_rights=include_rights,
    )


def build_rights_queue(
    records: Iterable[SourceRecord],
    *,
    collection: Collection | str | None = None,
) -> list[EnrichmentTask]:
    return _build_rights_queue(records, resolve_collection(collection))
