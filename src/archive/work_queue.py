from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Iterable

from archive.heuristics import document_coverage_claim_from_title
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
    record_role: str
    expected_claim_kind: str | None
    reasons: list[str]
    instructions: str

    def to_dict(self) -> dict:
        return asdict(self)


def _task_id(item_id: str, task_type: str) -> str:
    digest = hashlib.sha256(f"{item_id}|{task_type}".encode("utf-8")).hexdigest()[:16]
    return f"task:{task_type}:{digest}"


def _record_role(item: SourceItem) -> str:
    """Infer workflow role from source structure before generic media labels."""

    media = (item.media_type_raw or "").lower()
    title = (item.title_raw or "").lower()
    collection = (item.collection_raw or "").lower()
    collection_id = item.metadata_raw.get("collection_id")
    try:
        collection_id = int(collection_id) if collection_id is not None else None
    except (TypeError, ValueError):
        collection_id = None

    # Source-specific roles are much more meaningful than generic `movies` or
    # missing item-type labels.
    if item.source_id == "internet-archive-understanding-911":
        return "broadcast"
    if item.source_id == "archdisk-911-photo-map":
        return "photo"
    if item.source_id == "september-11-digital-archive":
        if collection_id == 11:
            return "document"
        if collection_id == 267:
            return "testimony"
        if collection_id == 266:
            return "audio"

    if item.source_id == "nist-wtc-disaster-repository" or media == "repository_entry":
        return "repository"
    if media == "event_record" or item.metadata_raw.get("document_family") == "sigact":
        return "event_record"
    if "incident action plan" in title or any(token in media for token in ("document", "text", "pdf")):
        return "document"
    if "voices of 9.11" in collection or "oral history" in collection or "oral_history" in media:
        return "testimony"
    if "sonic memorial" in collection or "audio" in media or "sound" in media:
        return "audio"
    if any(token in media for token in ("photo", "image")):
        return "photo"
    if any(token in media for token in ("video", "movie", "film")):
        return "video"
    return "unknown"


def _expected_claim_kind(task_type: str, role: str) -> str | None:
    if task_type == "resolve_time":
        if role in {"photo", "video"}:
            return "capture_time"
        if role in {"audio", "broadcast"}:
            return "recording_time"
        if role == "testimony":
            return "interview_time_or_described_event_time"
        if role == "document":
            return "document_coverage"
        if role == "event_record":
            return "event_time"
        return "unknown"
    if task_type == "resolve_location":
        if role in {"photo", "video"}:
            return "capture_location"
        if role in {"audio", "testimony"}:
            return "testimony_or_recording_location"
        if role == "document":
            return "document_coverage_location"
        if role == "event_record":
            return "event_location"
        return "unknown"
    return None


def _instructions(task_type: str, role: str) -> str:
    if task_type == "resolve_time":
        role_text = {
            "photo": "capture time of the photograph",
            "video": "capture interval of the video",
            "audio": "recording interval of the audio",
            "broadcast": "broadcast recording interval",
            "testimony": "interview date and any separately evidenced event times described in the testimony",
            "document": "coverage/effective period of the document",
            "event_record": "time of the historical event described by the record",
        }.get(role, "historically relevant time represented by this record")
        return (
            f"Find the strongest available evidence for the {role_text}. Return a proposed time or interval, "
            "semantic time kind, uncertainty, evidence references, and method. Keep publication/archive dates "
            "separate. Do not replace source metadata or mark the result verified."
        )
    if task_type == "resolve_location":
        if role in {"photo", "video"}:
            return (
                "Propose the camera capture location and, when possible, heading. Cite visible landmarks, "
                "source testimony, maps, or neighboring sequence evidence; include an accuracy radius and confidence."
            )
        if role == "testimony":
            return (
                "Identify locations tied to the witness's described September 11 experiences and label each semantic role. "
                "Keep the later interview location separate from event locations and do not infer places from vague narrative text."
            )
        if role == "event_record":
            return (
                "Resolve the event location from structured coordinates/grid references or explicit source text. "
                "Preserve the original location notation, state conversion uncertainty, cite the source record, "
                "and do not infer a precise point from a broad region label alone."
            )
        return (
            "Identify only locations explicitly associated with the recording and label their semantic role. "
            "Do not turn a place merely mentioned in narrative text into a capture location."
        )
    if task_type == "resolve_creator":
        if role == "event_record":
            noun = "reporting or originating unit/organization"
        else:
            noun = "issuing organization or original creator" if role == "document" else "original photographer, videographer, broadcaster, recorder, or source"
        return (
            f"Resolve the {noun}. Preserve aliases and distinguish uploader/custodian from original creator. "
            "Return evidence and confidence rather than overwriting raw metadata."
        )
    if task_type == "resolve_rights":
        return (
            "Determine the best available rights/usage status from the custodial source. Public visibility is not "
            "permission to redistribute; record uncertainty explicitly and retain the exact rights statement when available."
        )
    if task_type == "classify_media":
        return "Determine the source media/document type without inferring facts not present in evidence."
    if task_type == "improve_description":
        return (
            "Produce a concise factual description grounded only in the source record and linked evidence. "
            "Do not add identities, locations, or event claims that have not been independently supported."
        )
    raise KeyError(task_type)


def _task_is_applicable(item: SourceItem, task_type: str, role: str) -> bool:
    # Repository category records are discovery infrastructure, not historical
    # media. They should not generate person/time/location research tasks.
    if role == "repository" and task_type in {
        "resolve_time", "resolve_location", "resolve_creator", "classify_media", "improve_description"
    }:
        return False

    # If a source/collection already tells us what kind of historical record it
    # is, a generic media-classification task adds no value.
    if task_type == "classify_media" and role != "unknown":
        return False

    # Internet Archive TV items are timeline/broadcast anchors. The item-level
    # archive record is not a Lower Manhattan camera position; scene-level
    # footage geolocation belongs to a future segmentation stage.
    if role == "broadcast" and task_type == "resolve_location":
        return False

    # Strict title parsing already resolves the document's coverage period.
    if role == "document" and task_type == "resolve_time" and document_coverage_claim_from_title(item) is not None:
        return False

    # A document's missing generic location should not be treated as a camera
    # geolocation problem. Coverage geography can be added later as a separate
    # structured relationship when it is actually useful.
    if role == "document" and task_type == "resolve_location":
        return False
    return True


def _role_multiplier(task_type: str, role: str) -> float:
    if task_type == "resolve_location":
        return {"photo": 1.0, "video": 1.0, "audio": 0.75, "testimony": 0.70, "event_record": 1.0}.get(role, 0.55)
    if task_type == "resolve_time":
        return {
            "photo": 1.0,
            "video": 1.0,
            "audio": 0.9,
            "broadcast": 0.95,
            "testimony": 0.65,
            "document": 0.55,
            "event_record": 1.0,
        }.get(role, 0.7)
    if task_type == "resolve_creator":
        return {"testimony": 0.55, "audio": 0.70, "document": 0.75}.get(role, 1.0)
    return 1.0


def tasks_for_item(
    item: SourceItem,
    priority: EnrichmentPriority | None = None,
    *,
    include_rights: bool = False,
) -> list[EnrichmentTask]:
    """Build research-enrichment tasks for one source item.

    Rights clearance is deliberately excluded from the default research queue.
    It is a publication/use gate rather than evidence needed to reconstruct the
    historical timeline. Callers can opt it back in for a rights-clearance pass.
    """

    priority = priority or prioritize_item(item)
    role = _record_role(item)
    tasks: list[EnrichmentTask] = []
    for missing_field in priority.missing_fields:
        task_type = TASK_FOR_FIELD.get(missing_field)
        if task_type is None:
            continue
        if task_type == "resolve_rights" and not include_rights:
            continue
        if not _task_is_applicable(item, task_type, role):
            continue
        task_priority = min(
            1.0,
            priority.enrichment_priority * TASK_WEIGHT[task_type] * _role_multiplier(task_type, role),
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
                expected_claim_kind=_expected_claim_kind(task_type, role),
                reasons=list(priority.reasons),
                instructions=_instructions(task_type, role),
            )
        )

    # Structured military/event records may contain a useful grid reference
    # without coordinates that the spatial query layer can consume. Queue a
    # conversion/review task even though location_raw is technically populated.
    if role == "event_record" and item.metadata_raw.get("mgrs"):
        has_resolve_location = any(task.task_type == "resolve_location" for task in tasks)
        has_coordinates = all(
            item.metadata_raw.get(key) not in (None, "")
            for key in ("latitude", "longitude")
        )
        if not has_resolve_location and not has_coordinates:
            tasks.append(
                EnrichmentTask(
                    task_id=_task_id(item.id, "resolve_location"),
                    item_id=item.id,
                    source_id=item.source_id,
                    task_type="resolve_location",
                    priority=round(
                        min(1.0, priority.enrichment_priority * TASK_WEIGHT["resolve_location"]),
                        4,
                    ),
                    source_url=item.source_url,
                    title=item.title_raw,
                    creator=item.creator_raw,
                    date=item.date_raw,
                    location=item.location_raw,
                    record_role=role,
                    expected_claim_kind="event_location",
                    reasons=[*priority.reasons, "structured grid reference needs coordinate conversion"],
                    instructions=_instructions("resolve_location", role),
                )
            )
    return tasks


def build_work_queue(
    records: Iterable[SourceItem],
    *,
    include_rights: bool = False,
) -> list[EnrichmentTask]:
    tasks: list[EnrichmentTask] = []
    for item in records:
        tasks.extend(tasks_for_item(item, include_rights=include_rights))
    return sorted(tasks, key=lambda task: (-task.priority, task.task_type, task.item_id))


def build_rights_queue(records: Iterable[SourceItem]) -> list[EnrichmentTask]:
    """Build only publication/rights-clearance tasks."""

    tasks: list[EnrichmentTask] = []
    for item in records:
        for task in tasks_for_item(item, include_rights=True):
            if task.task_type == "resolve_rights":
                tasks.append(task)
    return sorted(tasks, key=lambda task: (-task.priority, task.item_id))