from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Iterable

from archive.models import SourceItem
from archive.quality import EnrichmentPriority, prioritize_item


TASK_FOR_FIELD = {
    "date_raw": "resolve_time",
    "location_raw": "resolve_location",
    "creator_raw": "resolve_creator",
    "rights_raw": "resolve_rights",
    "description_raw": "improve_description",
    "media_type_raw": "classify_media",
}

TASK_WEIGHT = {
    "resolve_time": 1.00,
    "resolve_location": 1.00,
    "resolve_creator": 0.85,
    "resolve_rights": 0.75,
    "classify_media": 0.55,
    "improve_description": 0.45,
}


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
    reasons: list[str]
    instructions: str

    def to_dict(self) -> dict:
        return asdict(self)


def _task_id(item_id: str, task_type: str) -> str:
    digest = hashlib.sha256(f"{item_id}|{task_type}".encode("utf-8")).hexdigest()[:16]
    return f"task:{task_type}:{digest}"


def _instructions(task_type: str) -> str:
    return {
        "resolve_time": (
            "Find the strongest available evidence for when the media/event occurred. "
            "Return a proposed time or interval, uncertainty, evidence references, and method. "
            "Do not replace source metadata or mark the result verified."
        ),
        "resolve_location": (
            "Propose the capture/event location and, when possible, camera heading. "
            "Cite visible landmarks, source testimony, maps, or neighboring sequence evidence; "
            "include an accuracy radius and confidence."
        ),
        "resolve_creator": (
            "Resolve the original photographer, videographer, broadcaster, recorder, or source. "
            "Preserve aliases and distinguish uploader/custodian from original creator."
        ),
        "resolve_rights": (
            "Determine the best available rights/usage status from the custodial source. "
            "Public visibility is not permission to redistribute; record uncertainty explicitly."
        ),
        "classify_media": "Determine the source media type without inferring facts not present in evidence.",
        "improve_description": (
            "Produce a concise factual description grounded only in the source record and linked evidence. "
            "Do not add identities, locations, or event claims that have not been independently supported."
        ),
    }[task_type]


def tasks_for_item(item: SourceItem, priority: EnrichmentPriority | None = None) -> list[EnrichmentTask]:
    priority = priority or prioritize_item(item)
    tasks: list[EnrichmentTask] = []
    for missing_field in priority.missing_fields:
        task_type = TASK_FOR_FIELD.get(missing_field)
        if task_type is None:
            continue
        task_priority = min(1.0, priority.enrichment_priority * TASK_WEIGHT[task_type])
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
                reasons=list(priority.reasons),
                instructions=_instructions(task_type),
            )
        )
    return tasks


def build_work_queue(records: Iterable[SourceItem]) -> list[EnrichmentTask]:
    tasks: list[EnrichmentTask] = []
    for item in records:
        tasks.extend(tasks_for_item(item))
    return sorted(tasks, key=lambda task: (-task.priority, task.task_type, task.item_id))
