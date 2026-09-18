"""The September 11, 2001 collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from historical_engine.collection import BaseCollection
from historical_engine.roles import RoleRule
from historical_engine.routing import ConfidenceRouter, RoutingPolicy
from evidence_collections.september11 import rules
from evidence_collections.september11.hooks import build_hooks

COLLECTION_ID = "september11"
PACKAGE_DIR = Path(__file__).resolve().parent
ONTOLOGY_PATH = PACKAGE_DIR / "ontology.yaml"
SOURCES_PATH = PACKAGE_DIR / "sources.yaml"

DESCRIPTION = (
    "Provenance-first archive and research pipeline for the September 11, 2001 "
    "attacks: custodial source registration, metadata-first ingestion, "
    "evidence-backed temporal/spatial/entity claims, and reviewed agent proposals."
)

#: Routing thresholds for this corpus. Deliberately conservative: anything
#: touching a named person goes to a human regardless of model confidence.
ROUTER = ConfidenceRouter(
    default_policy=RoutingPolicy(accept_at=0.92, escalate_at=0.65, weak_at=0.35),
    policies={
        "resolve_time": RoutingPolicy(accept_at=0.90, escalate_at=0.60, weak_at=0.30),
        "resolve_location": RoutingPolicy(accept_at=0.94, escalate_at=0.70, weak_at=0.40),
        "resolve_creator": RoutingPolicy(accept_at=0.92, escalate_at=0.65, weak_at=0.35),
        "entity_resolution": RoutingPolicy(
            accept_at=1.0,
            escalate_at=0.60,
            weak_at=0.30,
            force_human_review=True,
            note="Resolving a mention to a named individual in this corpus is always a human decision.",
        ),
        "classify_media": RoutingPolicy(accept_at=0.85, escalate_at=0.55, weak_at=0.25),
    },
)


@dataclass
class September11Collection(BaseCollection):
    id: str = COLLECTION_ID
    name: str = "September 11, 2001"
    description: str = DESCRIPTION
    ontology_path: Path | str | None = ONTOLOGY_PATH
    sources_path: Path | str | None = SOURCES_PATH
    source_values: dict[str, float] = field(default_factory=lambda: dict(rules.SOURCE_VALUE))
    router: ConfidenceRouter = field(default_factory=lambda: ROUTER)

    def __post_init__(self) -> None:
        if self.hooks.derive_temporal is None:
            self.hooks = build_hooks()

    def role_rules(self) -> Sequence[RoleRule]:
        return rules.role_rules()


def build_collection() -> September11Collection:
    return September11Collection()
