from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from archive.models import EvidenceRef, SourceItem, TemporalClaim

SOURCE_ID = "nist-wtc-organized-media"
NY_TZ = ZoneInfo("America/New_York")


class NistOrganizedMediaError(ValueError):
    pass


def _first(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return "; ".join(parts) or None
    text = str(value).strip()
    return text or None


def _boolish(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "x", "checked"}:
        return True
    if text in {"0", "false", "no", "n", "unchecked"}:
        return False
    return None


def _parse_seconds(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        seconds = float(str(value).strip())
    except ValueError:
        return None
    if seconds < 0:
        return None
    return int(round(seconds))


def _parse_local_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None

    # Known/likely export forms from legacy asset databases and spreadsheets.
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=NY_TZ)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY_TZ)
    return parsed


def normalize_nist_organized_row(row: Mapping[str, Any]) -> SourceItem:
    record_name = _text(_first(row, "Record Name", "RecordName", "Filename", "File Name"))
    asset_reference = _text(_first(row, "Asset Reference", "AssetReference", "Asset Ref"))
    stable = record_name or asset_reference
    if not stable:
        raise NistOrganizedMediaError("NIST organized-media row needs Record Name or Asset Reference")

    creator = _text(_first(row, "Photographer", "Videographer", "Creator", "Source"))
    shot_from = _text(_first(row, "Shot From", "ShotFrom", "Location"))
    date_recorded = _text(_first(row, "Date Recorded", "DateRecorded", "Start Recording"))
    copyright_flag = _boolish(_first(row, "Copyright"))
    use_limited = _boolish(_first(row, "Use Limited", "UseLimited"))
    copyright_agreement = _text(_first(row, "Copyright Agreement", "CopyrightAgreement"))
    rights_parts: list[str] = []
    if copyright_flag is True:
        rights_parts.append("Copyright indicated by NIST")
    if use_limited is True:
        rights_parts.append("Use limited")
    if copyright_agreement:
        rights_parts.append(copyright_agreement)

    media_type = "video" if _first(row, "End Recording", "Duration", "Videographer") is not None else "photo"
    metadata = dict(row)
    metadata["_nist_normalized"] = {
        "asset_reference": asset_reference,
        "record_name": record_name,
        "shot_from": shot_from,
        "date_recorded": date_recorded,
        "end_recording": _text(_first(row, "End Recording", "EndRecording")),
        "duration": _text(_first(row, "Duration")),
        "time_uncertainty_seconds": _parse_seconds(_first(row, "Time Uncertainty (s)", "Time Uncertainty", "TimeUncertainty")),
        "view_direction": _text(_first(row, "View Direction", "ViewDirection")),
        "content": _text(_first(row, "Content")),
        "categories": _text(_first(row, "Categories")),
        "copyright": copyright_flag,
        "use_limited": use_limited,
    }

    return SourceItem(
        id=f"{SOURCE_ID}:{stable}",
        source_id=SOURCE_ID,
        source_item_id=stable,
        source_url="",
        title_raw=record_name or stable,
        description_raw=_text(_first(row, "Content", "Description")),
        creator_raw=creator,
        date_raw=date_recorded,
        location_raw=shot_from,
        rights_raw="; ".join(rights_parts) or None,
        collection_raw="NIST Organized Photos and Video Clips",
        media_type_raw=media_type,
        metadata_raw=metadata,
    )


def temporal_claim_from_nist_row(item: SourceItem) -> TemporalClaim | None:
    normalized = item.metadata_raw.get("_nist_normalized")
    if not isinstance(normalized, dict):
        return None
    start = _parse_local_datetime(normalized.get("date_recorded"))
    end = _parse_local_datetime(normalized.get("end_recording"))
    if start is None and end is None:
        return None
    uncertainty = _parse_seconds(normalized.get("time_uncertainty_seconds"))
    uncertainty_ms = uncertainty * 1000 if uncertainty is not None else None
    return TemporalClaim(
        subject_id=item.id,
        start_time=start,
        end_time=end,
        uncertainty_before_ms=uncertainty_ms,
        uncertainty_after_ms=uncertainty_ms,
        confidence=0.95 if uncertainty is not None else 0.8,
        method="nist_visual_database_timing",
        created_by_agent="nist-organized-importer",
        evidence=[
            EvidenceRef(
                source_item_id=item.id,
                relationship="timing_metadata",
                note="Timing and uncertainty preserved from NIST visual-database metadata.",
            )
        ],
    )


def serialize_temporal_claim(claim: TemporalClaim) -> dict[str, Any]:
    value = asdict(claim)
    if claim.start_time is not None:
        value["start_time"] = claim.start_time.isoformat()
    if claim.end_time is not None:
        value["end_time"] = claim.end_time.isoformat()
    value["status"] = claim.status.value
    return value
