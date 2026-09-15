from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ReviewStatus(StrEnum):
    RAW = "raw"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class MediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    OTHER = "other"


class TimeKind(StrEnum):
    EVENT = "event_time"
    CAPTURE = "capture_time"
    RECORDING = "recording_time"
    DOCUMENT_COVERAGE = "document_coverage"
    INTERVIEW = "interview_time"
    PUBLICATION = "publication_time"
    ARCHIVE_INGEST = "archive_ingest_time"
    UNKNOWN = "unknown"


class LocationKind(StrEnum):
    EVENT = "event_location"
    CAPTURE = "capture_location"
    TESTIMONY = "testimony_location"
    DOCUMENT_COVERAGE = "document_coverage_location"
    SUBJECT = "subject_location"
    UNKNOWN = "unknown"


class EntityKind(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    RESPONDER_UNIT = "responder_unit"
    BUILDING = "building"
    VEHICLE = "vehicle"
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"
    OTHER = "other"


class EntityRole(StrEnum):
    SUBJECT = "subject"
    INTERVIEWEE = "interviewee"
    CREATOR = "creator"
    BROADCASTER = "broadcaster"
    WITNESS = "witness"
    RESPONDER = "responder"
    MENTIONED = "mentioned"


@dataclass(slots=True)
class SourceItem:
    id: str
    source_id: str
    source_item_id: str
    source_url: str
    title_raw: str | None = None
    description_raw: str | None = None
    creator_raw: str | None = None
    date_raw: str | None = None
    archive_added_raw: str | None = None
    location_raw: str | None = None
    rights_raw: str | None = None
    collection_raw: str | None = None
    media_type_raw: str | None = None
    metadata_raw: dict[str, Any] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class EvidenceRef:
    source_item_id: str
    relationship: str = "supports"
    note: str | None = None
    weight: float | None = None


@dataclass(slots=True)
class TemporalClaim:
    subject_id: str
    time_kind: TimeKind = TimeKind.UNKNOWN
    start_time: datetime | None = None
    end_time: datetime | None = None
    uncertainty_before_ms: int | None = None
    uncertainty_after_ms: int | None = None
    confidence: float = 0.0
    status: ReviewStatus = ReviewStatus.PROPOSED
    method: str | None = None
    created_by_agent: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(slots=True)
class SpatialClaim:
    subject_id: str
    latitude: float
    longitude: float
    location_kind: LocationKind = LocationKind.UNKNOWN
    accuracy_radius_m: float | None = None
    heading_deg: float | None = None
    heading_uncertainty_deg: float | None = None
    confidence: float = 0.0
    status: ReviewStatus = ReviewStatus.PROPOSED
    method: str | None = None
    created_by_agent: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(slots=True)
class EntityReferenceClaim:
    subject_id: str
    entity_kind: EntityKind
    role: EntityRole
    name_raw: str
    normalized_name: str | None = None
    confidence: float = 0.0
    status: ReviewStatus = ReviewStatus.PROPOSED
    method: str | None = None
    created_by_agent: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass(slots=True)
class AgentProposal:
    agent_name: str
    agent_version: str
    subject_id: str
    proposal_type: str
    proposal_value: dict[str, Any]
    confidence: float
    evidence: list[EvidenceRef] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    notes: str | None = None
