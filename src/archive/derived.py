from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from archive.adapters.nist_organized import temporal_claim_from_nist_row
from archive.heuristics import document_coverage_claim_from_title
from archive.models import (
    EntityKind,
    EntityReferenceClaim,
    EntityRole,
    EvidenceRef,
    LocationKind,
    SourceItem,
    SpatialClaim,
    TemporalClaim,
    TimeKind,
)

_VOICES_FILENAME_RE = re.compile(
    r"^V\d+\s+(?P<name>.+?)(?:\.(?:mov|mp4|m4v|avi)){1,2}$",
    re.IGNORECASE,
)


def _parse_ia_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _internet_archive_recording_claim(item: SourceItem) -> TemporalClaim | None:
    if item.source_id != "internet-archive-understanding-911":
        return None
    start = _parse_ia_utc_datetime(item.metadata_raw.get("start_time"))
    end = _parse_ia_utc_datetime(item.metadata_raw.get("stop_time"))
    if start is None and end is None:
        return None
    if start is not None and end is not None and end < start:
        return None
    return TemporalClaim(
        subject_id=item.id,
        time_kind=TimeKind.RECORDING,
        start_time=start,
        end_time=end,
        confidence=0.97,
        method="internet_archive_broadcast_start_stop_metadata",
        created_by_agent="deterministic-internet-archive-importer",
        evidence=[
            EvidenceRef(
                source_item_id=item.id,
                relationship="broadcast_timing_metadata",
                note=(
                    "UTC recording interval preserved from Internet Archive start_time/stop_time metadata. "
                    "Local-time and UTC-offset source fields remain available in raw metadata."
                ),
                weight=0.97,
            )
        ],
    )


def derive_temporal_claims(records: Iterable[SourceItem]) -> list[TemporalClaim]:
    """Run deterministic, evidence-preserving temporal derivations."""
    claims: list[TemporalClaim] = []
    for item in records:
        claim = document_coverage_claim_from_title(item)
        if claim is not None:
            claims.append(claim)

        if item.source_id == "nist-wtc-organized-media":
            nist_claim = temporal_claim_from_nist_row(item)
            if nist_claim is not None:
                claims.append(nist_claim)

        ia_claim = _internet_archive_recording_claim(item)
        if ia_claim is not None:
            claims.append(ia_claim)
    return claims


def derive_spatial_claims(records: Iterable[SourceItem]) -> list[SpatialClaim]:
    """Create provenance-backed spatial claims from structured source geometry."""
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


def derive_entity_claims(records: Iterable[SourceItem]) -> list[EntityReferenceClaim]:
    """Derive narrow entity references from explicit source naming conventions."""
    claims: list[EntityReferenceClaim] = []
    for item in records:
        collection_id = item.metadata_raw.get("collection_id")
        if item.source_id == "september-11-digital-archive" and collection_id == 267:
            title = (item.title_raw or "").strip()
            match = _VOICES_FILENAME_RE.match(title)
            if match:
                name = " ".join(match.group("name").split())
                if name:
                    claims.append(
                        EntityReferenceClaim(
                            subject_id=item.id,
                            entity_kind=EntityKind.PERSON,
                            role=EntityRole.INTERVIEWEE,
                            name_raw=name,
                            normalized_name=name,
                            confidence=0.95,
                            method="voices_911_filename_convention",
                            created_by_agent="deterministic-entity-parser",
                            evidence=[
                                EvidenceRef(
                                    source_item_id=item.id,
                                    relationship="interviewee_filename",
                                    note=f"Interviewee name parsed from Voices of 9.11 source filename: {title}",
                                    weight=0.95,
                                )
                            ],
                        )
                    )

        if item.source_id == "internet-archive-understanding-911":
            contributor = item.metadata_raw.get("contributor")
            if isinstance(contributor, list):
                contributor = "; ".join(str(value) for value in contributor if value)
            if isinstance(contributor, str) and contributor.strip():
                name = contributor.strip()
                claims.append(
                    EntityReferenceClaim(
                        subject_id=item.id,
                        entity_kind=EntityKind.ORGANIZATION,
                        role=EntityRole.BROADCASTER,
                        name_raw=name,
                        normalized_name=name,
                        confidence=0.99,
                        method="internet_archive_contributor_metadata",
                        created_by_agent="deterministic-entity-parser",
                        evidence=[
                            EvidenceRef(
                                source_item_id=item.id,
                                relationship="broadcaster_metadata",
                                note="Broadcaster preserved from Internet Archive contributor metadata.",
                                weight=0.99,
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


def serialize_entity_claim(claim: EntityReferenceClaim) -> dict[str, Any]:
    payload = asdict(claim)
    payload["entity_kind"] = claim.entity_kind.value
    payload["role"] = claim.role.value
    payload["status"] = claim.status.value
    return payload
