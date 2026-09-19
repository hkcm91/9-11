"""The collection abstraction.

A *collection* is one historical corpus — a set of attacks, a document
release, a conflict archive — expressed as configuration plus a small amount of
code. The engine talks to a collection through this interface and never through
a hardcoded source identifier.

``BaseCollection`` supplies generic behaviour for everything, so a new
collection can be created from a YAML ontology and a YAML source registry with
no Python at all. Collections override only what is genuinely theirs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence, runtime_checkable

from historical_engine import work_rules
from historical_engine.models.graph import CollectionRecord
from historical_engine.ontology import Ontology, default_ontology, load_ontology
from historical_engine.quality import DEFAULT_SOURCE_VALUE
from historical_engine.records import SourceRecord
from historical_engine.roles import RoleRule, classify, generic_role_rules
from historical_engine.routing import ConfidenceRouter, RoutingPolicy
from historical_engine.sources import SourceRegistryEntry, enabled_sources, load_source_registry


@dataclass(slots=True)
class CollectionHooks:
    """Optional collection-supplied behaviour.

    Every hook is optional and defaults to "do nothing", so a collection opts
    in to exactly the extension points it needs. Hooks derive *claims* and
    *proposals*; none of them may write a verified record.
    """

    #: Deterministic derivations: record -> claims. Keyed by claim family.
    derive_temporal: Callable[[SourceRecord], Iterable[Any]] | None = None
    derive_spatial: Callable[[SourceRecord], Iterable[Any]] | None = None
    derive_entities: Callable[[SourceRecord], Iterable[Any]] | None = None
    #: Optional deterministic graph derivation: record -> Entity/Event/Relationship objects.
    derive_graph: Callable[[SourceRecord], Iterable[Any]] | None = None
    #: True when a deterministic time claim already exists for this record, so
    #: the work queue should not raise a research task for it.
    has_deterministic_time: Callable[[SourceRecord], bool] | None = None
    #: Extra prioritisation reasons surfaced to researchers.
    priority_reasons: Callable[[SourceRecord], Iterable[str]] | None = None


@runtime_checkable
class Collection(Protocol):
    """What the engine needs from a collection."""

    id: str
    name: str
    description: str

    @property
    def ontology(self) -> Ontology: ...

    def sources(self, *, enabled_only: bool = True) -> list[SourceRegistryEntry]: ...

    def role_rules(self) -> Sequence[RoleRule]: ...

    def classify_record(self, record: SourceRecord) -> str: ...

    def task_applies(self, record: SourceRecord, task_type: str, role: str) -> bool: ...

    def task_priority_multiplier(self, task_type: str, role: str) -> float: ...

    def expected_claim_kind(self, task_type: str, role: str) -> str | None: ...

    def task_instructions(self, task_type: str, role: str) -> str: ...

    def requires_human_review(self, *, record: SourceRecord, task_type: str, role: str) -> bool: ...

    def source_value(self, source_id: str) -> float: ...

    def routing_policy(self, task_type: str) -> RoutingPolicy: ...

    @property
    def hooks(self) -> CollectionHooks: ...


# --- generic defaults --------------------------------------------------------


@dataclass
class BaseCollection:
    """Generic collection. Configuration-driven, no domain assumptions."""

    id: str
    name: str
    description: str = ""
    ontology_path: Path | str | None = None
    sources_path: Path | str | None = None
    source_values: dict[str, float] = field(default_factory=dict)
    default_source_value: float = DEFAULT_SOURCE_VALUE
    router: ConfidenceRouter = field(default_factory=ConfidenceRouter)
    hooks: CollectionHooks = field(default_factory=CollectionHooks)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _ontology: Ontology | None = field(default=None, repr=False)
    _sources: list[SourceRegistryEntry] | None = field(default=None, repr=False)

    # -- identity ------------------------------------------------------------

    def record(self) -> CollectionRecord:
        return CollectionRecord(
            id=self.id,
            name=self.name,
            description=self.description,
            ontology_version=self.ontology.version,
            config_version=self.ontology.version,
            created_at=self.created_at,
        )

    @property
    def ontology(self) -> Ontology:
        if self._ontology is None:
            self._ontology = (
                load_ontology(self.ontology_path, collection_id=self.id)
                if self.ontology_path is not None
                else default_ontology(self.id)
            )
        return self._ontology

    # -- sources -------------------------------------------------------------

    def sources(self, *, enabled_only: bool = True) -> list[SourceRegistryEntry]:
        if self.sources_path is None:
            return []
        if enabled_only:
            return enabled_sources(self.sources_path)
        if self._sources is None:
            self._sources = load_source_registry(self.sources_path)
        return list(self._sources)

    def source_ids(self) -> set[str]:
        return {entry.id for entry in self.sources(enabled_only=False)}

    def source_value(self, source_id: str) -> float:
        return self.source_values.get(source_id, self.default_source_value)

    # -- record roles --------------------------------------------------------

    def role_rules(self) -> Sequence[RoleRule]:
        return generic_role_rules()

    def classify_record(self, record: SourceRecord) -> str:
        return classify(record, self.role_rules())

    # -- work-queue behaviour ------------------------------------------------

    def task_applies(self, record: SourceRecord, task_type: str, role: str) -> bool:
        return work_rules.task_applies(
            record,
            task_type,
            role,
            has_deterministic_time=self.hooks.has_deterministic_time,
        )

    def task_priority_multiplier(self, task_type: str, role: str) -> float:
        return work_rules.role_multiplier(task_type, role)

    def expected_claim_kind(self, task_type: str, role: str) -> str | None:
        return work_rules.expected_claim_kind(task_type, role)

    def task_instructions(self, task_type: str, role: str) -> str:
        return work_rules.instructions(task_type, role)

    def requires_human_review(self, *, record: SourceRecord, task_type: str, role: str) -> bool:
        return self.ontology.sensitive.requires_human_review(role=role, task_type=task_type)

    # -- AI routing ----------------------------------------------------------

    def routing_policy(self, task_type: str) -> RoutingPolicy:
        return self.router.policy_for(task_type)
