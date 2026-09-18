"""A deliberately tiny synthetic collection.

`demo_history` exists for one reason: to prove that the engine runs a second,
unrelated corpus with no changes to core code. The content is fictional — a
mill fire in an invented borough — so that nothing here can be mistaken for a
historical assertion.

It exercises the same pipeline the September 11 collection uses: source
registry, record roles, enrichment priority, work queue, deterministic claims,
entities, an event, a supporting relationship and a contradictory claim pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from historical_engine.collection import BaseCollection, CollectionHooks
from historical_engine.models.graph import (
    AssertionLevel,
    ClaimRelation,
    ClaimRelationType,
    Entity,
    EntityType,
    Event,
    EvidenceItem,
    Provenance,
    Relationship,
    ReviewState,
)
from historical_engine.routing import ConfidenceRouter, RoutingPolicy
from evidence_collections.demo_history import derivations

COLLECTION_ID = "demo_history"
PACKAGE_DIR = Path(__file__).resolve().parent
ONTOLOGY_PATH = PACKAGE_DIR / "ontology.yaml"
SOURCES_PATH = PACKAGE_DIR / "sources.yaml"
RECORDS_PATH = PACKAGE_DIR / "fixtures" / "records.jsonl"

DOCUMENT_ID = "demo:document:inspector-report"
TESTIMONY_ID = "demo:testimony:hollis-interview"
PHOTO_ID = "demo:photo:mill-facade"

ENTITY_PERSON_ID = "demo:entity:ada-hollis"
ENTITY_ORG_ID = "demo:entity:riverbridge-mill-company"
EVENT_ID = "demo:event:riverbridge-mill-fire"

ROUTER = ConfidenceRouter(
    default_policy=RoutingPolicy(accept_at=0.85, escalate_at=0.55, weak_at=0.25),
    policies={
        "resolve_creator": RoutingPolicy(
            accept_at=0.90,
            escalate_at=0.60,
            weak_at=0.30,
            force_human_review=True,
            note="Attribution in this fixture corpus is always a human decision.",
        ),
    },
)


@dataclass
class DemoHistoryCollection(BaseCollection):
    id: str = COLLECTION_ID
    name: str = "Riverbridge demo history (synthetic)"
    description: str = (
        "A tiny synthetic corpus used to validate that the engine is genuinely "
        "collection-agnostic. Not real history."
    )
    ontology_path: Path | str | None = ONTOLOGY_PATH
    sources_path: Path | str | None = SOURCES_PATH
    source_values: dict[str, float] = field(
        default_factory=lambda: {
            "demo-borough-record-office": 0.90,
            "demo-oral-history-project": 0.75,
            "demo-photo-collection": 0.60,
        }
    )
    router: ConfidenceRouter = field(default_factory=lambda: ROUTER)

    def __post_init__(self) -> None:
        if self.hooks.derive_temporal is None:
            self.hooks = CollectionHooks(
                derive_temporal=derivations.derive_temporal,
                derive_entities=derivations.derive_entities,
            )


def build_collection() -> DemoHistoryCollection:
    return DemoHistoryCollection()


# --- graph fixtures ----------------------------------------------------------

_PROV = Provenance(
    method="demo_fixture",
    created_by_agent="demo-fixture-builder",
    agent_version="1",
    note="Synthetic fixture supplied with the collection, not an inference.",
)


def demo_entities() -> list[Entity]:
    return [
        Entity(
            id=ENTITY_PERSON_ID,
            collection_id=COLLECTION_ID,
            entity_type=str(EntityType.PERSON),
            canonical_name="Ada Hollis",
            description="Interviewee in the Riverbridge Oral History Project.",
            status=ReviewState.PROPOSED,
            confidence=0.95,
            provenance=_PROV,
            evidence=[EvidenceItem(source_item_id=TESTIMONY_ID, relationship="interviewee_label")],
        ),
        Entity(
            id=ENTITY_ORG_ID,
            collection_id=COLLECTION_ID,
            entity_type=str(EntityType.ORGANIZATION),
            canonical_name="Riverbridge Mill Company",
            description="Operator of the mill named in the inspection report.",
            status=ReviewState.PROPOSED,
            confidence=0.90,
            provenance=_PROV,
            evidence=[EvidenceItem(source_item_id=DOCUMENT_ID, relationship="named_in_report")],
        ),
    ]


def demo_event() -> Event:
    return Event(
        id=EVENT_ID,
        collection_id=COLLECTION_ID,
        name="Riverbridge Mill fire",
        event_type="fire",
        description="Fire at the Riverbridge Mill, April 1898. Start time is disputed.",
        start_time=datetime(1898, 4, 9, 21, 30, tzinfo=timezone.utc),
        end_time=None,
        time_precision="hour",
        status=ReviewState.PROPOSED,
        confidence=0.70,
        provenance=_PROV,
        evidence=[
            EvidenceItem(source_item_id=DOCUMENT_ID, relationship="reported_in_inspection_report"),
        ],
    )


def demo_relationships() -> list[Relationship]:
    """One supporting relationship: the testimony describes the event."""

    return [
        Relationship(
            id="demo:rel:testimony-describes-fire",
            collection_id=COLLECTION_ID,
            subject_type="record",
            subject_id=TESTIMONY_ID,
            predicate="describes",
            object_type="event",
            object_id=EVENT_ID,
            assertion_level=AssertionLevel.WITNESSED,
            confidence=0.85,
            status=ReviewState.PROPOSED,
            provenance=_PROV,
            evidence=[
                EvidenceItem(
                    source_item_id=TESTIMONY_ID,
                    relationship="narrative_describes_event",
                    note="The interviewee recounts the night of the fire.",
                    weight=0.85,
                )
            ],
        ),
        Relationship(
            id="demo:rel:photo-depicts-mill",
            collection_id=COLLECTION_ID,
            subject_type="record",
            subject_id=PHOTO_ID,
            predicate="depicts",
            object_type="entity",
            object_id=ENTITY_ORG_ID,
            assertion_level=AssertionLevel.MENTIONED,
            confidence=0.60,
            status=ReviewState.PROPOSED,
            provenance=_PROV,
            evidence=[
                EvidenceItem(
                    source_item_id=PHOTO_ID,
                    relationship="title_names_subject",
                    note="Title names the mill; the photograph is otherwise undated.",
                    weight=0.60,
                )
            ],
        ),
    ]


def demo_claim_relation(document_claim_id: str, testimony_claim_id: str) -> ClaimRelation:
    """The contradictory pair: the report and the testimony disagree on the start time.

    Neither claim is deleted or averaged. The disagreement is itself recorded.
    """

    return ClaimRelation(
        id="demo:claimrel:start-time-dispute",
        collection_id=COLLECTION_ID,
        subject_claim_id=testimony_claim_id,
        relation=ClaimRelationType.CONTRADICTS,
        object_claim_id=document_claim_id,
        confidence=0.80,
        status=ReviewState.PROPOSED,
        provenance=_PROV,
        note="Testimony places the fire's start about ninety minutes later than the report.",
        evidence=[
            EvidenceItem(source_item_id=TESTIMONY_ID, relationship="recounted_fire_start"),
            EvidenceItem(source_item_id=DOCUMENT_ID, relationship="reported_fire_start"),
        ],
    )
