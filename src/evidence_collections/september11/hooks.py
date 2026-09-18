"""September 11 collection hooks.

Hooks are the collection's contribution to generic engine stages. Every hook
here produces *claims* — separately represented, evidence-backed, confidence-
bearing, status ``proposed``. None of them writes to a source record and none
can mark anything verified.
"""

from __future__ import annotations

from typing import Iterable

from archive.models import (
    EntityReferenceClaim,
    SourceItem,
    SpatialClaim,
    TemporalClaim,
)
from historical_engine.collection import CollectionHooks
from evidence_collections.september11 import derivations
from evidence_collections.september11.heuristics import document_coverage_claim_from_title
from evidence_collections.september11.rules import priority_reasons


def derive_temporal(item: SourceItem) -> Iterable[TemporalClaim]:
    return derivations.derive_temporal_claims([item])


def derive_spatial(item: SourceItem) -> Iterable[SpatialClaim]:
    return derivations.derive_spatial_claims([item])


def derive_entities(item: SourceItem) -> Iterable[EntityReferenceClaim]:
    return derivations.derive_entity_claims([item])


def has_deterministic_time(item: SourceItem) -> bool:
    """True when a strict title parser already resolved this document's coverage.

    Only FDNY "Incident Action Plan: m/d/yy - m/d/yy" titles qualify. The title
    stays the evidence; the interval is a separate claim.
    """

    return document_coverage_claim_from_title(item) is not None


def build_hooks() -> CollectionHooks:
    return CollectionHooks(
        derive_temporal=derive_temporal,
        derive_spatial=derive_spatial,
        derive_entities=derive_entities,
        has_deterministic_time=has_deterministic_time,
        priority_reasons=priority_reasons,
    )
