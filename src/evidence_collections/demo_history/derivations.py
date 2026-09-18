"""Deterministic derivations for the synthetic demo collection.

These exist to exercise the *generic* derivation hook with a second, unrelated
corpus. They read explicit structured fields only — nothing is guessed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from archive.models import (
    EntityKind,
    EntityReferenceClaim,
    EntityRole,
    EvidenceRef,
    SourceItem,
    TemporalClaim,
    TimeKind,
)

#: Source id -> (metadata key, method, confidence, note)
_EVENT_TIME_FIELDS: dict[str, tuple[str, str, float, str]] = {
    "demo-borough-record-office": (
        "reported_fire_start",
        "demo_inspection_report_reported_start",
        0.80,
        "Start time as recorded in the borough inspector's report.",
    ),
    "demo-oral-history-project": (
        "recounted_fire_start",
        "demo_testimony_recounted_start",
        0.55,
        "Start time as recounted by the interviewee decades after the event.",
    ),
}


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def derive_temporal(item: SourceItem) -> Iterable[TemporalClaim]:
    spec = _EVENT_TIME_FIELDS.get(item.source_id)
    if spec is None:
        return []
    key, method, confidence, note = spec
    start = _parse(item.metadata_raw.get(key))
    if start is None:
        return []
    return [
        TemporalClaim(
            subject_id=item.id,
            time_kind=TimeKind.EVENT,
            start_time=start,
            end_time=None,
            confidence=confidence,
            method=method,
            created_by_agent="deterministic-demo-importer",
            evidence=[
                EvidenceRef(
                    source_item_id=item.id,
                    relationship=key,
                    note=note,
                    weight=confidence,
                )
            ],
        )
    ]


def derive_entities(item: SourceItem) -> Iterable[EntityReferenceClaim]:
    label = item.metadata_raw.get("interviewee_label")
    if not isinstance(label, str) or "," not in label:
        return []
    family, _, given = label.partition(",")
    normalized = f"{given.strip()} {family.strip()}".strip()
    if not normalized:
        return []
    return [
        EntityReferenceClaim(
            subject_id=item.id,
            entity_kind=EntityKind.PERSON,
            role=EntityRole.INTERVIEWEE,
            name_raw=label,
            normalized_name=normalized,
            confidence=0.95,
            method="demo_interviewee_label",
            created_by_agent="deterministic-demo-entity-parser",
            evidence=[
                EvidenceRef(
                    source_item_id=item.id,
                    relationship="interviewee_label",
                    note=f"Interviewee label preserved verbatim from source metadata: {label}",
                    weight=0.95,
                )
            ],
        )
    ]
