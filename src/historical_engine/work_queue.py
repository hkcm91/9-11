"""Collection-aware research work queue.

The queue engine knows nothing about any particular archive. For each record it
asks the active collection:

* what *role* does this record play?
* does this task type apply to it?
* how should its priority be scaled?
* what claim kind should the researcher return, and with what instructions?
* does collection policy force human review?

Rights clearance is deliberately excluded from the default research queue: it
is a publication gate, not evidence needed to reconstruct the historical
record. ``build_rights_queue`` produces that pass separately.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Iterable

from historical_engine.collection import Collection
from historical_engine.quality import EnrichmentPriority, prioritize_item
from historical_engine.records import SourceRecord
from historical_engine.work_rules import TASK_FOR_FIELD, TASK_WEIGHT


@dataclass(slots=True)
class EnrichmentTask:
    task_id: str
    item_id: str
    source_id: str
    task_type: str
    priority: float
    source_url: str
    title: str | None
    creator: str | None
    date: str | None
    location: str | None
    record_role: str
    expected_claim_kind: str | None
    reasons: list[str]
    instructions: str
    collection_id: str | None = None
    requires_human_review: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _task_id(item_id: str, task_type: str) -> str:
    digest = hashlib.sha256(f"{item_id}|{task_type}".encode("utf-8")).hexdigest()[:16]
    return f"task:{task_type}:{digest}"


def priority_for(collection: Collection, item: SourceRecord) -> EnrichmentPriority:
    return prioritize_item(
        item,
        source_value=collection.source_value(item.source_id),
        extra_reasons=collection.hooks.priority_reasons,
    )


def tasks_for_item(
    item: SourceRecord,
    collection: Collection,
    priority: EnrichmentPriority | None = None,
    *,
    include_rights: bool = False,
) -> list[EnrichmentTask]:
    """Build research-enrichment tasks for one source record."""

    priority = priority or priority_for(collection, item)
    role = collection.classify_record(item)
    tasks: list[EnrichmentTask] = []
    for missing_field in priority.missing_fields:
        task_type = TASK_FOR_FIELD.get(missing_field)
        if task_type is None:
            continue
        if task_type == "resolve_rights" and not include_rights:
            continue
        if not collection.task_applies(item, task_type, role):
            continue
        task_priority = min(
            1.0,
            priority.enrichment_priority
            * TASK_WEIGHT[task_type]
            * collection.task_priority_multiplier(task_type, role),
        )
        tasks.append(
            EnrichmentTask(
                task_id=_task_id(item.id, task_type),
                item_id=item.id,
                source_id=item.source_id,
                task_type=task_type,
                priority=round(task_priority, 4),
                source_url=item.source_url,
                title=item.title_raw,
                creator=item.creator_raw,
                date=item.date_raw,
                location=item.location_raw,
                record_role=role,
                expected_claim_kind=collection.expected_claim_kind(task_type, role),
                reasons=list(priority.reasons),
                instructions=collection.task_instructions(task_type, role),
                collection_id=collection.id,
                requires_human_review=collection.requires_human_review(
                    record=item, task_type=task_type, role=role
                ),
            )
        )
    return tasks


def build_work_queue(
    records: Iterable[SourceRecord],
    collection: Collection,
    *,
    include_rights: bool = False,
) -> list[EnrichmentTask]:
    tasks: list[EnrichmentTask] = []
    for item in records:
        tasks.extend(tasks_for_item(item, collection, include_rights=include_rights))
    return sorted(tasks, key=lambda task: (-task.priority, task.task_type, task.item_id))


def build_rights_queue(
    records: Iterable[SourceRecord],
    collection: Collection,
) -> list[EnrichmentTask]:
    """Build only publication/rights-clearance tasks."""

    tasks: list[EnrichmentTask] = []
    for item in records:
        for task in tasks_for_item(item, collection, include_rights=True):
            if task.task_type == "resolve_rights":
                tasks.append(task)
    return sorted(tasks, key=lambda task: (-task.priority, task.item_id))
