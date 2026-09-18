"""Evidence graph: relationships, claim-to-claim edges, and their guard rails."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from archive.store import ArchiveStore
from historical_engine.collection_registry import get_collection
from historical_engine.models import (
    AssertionLevel,
    ClaimRelation,
    ClaimRelationType,
    Entity,
    EntityAlias,
    EntityType,
    Event,
    EvidenceItem,
    GraphValidationError,
    Provenance,
    Relationship,
    ReviewState,
    Revision,
    validate_claim_relation,
    validate_relationship,
)


def _prov() -> Provenance:
    return Provenance(method="test", created_by_agent="test-agent", agent_version="1")


def _relationship(**kwargs) -> Relationship:
    payload = {
        "id": "rel:1",
        "collection_id": "demo_history",
        "subject_type": "record",
        "subject_id": "item:a",
        "predicate": "depicts",
        "object_type": "event",
        "object_id": "event:1",
        "assertion_level": AssertionLevel.MENTIONED,
        "confidence": 0.5,
        "provenance": _prov(),
        "evidence": [EvidenceItem(source_item_id="item:a")],
    }
    payload.update(kwargs)
    return Relationship(**payload)


def _claim_relation(**kwargs) -> ClaimRelation:
    payload = {
        "id": "claimrel:1",
        "collection_id": "demo_history",
        "subject_claim_id": "claim:a",
        "relation": ClaimRelationType.SUPPORTS,
        "object_claim_id": "claim:b",
        "confidence": 0.7,
        "provenance": _prov(),
        "evidence": [EvidenceItem(source_item_id="item:a")],
    }
    payload.update(kwargs)
    return ClaimRelation(**payload)


# --- relationship validation -------------------------------------------------


def test_a_relationship_needs_evidence_method_and_endpoints() -> None:
    validate_relationship(_relationship())
    with pytest.raises(GraphValidationError):
        validate_relationship(_relationship(evidence=[]))
    with pytest.raises(GraphValidationError):
        validate_relationship(_relationship(provenance=None))
    with pytest.raises(GraphValidationError):
        validate_relationship(_relationship(object_id="  "))


def test_a_machine_may_not_assert_an_established_link() -> None:
    for level in (AssertionLevel.ESTABLISHED, AssertionLevel.CORROBORATED):
        with pytest.raises(GraphValidationError):
            validate_relationship(_relationship(assertion_level=level), actor_kind="machine")
        validate_relationship(_relationship(assertion_level=level), actor_kind="human")


def test_a_machine_may_not_assign_a_reviewed_status() -> None:
    for status in (ReviewState.REVIEWED, ReviewState.VERIFIED, ReviewState.REJECTED):
        with pytest.raises(GraphValidationError):
            validate_relationship(_relationship(status=status), actor_kind="machine")


def test_assertion_levels_stay_distinct() -> None:
    """"Mentioned" and "established" are not interchangeable."""

    mentioned = validate_relationship(_relationship(assertion_level=AssertionLevel.MENTIONED))
    alleged = validate_relationship(
        _relationship(id="rel:2", assertion_level=AssertionLevel.ALLEGED)
    )
    assert mentioned.assertion_level != alleged.assertion_level


def test_ontology_constrains_predicates_and_types() -> None:
    ontology = get_collection("demo_history").ontology
    validate_relationship(_relationship(), allowed_predicates=ontology.predicates)
    with pytest.raises(GraphValidationError):
        validate_relationship(
            _relationship(predicate="vibes_with"), allowed_predicates=ontology.predicates
        )


# --- claim-to-claim ----------------------------------------------------------


@pytest.mark.parametrize(
    "relation",
    [
        ClaimRelationType.SUPPORTS,
        ClaimRelationType.CONTRADICTS,
        ClaimRelationType.PARTIALLY_CORROBORATES,
        ClaimRelationType.SUPERSEDES,
    ],
)
def test_claim_reasoning_edges_are_explicit_and_evidenced(relation) -> None:
    validated = validate_claim_relation(_claim_relation(relation=relation))
    assert validated.relation == relation
    assert validated.evidence


def test_a_claim_may_not_relate_to_itself() -> None:
    with pytest.raises(GraphValidationError):
        validate_claim_relation(_claim_relation(object_claim_id="claim:a"))


def test_claim_relations_need_evidence_and_provenance() -> None:
    with pytest.raises(GraphValidationError):
        validate_claim_relation(_claim_relation(evidence=[]))
    with pytest.raises(GraphValidationError):
        validate_claim_relation(_claim_relation(provenance=None))


def test_a_machine_may_not_mark_a_claim_relation_verified() -> None:
    with pytest.raises(GraphValidationError):
        validate_claim_relation(_claim_relation(status=ReviewState.VERIFIED))


# --- persistence -------------------------------------------------------------


def test_graph_writes_persist_alongside_untouched_raw_records(tmp_path: Path) -> None:
    ontology = get_collection("demo_history").ontology
    with ArchiveStore(tmp_path / "graph.sqlite") as store:
        store.put_entity(
            Entity(
                id="entity:1",
                collection_id="demo_history",
                entity_type=str(EntityType.PERSON),
                canonical_name="Ada Hollis",
                confidence=0.9,
                provenance=_prov(),
            ),
            allowed_entity_types=ontology.entity_types,
        )
        store.put_entity_alias(
            EntityAlias(entity_id="entity:1", alias="A. Hollis", confidence=0.8, provenance=_prov())
        )
        store.put_event(
            Event(
                id="event:1",
                collection_id="demo_history",
                name="A fire",
                event_type="fire",
                start_time=datetime(1898, 4, 9, tzinfo=timezone.utc),
                confidence=0.6,
                provenance=_prov(),
            ),
            allowed_event_types=ontology.event_types,
        )
        store.put_relationship(_relationship(), allowed_predicates=ontology.predicates)
        store.put_claim_relation(_claim_relation())
        store.put_revision(
            Revision(
                id="rev:1",
                collection_id="demo_history",
                target_kind="relationship",
                target_id="rel:1",
                supersedes_revision_id=None,
                reason="initial assessment",
                actor="reviewer",
            )
        )
        stats = store.stats()

    assert stats["entities"] == 1
    assert stats["entity_aliases"] == 1
    assert stats["events"] == 1
    assert stats["relationships"] == 1
    assert stats["claim_relations"] == 1
    assert stats["revisions"] == 1
    # Graph writes must not invent source records.
    assert stats["source_records"] == 0


def test_a_machine_write_is_refused_at_the_store_boundary(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "graph.sqlite") as store:
        with pytest.raises(GraphValidationError):
            store.put_relationship(_relationship(status=ReviewState.VERIFIED))
        assert store.stats()["relationships"] == 0


def test_revisions_supersede_rather_than_erase(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "graph.sqlite") as store:
        first = store.put_revision(
            Revision(
                id="rev:1",
                collection_id="demo_history",
                target_kind="relationship",
                target_id="rel:1",
                supersedes_revision_id=None,
                reason="initial",
                actor="reviewer",
            )
        )
        store.put_revision(
            Revision(
                id="rev:2",
                collection_id="demo_history",
                target_kind="relationship",
                target_id="rel:1",
                supersedes_revision_id=first,
                reason="corrected after new evidence",
                actor="reviewer",
            )
        )
        rows = store.connection.execute(
            "SELECT revision_id, supersedes_revision_id FROM revisions ORDER BY revision_id"
        ).fetchall()

    assert [row["revision_id"] for row in rows] == ["rev:1", "rev:2"]
    assert rows[1]["supersedes_revision_id"] == "rev:1"


def test_evidence_items_round_trip_the_existing_embedded_shape() -> None:
    payload = {"source_item_id": "item:a", "relationship": "supports", "weight": 0.5}
    assert EvidenceItem.from_ref(payload).to_ref() == payload
