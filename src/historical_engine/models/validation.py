"""Guard rails for graph writes.

These functions encode the project's non-negotiable safeguards:

* a derived statement cites evidence and carries confidence, method and actor;
* a machine actor may never hand itself ``reviewed``/``verified`` status or an
  ``established``/``corroborated`` assertion level;
* semantic distinctions between "mentioned" and "established" cannot be
  collapsed into an unlabelled edge.
"""

from __future__ import annotations

from typing import Iterable

from historical_engine.models.graph import (
    HUMAN_ONLY_ASSERTION_LEVELS,
    HUMAN_ONLY_STATES,
    AssertionLevel,
    ClaimRelation,
    ClaimRelationType,
    Entity,
    Event,
    Relationship,
    ReviewState,
)


class GraphValidationError(ValueError):
    """Raised when a graph write would violate a provenance safeguard."""


def _check_confidence(value: float, label: str) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise GraphValidationError(f"{label}.confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise GraphValidationError(f"{label}.confidence must be between 0 and 1")
    return confidence


def _check_machine_status(status: ReviewState | str, actor_kind: str, label: str) -> None:
    if actor_kind == "human":
        return
    if str(status) in HUMAN_ONLY_STATES:
        raise GraphValidationError(
            f"{label}: a {actor_kind} actor may not assign review status '{status}'"
        )


def validate_relationship(
    relationship: Relationship,
    *,
    actor_kind: str = "machine",
    allowed_predicates: Iterable[str] | None = None,
    allowed_entity_types: Iterable[str] | None = None,
) -> Relationship:
    """Validate a graph edge before it is persisted."""

    if not relationship.predicate.strip():
        raise GraphValidationError("relationship.predicate is required")
    if not relationship.subject_id.strip() or not relationship.object_id.strip():
        raise GraphValidationError("relationship endpoints are required")
    if allowed_predicates is not None and relationship.predicate not in set(allowed_predicates):
        raise GraphValidationError(
            f"predicate '{relationship.predicate}' is not in the collection ontology"
        )
    if allowed_entity_types is not None:
        known = set(allowed_entity_types)
        for label, value in (
            ("subject_type", relationship.subject_type),
            ("object_type", relationship.object_type),
        ):
            if value not in known:
                raise GraphValidationError(
                    f"{label} '{value}' is not in the collection ontology"
                )

    relationship.confidence = _check_confidence(relationship.confidence, "relationship")
    _check_machine_status(relationship.status, actor_kind, "relationship")

    level = AssertionLevel(relationship.assertion_level)
    if actor_kind != "human" and str(level) in HUMAN_ONLY_ASSERTION_LEVELS:
        raise GraphValidationError(
            f"relationship: a {actor_kind} actor may not assert level '{level}'"
        )
    if relationship.provenance is None or not relationship.provenance.method.strip():
        raise GraphValidationError("relationship.provenance.method is required")
    if not relationship.evidence:
        raise GraphValidationError("relationship requires at least one evidence reference")
    if (
        relationship.start_time is not None
        and relationship.end_time is not None
        and relationship.end_time < relationship.start_time
    ):
        raise GraphValidationError("relationship end_time precedes start_time")
    return relationship


def validate_claim_relation(
    relation: ClaimRelation,
    *,
    actor_kind: str = "machine",
) -> ClaimRelation:
    """Validate a claim-to-claim reasoning edge."""

    if not relation.subject_claim_id.strip() or not relation.object_claim_id.strip():
        raise GraphValidationError("claim relation endpoints are required")
    if relation.subject_claim_id == relation.object_claim_id:
        raise GraphValidationError("a claim may not relate to itself")
    # Raises ValueError for an unknown relation, which is the intended failure.
    relation.relation = ClaimRelationType(relation.relation)
    relation.confidence = _check_confidence(relation.confidence, "claim_relation")
    _check_machine_status(relation.status, actor_kind, "claim_relation")
    if relation.provenance is None or not relation.provenance.method.strip():
        raise GraphValidationError("claim_relation.provenance.method is required")
    if not relation.evidence:
        raise GraphValidationError("claim_relation requires at least one evidence reference")
    return relation


def validate_entity(entity: Entity, *, actor_kind: str = "machine",
                    allowed_entity_types: Iterable[str] | None = None) -> Entity:
    if not entity.canonical_name.strip():
        raise GraphValidationError("entity.canonical_name is required")
    if allowed_entity_types is not None and entity.entity_type not in set(allowed_entity_types):
        raise GraphValidationError(
            f"entity_type '{entity.entity_type}' is not in the collection ontology"
        )
    entity.confidence = _check_confidence(entity.confidence, "entity")
    _check_machine_status(entity.status, actor_kind, "entity")
    return entity


def validate_event(event: Event, *, actor_kind: str = "machine",
                   allowed_event_types: Iterable[str] | None = None) -> Event:
    if not event.name.strip():
        raise GraphValidationError("event.name is required")
    if allowed_event_types is not None and event.event_type not in set(allowed_event_types):
        raise GraphValidationError(
            f"event_type '{event.event_type}' is not in the collection ontology"
        )
    event.confidence = _check_confidence(event.confidence, "event")
    _check_machine_status(event.status, actor_kind, "event")
    if (
        event.start_time is not None
        and event.end_time is not None
        and event.end_time < event.start_time
    ):
        raise GraphValidationError("event end_time precedes start_time")
    return event
