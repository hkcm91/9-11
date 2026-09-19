"""WikiLeaks releases as a collection on the Historical Evidence Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from historical_engine.collection import BaseCollection, CollectionHooks
from historical_engine.records import SourceRecord
from historical_engine.roles import RoleRule
from historical_engine.routing import ConfidenceRouter, RoutingPolicy

from evidence_collections.wikileaks import rules
from evidence_collections.wikileaks.graph import derive_graph

COLLECTION_ID = "wikileaks"
PACKAGE_DIR = Path(__file__).resolve().parent
ONTOLOGY_PATH = PACKAGE_DIR / "ontology.yaml"
SOURCES_PATH = PACKAGE_DIR / "sources.yaml"

ROUTER = ConfidenceRouter(
    default_policy=RoutingPolicy(accept_at=0.95, escalate_at=0.70, weak_at=0.40),
    policies={
        "entity_resolution": RoutingPolicy(
            accept_at=1.0,
            escalate_at=0.65,
            weak_at=0.35,
            force_human_review=True,
            note="Named-person entity resolution in leaked/public-record corpora always requires human review.",
        ),
        "relationship_link": RoutingPolicy(
            accept_at=1.0,
            escalate_at=0.70,
            weak_at=0.40,
            force_human_review=True,
            note="A machine-proposed relationship must not imply wrongdoing or become established without review.",
        ),
        "claim_relation": RoutingPolicy(
            accept_at=1.0,
            escalate_at=0.70,
            weak_at=0.40,
            force_human_review=True,
            note="Corroboration/contradiction between consequential claims requires review.",
        ),
    },
)


@dataclass
class WikiLeaksCollection(BaseCollection):
    id: str = COLLECTION_ID
    name: str = "WikiLeaks Public Releases"
    description: str = (
        "Provenance-first research collection for publicly released WikiLeaks corpora, "
        "including diplomatic cables and structured war-diary event records."
    )
    ontology_path: Path | str | None = ONTOLOGY_PATH
    sources_path: Path | str | None = SOURCES_PATH
    source_values: dict[str, float] = field(default_factory=lambda: dict(rules.SOURCE_VALUE))
    router: ConfidenceRouter = field(default_factory=lambda: ROUTER)
    hooks: CollectionHooks = field(
        default_factory=lambda: CollectionHooks(
            priority_reasons=rules.priority_reasons,
            derive_graph=derive_graph,
        )
    )

    def role_rules(self) -> Sequence[RoleRule]:
        return rules.role_rules()

    def expected_claim_kind(self, task_type: str, role: str) -> str | None:
        if role == rules.ROLE_EVENT_RECORD:
            if task_type == "resolve_time":
                return "event_time"
            if task_type == "resolve_location":
                return "event_location"
        return super().expected_claim_kind(task_type, role)

    def task_instructions(self, task_type: str, role: str) -> str:
        if role == rules.ROLE_EVENT_RECORD and task_type == "resolve_time":
            return (
                "Resolve the event time represented by this source record. Preserve the source timestamp, "
                "distinguish event time from report/update time, cite the record, state uncertainty, and do not "
                "mark the result verified."
            )
        if role == rules.ROLE_EVENT_RECORD and task_type == "resolve_location":
            return (
                "Resolve the event location from explicit source fields such as MGRS or a named place. Preserve "
                "the original grid/location notation, state conversion uncertainty, cite the source record, and "
                "do not infer a precise point from a broad region label alone."
            )
        if role == rules.ROLE_EVENT_RECORD and task_type == "resolve_creator":
            return (
                "Resolve the reporting/originating unit or organization. Distinguish the reporting unit from "
                "entities merely described in the event narrative and preserve the original source value."
            )
        return super().task_instructions(task_type, role)

    def task_priority_multiplier(self, task_type: str, role: str) -> float:
        if role == rules.ROLE_EVENT_RECORD and task_type in {"resolve_time", "resolve_location"}:
            return 1.0
        return super().task_priority_multiplier(task_type, role)

    def requires_human_review(self, *, record: SourceRecord, task_type: str, role: str) -> bool:
        if role == rules.ROLE_EVENT_RECORD and task_type in {
            "resolve_time",
            "resolve_location",
            "resolve_creator",
        }:
            return True
        return super().requires_human_review(record=record, task_type=task_type, role=role)


def build_collection() -> WikiLeaksCollection:
    return WikiLeaksCollection()
