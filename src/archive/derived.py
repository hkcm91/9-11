"""Backward-compatible deterministic-derivation facade.

The derivations themselves are collection knowledge (which source encodes a
broadcast interval, which folder name means "before 8:46 AM"), so they moved to
``evidence_collections.september11.derivations`` and are reached through the
active collection's hooks.

The contract is unchanged: these produce *claims* — separate from the source
record, evidence-backed, confidence-bearing, status ``proposed``. They never
write to a source record and never mark anything verified.
"""

from __future__ import annotations

from typing import Callable, Iterable, TypeVar

from archive.collections_compat import resolve_collection
from archive.models import EntityReferenceClaim, SpatialClaim, TemporalClaim
from historical_engine.collection import Collection
from historical_engine.records import SourceRecord

# Serialization is shape-driven, not collection-driven, so it stays importable
# from here unchanged.
from evidence_collections.september11.derivations import (  # noqa: F401
    serialize_entity_claim,
    serialize_spatial_claim,
    serialize_temporal_claim,
)

__all__ = [
    "derive_entity_claims",
    "derive_spatial_claims",
    "derive_temporal_claims",
    "serialize_entity_claim",
    "serialize_spatial_claim",
    "serialize_temporal_claim",
]

_T = TypeVar("_T")


def _run_hook(
    records: Iterable[SourceRecord],
    hook: Callable[[SourceRecord], Iterable[_T]] | None,
) -> list[_T]:
    if hook is None:
        return []
    claims: list[_T] = []
    for item in records:
        claims.extend(hook(item))
    return claims


def derive_temporal_claims(
    records: Iterable[SourceRecord],
    *,
    collection: Collection | str | None = None,
) -> list[TemporalClaim]:
    """Run the active collection's deterministic temporal derivations."""

    return _run_hook(records, resolve_collection(collection).hooks.derive_temporal)


def derive_spatial_claims(
    records: Iterable[SourceRecord],
    *,
    collection: Collection | str | None = None,
) -> list[SpatialClaim]:
    """Create provenance-backed spatial claims from structured source geometry."""

    return _run_hook(records, resolve_collection(collection).hooks.derive_spatial)


def derive_entity_claims(
    records: Iterable[SourceRecord],
    *,
    collection: Collection | str | None = None,
) -> list[EntityReferenceClaim]:
    """Derive narrow entity references from explicit source naming conventions."""

    return _run_hook(records, resolve_collection(collection).hooks.derive_entities)
