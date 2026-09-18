"""Generic evidence-graph vocabulary.

These types are deliberately *additive*. They do not replace the source-record
and claim structures the pipeline already relies on; they give the engine
first-class ways to say "this canonical person exists", "these two claims
contradict each other", "this assessment superseded that one" — always with
provenance and always separately from the raw observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewState(StrEnum):
    """Lifecycle of a derived assertion. Mirrors ``archive.models.ReviewStatus``."""

    RAW = "raw"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


#: States a machine/AI pathway may never assign on its own.
HUMAN_ONLY_STATES: frozenset[str] = frozenset(
    {ReviewState.REVIEWED, ReviewState.VERIFIED, ReviewState.REJECTED, ReviewState.DISPUTED}
)


class EntityType(StrEnum):
    """Generic entity vocabulary.

    Responder-, military- or conflict-specific concepts belong in a collection
    ontology, which may extend this list with its own string types.
    """

    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    BUILDING = "building"
    UNIT = "unit"
    VEHICLE = "vehicle"
    VESSEL = "vessel"
    AIRCRAFT = "aircraft"
    DOCUMENT = "document"
    OTHER = "other"


class AssertionLevel(StrEnum):
    """How strongly the record supports a link.

    A generic "connected to" edge erases exactly the distinctions that matter
    most in a sensitive collection, so the engine forces the caller to say
    which one it means.
    """

    MENTIONED = "mentioned"
    ASSOCIATED = "associated"
    ALLEGED = "alleged"
    WITNESSED = "witnessed"
    REPORTED = "reported"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
    ESTABLISHED = "established"


#: Assertion levels that must never be reached without human review.
HUMAN_ONLY_ASSERTION_LEVELS: frozenset[str] = frozenset(
    {AssertionLevel.ESTABLISHED, AssertionLevel.CORROBORATED}
)


class ClaimRelationType(StrEnum):
    """Claim-to-claim reasoning edges."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    PARTIALLY_CORROBORATES = "partially_corroborates"
    SUPERSEDES = "supersedes"
    DUPLICATES = "duplicates"
    DERIVES_FROM = "derives_from"
    REFINES = "refines"


@dataclass(slots=True)
class CollectionRecord:
    """Registry row describing one historical corpus."""

    id: str
    name: str
    description: str = ""
    ontology_version: str = "0"
    config_version: str = "0"
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Provenance:
    """Who/what produced a derived statement, and on what basis."""

    method: str
    created_by_agent: str | None = None
    agent_version: str | None = None
    proposal_id: str | None = None
    claim_id: str | None = None
    note: str | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class EvidenceItem:
    """First-class, reusable evidence reference.

    Compatible with the embedded ``EvidenceRef`` dicts already stored on
    claims: ``from_ref``/``to_ref`` round-trip the existing shape.
    """

    source_item_id: str
    relationship: str = "supports"
    note: str | None = None
    weight: float | None = None
    evidence_id: str | None = None
    locator: str | None = None

    @classmethod
    def from_ref(cls, payload: Any) -> "EvidenceItem":
        if isinstance(payload, EvidenceItem):
            return payload
        if isinstance(payload, dict):
            return cls(
                source_item_id=str(payload["source_item_id"]),
                relationship=str(payload.get("relationship") or "supports"),
                note=payload.get("note"),
                weight=payload.get("weight"),
                evidence_id=payload.get("evidence_id"),
                locator=payload.get("locator"),
            )
        # dataclass-shaped EvidenceRef from archive.models
        return cls(
            source_item_id=str(getattr(payload, "source_item_id")),
            relationship=str(getattr(payload, "relationship", "supports") or "supports"),
            note=getattr(payload, "note", None),
            weight=getattr(payload, "weight", None),
        )

    def to_ref(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_item_id": self.source_item_id,
            "relationship": self.relationship,
        }
        if self.note is not None:
            payload["note"] = self.note
        if self.weight is not None:
            payload["weight"] = self.weight
        if self.evidence_id is not None:
            payload["evidence_id"] = self.evidence_id
        if self.locator is not None:
            payload["locator"] = self.locator
        return payload


@dataclass(slots=True)
class Entity:
    """Canonical entity. Resolution of a mention to an entity is itself a claim."""

    id: str
    collection_id: str
    entity_type: str
    canonical_name: str
    description: str | None = None
    status: ReviewState = ReviewState.PROPOSED
    confidence: float = 0.0
    provenance: Provenance | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EntityAlias:
    """An alternate name or spelling, kept with the provenance that produced it."""

    entity_id: str
    alias: str
    alias_kind: str = "alternate_name"
    language: str | None = None
    status: ReviewState = ReviewState.PROPOSED
    confidence: float = 0.0
    provenance: Provenance | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass(slots=True)
class Event:
    """A historical event or episode. Exact timestamps are never required."""

    id: str
    collection_id: str
    name: str
    event_type: str = "episode"
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    time_precision: str | None = None
    status: ReviewState = ReviewState.PROPOSED
    confidence: float = 0.0
    provenance: Provenance | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Relationship:
    """A provenance-carrying graph edge: subject -> predicate -> object."""

    id: str
    collection_id: str
    subject_type: str
    subject_id: str
    predicate: str
    object_type: str
    object_id: str
    assertion_level: AssertionLevel = AssertionLevel.MENTIONED
    start_time: datetime | None = None
    end_time: datetime | None = None
    confidence: float = 0.0
    status: ReviewState = ReviewState.PROPOSED
    provenance: Provenance | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClaimRelation:
    """An explicit, provenance-carrying edge between two claims."""

    id: str
    collection_id: str
    subject_claim_id: str
    relation: ClaimRelationType
    object_claim_id: str
    confidence: float = 0.0
    status: ReviewState = ReviewState.PROPOSED
    provenance: Provenance | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)
    note: str | None = None


@dataclass(slots=True)
class Revision:
    """A correction that supersedes a prior assessment without erasing it."""

    id: str
    collection_id: str
    target_kind: str
    target_id: str
    supersedes_revision_id: str | None
    reason: str
    actor: str
    actor_kind: str = "human"
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
