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
    location_raw: str | None = None
    rights_raw: str | None = None
    collection_raw: str | None = None
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
    accuracy_radius_m: float | None = None
    heading_deg: float | None = None
    heading_uncertainty_deg: float | None = None
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
