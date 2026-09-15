from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

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
from archive.voices import parse_voices_interviewee_label

_ARCHDISK_TIME_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?$")
_FACING_RE = re.compile(
    r"\bfacing\s+(?P<direction>north|south|east|west|northeast|northwest|southeast|southwest|n|s|e|w|ne|nw|se|sw)\b",
    re.IGNORECASE,
)
_NY_TZ = ZoneInfo("America/New_York")
_HEADING = {
    "north": 0.0,
    "n": 0.0,
    "northeast": 45.0,
    "ne": 45.0,
    "east": 90.0,
    "e": 90.0,
    "southeast": 135.0,
    "se": 135.0,
    "south": 180.0,
    "s": 180.0,
    "southwest": 225.0,
    "sw": 225.0,
    "west": 270.0,
    "w": 270.0,
    "northwest": 315.0,
    "nw": 315.0,
}


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


def _archdisk_capture_time_claim(item: SourceItem) -> TemporalClaim | None:
    if item.source_id != "archdisk-911-photo-map":
        return None

    raw_time = item.metadata_raw.get("time_taken_raw") or item.date_raw
    if isinstance(raw_time, str):
        match = _ARCHDISK_TIME_RE.match(raw_time.strip())
        if match:
            hour = int(match.group("h"))
            minute = int(match.group("m"))
            second = int(match.group("s") or 0)
            if hour < 24 and minute < 60 and second < 60:
                captured = datetime(2001, 9, 11, hour, minute, second, tzinfo=_NY_TZ)
                return TemporalClaim(
                    subject_id=item.id,
                    time_kind=TimeKind.CAPTURE,
                    start_time=captured,
                    end_time=captured,
                    confidence=0.85,
                    method="archdisk_time_taken",
                    created_by_agent="deterministic-archdisk-importer",
                    evidence=[
                        EvidenceRef(
                            source_item_id=item.id,
                            relationship="community_map_capture_time",
                            note=(
                                f"Capture time {raw_time.strip()} preserved from archDisk timeTaken metadata; "
                                "date anchored to the map's September 11, 2001 event scope."
                            ),
                            weight=0.85,
                        )
                    ],
                )

    folder = item.metadata_raw.get("folder_path")
    if isinstance(folder, str) and folder.strip().casefold() == "before 8:46am":
        return TemporalClaim(
            subject_id=item.id,
            time_kind=TimeKind.CAPTURE,
            start_time=None,
            end_time=datetime(2001, 9, 11, 8, 46, 0, tzinfo=_NY_TZ),
            confidence=0.70,
            method="archdisk_folder_time_bucket",
            created_by_agent="deterministic-archdisk-importer",
            evidence=[
                EvidenceRef(
                    source_item_id=item.id,
                    relationship="community_map_time_bucket",
                    note="archDisk folder classifies this photograph as captured before 8:46 AM on September 11, 2001.",
                    weight=0.70,
                )
            ],
        )
    return None


def _heading_from_text(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    match = _FACING_RE.search(value)
    if not match:
        return None
    return _HEADING.get(match.group("direction").casefold())


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

        archdisk_claim = _archdisk_capture_time_claim(item)
        if archdisk_claim is not None:
            claims.append(archdisk_claim)
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

        heading = _heading_from_text(item.metadata_raw.get("mapped_address") or item.location_raw)
        note = "Point geometry preserved from the public archDisk ArcGIS feature layer."
        if heading is not None:
            note += f" Facing direction in source address converted to heading {heading:.0f}°."
        note += " Community-curated position should be reviewed before verification."

        claims.append(
            SpatialClaim(
                subject_id=item.id,
                latitude=float(latitude),
                longitude=float(longitude),
                location_kind=LocationKind.CAPTURE,
                accuracy_radius_m=None,
                heading_deg=heading,
                heading_uncertainty_deg=22.5 if heading is not None else None,
                confidence=0.80,
                method="archdisk_arcgis_point",
                created_by_agent="deterministic-arcgis-importer",
                evidence=[
                    EvidenceRef(
                        source_item_id=item.id,
                        relationship="geospatial_source_point",
                        note=note,
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
        try:
            collection_id = int(collection_id) if collection_id is not None else None
        except (TypeError, ValueError):
            collection_id = None

        if item.source_id == "september-11-digital-archive" and collection_id == 267:
            parsed = parse_voices_interviewee_label(item.title_raw)
            if parsed is not None:
                claims.append(
                    EntityReferenceClaim(
                        subject_id=item.id,
                        entity_kind=EntityKind.PERSON,
                        role=EntityRole.INTERVIEWEE,
                        name_raw=parsed.name_raw,
                        normalized_name=parsed.normalized_name,
                        confidence=parsed.confidence,
                        method=parsed.method,
                        created_by_agent="deterministic-entity-parser",
                        evidence=[
                            EvidenceRef(
                                source_item_id=item.id,
                                relationship="interviewee_filename",
                                note=(
                                    "Interviewee source label parsed conservatively from Voices of 9.11 filename: "
                                    f"{(item.title_raw or '').strip()}"
                                ),
                                weight=parsed.confidence,
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

        if item.source_id == "archdisk-911-photo-map" and item.creator_raw:
            name = " ".join(item.creator_raw.split())
            if name:
                claims.append(
                    EntityReferenceClaim(
                        subject_id=item.id,
                        entity_kind=EntityKind.PERSON,
                        role=EntityRole.PHOTOGRAPHER,
                        name_raw=name,
                        normalized_name=name,
                        confidence=0.90,
                        method="archdisk_name_field",
                        created_by_agent="deterministic-entity-parser",
                        evidence=[
                            EvidenceRef(
                                source_item_id=item.id,
                                relationship="community_map_photographer",
                                note="Photographer name preserved from the archDisk photo-map Name field.",
                                weight=0.90,
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
