"""Collection ontologies.

An ontology is the declared vocabulary of one collection: which entity types,
event types, relationship predicates, record roles and assertion levels the
collection admits, plus its sensitive-content policy. It is data, loaded from
YAML, so that adding a collection does not require touching engine code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from historical_engine.models.graph import AssertionLevel, EntityType
from historical_engine.roles import GENERIC_ROLES

DEFAULT_ENTITY_TYPES: tuple[str, ...] = tuple(str(value) for value in EntityType)
DEFAULT_ASSERTION_LEVELS: tuple[str, ...] = tuple(str(value) for value in AssertionLevel)
DEFAULT_EVENT_TYPES: tuple[str, ...] = (
    "episode",
    "incident",
    "attack",
    "operation",
    "proceeding",
    "publication",
    "other",
)
DEFAULT_PREDICATES: tuple[str, ...] = (
    "depicts",
    "describes",
    "present_at",
    "occurred_at",
    "associated_with",
    "created_by",
    "custodian_of",
    "supports",
    "contradicts",
    "part_of",
    "located_in",
)


class OntologyError(ValueError):
    """Raised when an ontology document is malformed."""


@dataclass(frozen=True, slots=True)
class SensitivePolicy:
    """How carefully a collection must treat inference about people and harm."""

    force_human_review: bool = False
    force_human_review_roles: frozenset[str] = field(default_factory=frozenset)
    force_human_review_tasks: frozenset[str] = field(default_factory=frozenset)
    prohibited_inferences: frozenset[str] = field(default_factory=frozenset)
    note: str | None = None

    def requires_human_review(self, *, role: str | None = None, task_type: str | None = None) -> bool:
        if self.force_human_review:
            return True
        if role is not None and role in self.force_human_review_roles:
            return True
        if task_type is not None and task_type in self.force_human_review_tasks:
            return True
        return False


@dataclass(frozen=True, slots=True)
class Ontology:
    """The declared domain vocabulary of one collection."""

    collection_id: str
    version: str = "0"
    entity_types: frozenset[str] = frozenset(DEFAULT_ENTITY_TYPES)
    event_types: frozenset[str] = frozenset(DEFAULT_EVENT_TYPES)
    predicates: frozenset[str] = frozenset(DEFAULT_PREDICATES)
    record_roles: frozenset[str] = frozenset(GENERIC_ROLES)
    assertion_levels: frozenset[str] = frozenset(DEFAULT_ASSERTION_LEVELS)
    sensitive: SensitivePolicy = SensitivePolicy()
    extras: dict[str, Any] = field(default_factory=dict)

    def check_entity_type(self, value: str) -> str:
        if value not in self.entity_types:
            raise OntologyError(f"entity type '{value}' is not declared by {self.collection_id}")
        return value

    def check_event_type(self, value: str) -> str:
        if value not in self.event_types:
            raise OntologyError(f"event type '{value}' is not declared by {self.collection_id}")
        return value

    def check_predicate(self, value: str) -> str:
        if value not in self.predicates:
            raise OntologyError(f"predicate '{value}' is not declared by {self.collection_id}")
        return value


def _string_set(payload: dict[str, Any], key: str, defaults: Iterable[str]) -> frozenset[str]:
    """Read a vocabulary list.

    ``<key>`` replaces the engine defaults outright; ``extra_<key>`` adds to
    them. Extending is the common case, so collections rarely need to restate
    the generic vocabulary.
    """

    values = payload.get(key)
    extra = payload.get(f"extra_{key}") or []
    if not isinstance(extra, list):
        raise OntologyError(f"extra_{key} must be a list")
    if values is None:
        base = list(defaults)
    elif isinstance(values, list):
        base = [str(value) for value in values]
    else:
        raise OntologyError(f"{key} must be a list")
    return frozenset(base + [str(value) for value in extra])


def _sensitive_policy(payload: Any) -> SensitivePolicy:
    if payload is None:
        return SensitivePolicy()
    if not isinstance(payload, dict):
        raise OntologyError("sensitive must be a mapping")
    return SensitivePolicy(
        force_human_review=bool(payload.get("force_human_review", False)),
        force_human_review_roles=frozenset(
            str(value) for value in payload.get("force_human_review_roles") or []
        ),
        force_human_review_tasks=frozenset(
            str(value) for value in payload.get("force_human_review_tasks") or []
        ),
        prohibited_inferences=frozenset(
            str(value) for value in payload.get("prohibited_inferences") or []
        ),
        note=payload.get("note"),
    )


_KNOWN_KEYS = {
    "collection_id",
    "version",
    "entity_types",
    "extra_entity_types",
    "event_types",
    "extra_event_types",
    "predicates",
    "extra_predicates",
    "record_roles",
    "extra_record_roles",
    "assertion_levels",
    "extra_assertion_levels",
    "sensitive",
}


def ontology_from_dict(payload: dict[str, Any], *, collection_id: str | None = None) -> Ontology:
    if not isinstance(payload, dict):
        raise OntologyError("ontology document must be a mapping")
    resolved_id = str(payload.get("collection_id") or collection_id or "").strip()
    if not resolved_id:
        raise OntologyError("ontology requires a collection_id")
    return Ontology(
        collection_id=resolved_id,
        version=str(payload.get("version", "0")),
        entity_types=_string_set(payload, "entity_types", DEFAULT_ENTITY_TYPES),
        event_types=_string_set(payload, "event_types", DEFAULT_EVENT_TYPES),
        predicates=_string_set(payload, "predicates", DEFAULT_PREDICATES),
        record_roles=_string_set(payload, "record_roles", GENERIC_ROLES),
        assertion_levels=_string_set(payload, "assertion_levels", DEFAULT_ASSERTION_LEVELS),
        sensitive=_sensitive_policy(payload.get("sensitive")),
        extras={key: value for key, value in payload.items() if key not in _KNOWN_KEYS},
    )


def load_ontology(path: str | Path, *, collection_id: str | None = None) -> Ontology:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ontology_from_dict(document, collection_id=collection_id)


def default_ontology(collection_id: str) -> Ontology:
    return Ontology(collection_id=collection_id)
