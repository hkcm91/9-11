from datetime import datetime, timedelta, timezone
from pathlib import Path

from archive.store import ArchiveStore
from historical_engine.ai.questions import DecisionQuestion
from historical_engine.models.graph import Entity, Event, EvidenceItem, Provenance, ReviewState
from historical_engine.resolution_candidates import (
    build_resolution_candidates,
    entity_resolution_candidates,
    event_resolution_candidates,
)


def _evidence(source_id: str) -> list[EvidenceItem]:
    return [EvidenceItem(source_item_id=source_id)]


def _provenance() -> Provenance:
    return Provenance(method="test-fixture")


def test_entity_resolution_candidates_are_review_questions_not_merges(tmp_path: Path) -> None:
    database = tmp_path / "graph.sqlite"
    with ArchiveStore(database) as store:
        store.put_entity(
            Entity(
                id="entity:1",
                collection_id="wikileaks",
                entity_type="diplomatic_mission",
                canonical_name="U.S. Embassy Cairo",
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("cable:1"),
            )
        )
        store.put_entity(
            Entity(
                id="entity:2",
                collection_id="wikileaks",
                entity_type="diplomatic_mission",
                canonical_name="US Embassy Cairo",
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("cable:2"),
            )
        )
        store.put_entity(
            Entity(
                id="entity:3",
                collection_id="wikileaks",
                entity_type="diplomatic_mission",
                canonical_name="Embassy London",
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("cable:3"),
            )
        )

        candidates = entity_resolution_candidates(
            store.connection,
            collection_id="wikileaks",
            minimum_similarity=0.70,
        )

    assert len(candidates) == 1
    request = candidates[0]
    assert request.question == DecisionQuestion.SAME_ENTITY
    assert {request.subject_id, request.object_id} == {"entity:1", "entity:2"}
    assert request.task_type == "entity_resolution"
    assert request.evidence_ids == ["cable:1", "cable:2"]
    assert request.context["candidate_score"] >= 0.70


def test_event_candidates_require_time_and_structural_similarity(tmp_path: Path) -> None:
    database = tmp_path / "graph.sqlite"
    start = datetime(2004, 7, 11, 17, 29, tzinfo=timezone.utc)

    with ArchiveStore(database) as store:
        for event in (
            Event(
                id="event:1",
                collection_id="wikileaks",
                name="CACHE FOUND IN BAGHDAD",
                event_type="sigact",
                start_time=start,
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("warlog:1"),
                attributes={"category": "Cache Found/Cleared", "type": "Friendly Action"},
            ),
            Event(
                id="event:2",
                collection_id="wikileaks",
                name="BAGHDAD CACHE INVESTIGATION",
                event_type="sigact",
                start_time=start + timedelta(hours=1),
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("warlog:2"),
                attributes={"category": "Cache Found/Cleared", "type": "Friendly Action"},
            ),
            Event(
                id="event:3",
                collection_id="wikileaks",
                name="UNRELATED INCIDENT",
                event_type="sigact",
                start_time=start + timedelta(days=3),
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("warlog:3"),
                attributes={"category": "Direct Fire", "type": "Enemy Action"},
            ),
        ):
            store.put_event(event)

        candidates = event_resolution_candidates(
            store.connection,
            collection_id="wikileaks",
            max_time_delta_hours=12,
        )

    assert len(candidates) == 1
    request = candidates[0]
    assert request.question == DecisionQuestion.SAME_EVENT
    assert {request.subject_id, request.object_id} == {"event:1", "event:2"}
    assert request.evidence_ids == ["warlog:1", "warlog:2"]
    assert request.context["shared_category"] is True
    assert request.context["shared_type"] is True


def test_build_resolution_candidates_combines_both_queues(tmp_path: Path) -> None:
    database = tmp_path / "graph.sqlite"
    start = datetime(2004, 7, 11, 17, 29, tzinfo=timezone.utc)

    with ArchiveStore(database) as store:
        store.put_entity(
            Entity(
                id="entity:1",
                collection_id="wikileaks",
                entity_type="organization",
                canonical_name="State Department",
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("cable:1"),
            )
        )
        store.put_entity(
            Entity(
                id="entity:2",
                collection_id="wikileaks",
                entity_type="organization",
                canonical_name="State Department.",
                status=ReviewState.PROPOSED,
                confidence=1.0,
                provenance=_provenance(),
                evidence=_evidence("cable:2"),
            )
        )
        for event_id, source_id, minutes in (
            ("event:1", "warlog:1", 0),
            ("event:2", "warlog:2", 30),
        ):
            store.put_event(
                Event(
                    id=event_id,
                    collection_id="wikileaks",
                    name="IED ATTACK BAGHDAD",
                    event_type="sigact",
                    start_time=start + timedelta(minutes=minutes),
                    status=ReviewState.PROPOSED,
                    confidence=1.0,
                    provenance=_provenance(),
                    evidence=_evidence(source_id),
                    attributes={"category": "IED Explosion", "type": "Enemy Action"},
                )
            )

    candidates = build_resolution_candidates(database, collection_id="wikileaks")

    assert {request.question for request in candidates} == {
        DecisionQuestion.SAME_ENTITY,
        DecisionQuestion.SAME_EVENT,
    }
    assert all(request.collection_id == "wikileaks" for request in candidates)
