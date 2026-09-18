"""Generic, role-driven work-queue rules.

Everything here is a function of the *record role* — never of a source
identifier. Collections override any of it through the ``Collection``
interface. The first collection migrated onto the engine overrides none of it,
which is the clearest evidence that these rules really were generic.
"""

from __future__ import annotations

from typing import Callable

from historical_engine.records import SourceRecord
from historical_engine.roles import (
    ROLE_AUDIO,
    ROLE_BROADCAST,
    ROLE_DOCUMENT,
    ROLE_PHOTO,
    ROLE_REPOSITORY,
    ROLE_TESTIMONY,
    ROLE_UNKNOWN,
    ROLE_VIDEO,
)

TASK_FOR_FIELD: dict[str, str] = {
    "date_raw": "resolve_time",
    "location_raw": "resolve_location",
    "creator_raw": "resolve_creator",
    "rights_raw": "resolve_rights",
    "description_raw": "improve_description",
    "media_type_raw": "classify_media",
}

TASK_WEIGHT: dict[str, float] = {
    "resolve_time": 1.00,
    "resolve_location": 1.00,
    "resolve_creator": 0.85,
    "resolve_rights": 0.75,
    "classify_media": 0.55,
    "improve_description": 0.45,
}

#: Tasks that make no sense for a discovery/navigation record.
_REPOSITORY_SUPPRESSED = frozenset(
    {"resolve_time", "resolve_location", "resolve_creator", "classify_media", "improve_description"}
)


def expected_claim_kind(task_type: str, role: str) -> str | None:
    if task_type == "resolve_time":
        if role in {ROLE_PHOTO, ROLE_VIDEO}:
            return "capture_time"
        if role in {ROLE_AUDIO, ROLE_BROADCAST}:
            return "recording_time"
        if role == ROLE_TESTIMONY:
            return "interview_time_or_described_event_time"
        if role == ROLE_DOCUMENT:
            return "document_coverage"
        return "unknown"
    if task_type == "resolve_location":
        if role in {ROLE_PHOTO, ROLE_VIDEO}:
            return "capture_location"
        if role in {ROLE_AUDIO, ROLE_TESTIMONY}:
            return "testimony_or_recording_location"
        if role == ROLE_DOCUMENT:
            return "document_coverage_location"
        return "unknown"
    return None


def instructions(task_type: str, role: str) -> str:
    if task_type == "resolve_time":
        role_text = {
            ROLE_PHOTO: "capture time of the photograph",
            ROLE_VIDEO: "capture interval of the video",
            ROLE_AUDIO: "recording interval of the audio",
            ROLE_BROADCAST: "broadcast recording interval",
            ROLE_TESTIMONY: (
                "interview date and any separately evidenced event times described in the testimony"
            ),
            ROLE_DOCUMENT: "coverage/effective period of the document",
        }.get(role, "historically relevant time represented by this record")
        return (
            f"Find the strongest available evidence for the {role_text}. Return a proposed time or interval, "
            "semantic time kind, uncertainty, evidence references, and method. Keep publication/archive dates "
            "separate. Do not replace source metadata or mark the result verified."
        )
    if task_type == "resolve_location":
        if role in {ROLE_PHOTO, ROLE_VIDEO}:
            return (
                "Propose the camera capture location and, when possible, heading. Cite visible landmarks, "
                "source testimony, maps, or neighboring sequence evidence; include an accuracy radius and confidence."
            )
        if role == ROLE_TESTIMONY:
            return (
                "Identify locations tied to the witness's described experiences and label each semantic role. "
                "Keep the later interview location separate from event locations and do not infer places from "
                "vague narrative text."
            )
        return (
            "Identify only locations explicitly associated with the recording and label their semantic role. "
            "Do not turn a place merely mentioned in narrative text into a capture location."
        )
    if task_type == "resolve_creator":
        noun = (
            "issuing organization or original creator"
            if role == ROLE_DOCUMENT
            else "original photographer, videographer, broadcaster, recorder, or source"
        )
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


def role_multiplier(task_type: str, role: str) -> float:
    if task_type == "resolve_location":
        return {ROLE_PHOTO: 1.0, ROLE_VIDEO: 1.0, ROLE_AUDIO: 0.75, ROLE_TESTIMONY: 0.70}.get(role, 0.55)
    if task_type == "resolve_time":
        return {
            ROLE_PHOTO: 1.0,
            ROLE_VIDEO: 1.0,
            ROLE_AUDIO: 0.9,
            ROLE_BROADCAST: 0.95,
            ROLE_TESTIMONY: 0.65,
            ROLE_DOCUMENT: 0.55,
        }.get(role, 0.7)
    if task_type == "resolve_creator":
        return {ROLE_TESTIMONY: 0.55, ROLE_AUDIO: 0.70, ROLE_DOCUMENT: 0.75}.get(role, 1.0)
    return 1.0


def task_applies(
    record: SourceRecord,
    task_type: str,
    role: str,
    *,
    has_deterministic_time: Callable[[SourceRecord], bool] | None = None,
) -> bool:
    # Repository/category records are discovery infrastructure, not historical
    # media. They should not generate person/time/location research tasks.
    if role == ROLE_REPOSITORY and task_type in _REPOSITORY_SUPPRESSED:
        return False

    # If a source/collection already tells us what kind of historical record it
    # is, a generic media-classification task adds no value.
    if task_type == "classify_media" and role != ROLE_UNKNOWN:
        return False

    # A broadcast item is a timeline anchor. The item-level archive record is
    # not a camera position; scene-level footage geolocation belongs to a later
    # segmentation stage.
    if role == ROLE_BROADCAST and task_type == "resolve_location":
        return False

    # A deterministic parser has already resolved this document's coverage
    # period, so there is nothing to research.
    if (
        role == ROLE_DOCUMENT
        and task_type == "resolve_time"
        and has_deterministic_time is not None
        and has_deterministic_time(record)
    ):
        return False

    # A document's missing generic location should not be treated as a camera
    # geolocation problem. Coverage geography can be added later as a separate
    # structured relationship when it is actually useful.
    if role == ROLE_DOCUMENT and task_type == "resolve_location":
        return False
    return True
