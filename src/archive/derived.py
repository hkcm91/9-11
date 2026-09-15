from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from archive.adapters.nist_organized import temporal_claim_from_nist_row
from archive.heuristics import document_coverage_claim_from_title
from archive.models import EvidenceRef, LocationKind, SourceItem, SpatialClaim, TemporalClaim


def derive_temporal_claims(records: Iterable[SourceItem]) -> list[TemporalClaim]:
    """Run deterministic, evidence-preserving temporal derivations.

    These are claims, never replacements for SourceItem.date_raw. Only narrow
    transformations with explicit source evidence belong here; uncertain work
    stays in the agent proposal/review pipeline.
    """

    claims: list[TemporalClaim] = []
    for item in records:
        claim = document_coverage_claim_from_title(item)
        if claim is not None:
            claims.append(claim)

        if item.source_id == "nist-wtc-organized-media":
            nist_claim = temporal_claim_from_nist_row(item)
            if nist_claim is not None:
                claims.append(nist_claim)
    return claims


def derive_spatial_claims(records: Iterable[SourceItem]) -> list[SpatialClaim]:
    """Create provenance-backed spatial claims from structured source geometry.

    Community-curated coordinates are useful seed evidence, but they are not
    promoted to verified truth. Accuracy radius remains unset until the source
    or later review provides an evidence-backed precision estimate.
    """

    claims: list[SpatialClaim] = []
    for item in records:
        if item.source_id != "archdisk-911-photo-map":
            continue
        latitude = item.metadata_raw.get("resolved_latitude")
        longitude = item.metadata_raw.get("resolved_longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
            continue
        claims.append(
            SpatialClaim(
                subject_id=item.id,
                latitude=float(latitude),
                longitude=float(longitude),
                location_kind=LocationKind.CAPTURE,
                accuracy_radius_m=None,
                confidence=0.80,
                method="archdisk_arcgis_point",
                created_by_agent="deterministic-arcgis-importer",
                evidence=[
                    EvidenceRef(
                        source_item_id=item.id,
                        relationship="geospatial_source_point",
                        note=(
                            "Point geometry preserved from the public archDisk ArcGIS feature layer. "
                            "Community-curated position should be reviewed before verification."
                        ),
                        weight=0.8,
                    )
                ],
            )
        )
    return claims


def serialize_temporal_claim(claim: TemporalClaim) -> dict[str, Any]:
    payload = asdict(claim)
    payload["time_kind"] = claim.time_kind.value
    payload["status"] = claim.status.value
    if claim.start_time is not None:
        payload["start_time"] = claim.start_time.isoformat()
    if claim.end_time is not None:
        payload["end_time"] = claim.end_time.isoformat()
    return payload


def serialize_spatial_claim(claim: SpatialClaim) -> dict[str, Any]:
    payload = asdict(claim)
    payload["location_kind"] = claim.location_kind.value
    payload["status"] = claim.status.value
    return payload
