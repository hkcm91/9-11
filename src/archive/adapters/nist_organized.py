from __future__ import annotations

import csv
import json
import mimetypes
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

SOURCE_ID = "nist-wtc-organized-media"
DEFAULT_FOLDER_ID = "17lDS4YslnUaOHv-x2CEhWLVzmceNllk1"
DEFAULT_FOLDER_URL = f"https://googledrive.nist.gov/folders/{DEFAULT_FOLDER_ID}"
DEFAULT_USER_AGENT = "nine-eleven-archive/0.1 metadata-research; contact=https://github.com/hkcm91/9-11"
COLLECTION_RIGHTS_CONTEXT = (
    "NIST states that public repository materials may be protected by third-party copyright and "
    "may be subject to use restrictions; item-specific clearance is required."
)

try:
    NY_TZ = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:  # Windows Python may not ship the IANA database.
    NY_TZ = timezone(timedelta(hours=-4), name="EDT")

_HEADING = {
    "north": 0.0, "n": 0.0,
    "northeast": 45.0, "north east": 45.0, "ne": 45.0,
    "east": 90.0, "e": 90.0,
    "southeast": 135.0, "south east": 135.0, "se": 135.0,
    "south": 180.0, "s": 180.0,
    "southwest": 225.0, "south west": 225.0, "sw": 225.0,
    "west": 270.0, "w": 270.0,
    "northwest": 315.0, "north west": 315.0, "nw": 315.0,
}


class NistOrganizedMediaError(ValueError):
    pass


class NistOrganizedMediaFetchError(RuntimeError):
    pass


def _first(row: Mapping[str, Any], *names: str) -> Any:
    lowered = {str(k).strip().casefold(): v for k, v in row.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
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
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "x", "checked"}:
        return True
    if text in {"0", "false", "no", "n", "unchecked"}:
        return False
    return None


def _parse_number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _parse_seconds(value: Any) -> int | None:
    seconds = _parse_number(value)
    if seconds is None or seconds < 0:
        return None
    return int(round(seconds))


def _parse_duration_seconds(value: Any) -> float | None:
    text = _text(value)
    if not text:
        return None
    number = _parse_number(text)
    if number is not None:
        return number if number >= 0 else None
    parts = text.split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if any(number < 0 for number in numbers):
        return None
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def _parse_local_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    formats = (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M:%S", "%m/%d/%y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=NY_TZ)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=NY_TZ) if parsed.tzinfo is None else parsed


def _media_type(row: Mapping[str, Any], record_name: str | None) -> str:
    explicit = _text(_first(row, "Media Type", "MediaType", "Asset Type", "Type", "mime_type"))
    if explicit:
        lowered = explicit.casefold()
        if any(token in lowered for token in ("video", "movie", "quicktime")):
            return "video"
        if any(token in lowered for token in ("photo", "image", "jpeg", "jpg", "png", "tiff")):
            return "photo"
    if record_name:
        guessed, _ = mimetypes.guess_type(record_name)
        if guessed:
            if guessed.startswith("video/"):
                return "video"
            if guessed.startswith("image/"):
                return "photo"
    if _text(_first(row, "Videographer", "End Recording", "EndRecording", "Duration")):
        return "video"
    return "photo"


def _record_url(row: Mapping[str, Any], stable: str) -> str:
    explicit = _text(_first(row, "Source URL", "SourceURL", "URL", "webViewLink", "drive_url"))
    if explicit:
        return explicit
    drive_id = _text(_first(row, "Drive File ID", "drive_file_id", "File ID", "id"))
    if drive_id:
        return f"https://drive.google.com/file/d/{drive_id}/view"
    return DEFAULT_FOLDER_URL


def normalize_nist_organized_row(row: Mapping[str, Any]) -> SourceItem:
    """Normalize one NIST export/listing row while retaining the row verbatim."""
    record_name = _text(_first(row, "Record Name", "RecordName", "Filename", "File Name", "name"))
    asset_reference = _text(_first(row, "Asset Reference", "AssetReference", "Asset Ref", "path"))
    drive_id = _text(_first(row, "Drive File ID", "drive_file_id", "File ID"))
    stable = drive_id or asset_reference or record_name
    if not stable:
        raise NistOrganizedMediaError("NIST organized-media row needs a Drive file ID, Record Name, or Asset Reference")

    creator = _text(_first(row, "Photographer", "Videographer", "Creator", "Source", "source_group"))
    shot_from = _text(_first(row, "Shot From", "ShotFrom", "Location", "Camera Location"))
    date_recorded = _text(_first(row, "Date Recorded", "DateRecorded", "Start Recording", "Start Time", "Capture Time"))
    end_recording = _text(_first(row, "End Recording", "EndRecording", "End Time"))
    copyright_raw = _first(row, "Copyright")
    use_limited_raw = _first(row, "Use Limited", "UseLimited")
    copyright_flag = _boolish(copyright_raw)
    use_limited = _boolish(use_limited_raw)
    rights_parts: list[str] = []
    for field in ("Rights", "License", "Copyright Owner", "Copyright Agreement", "CopyrightAgreement", "Credit"):
        value = _text(_first(row, field))
        if value and value not in rights_parts:
            rights_parts.append(value)
    if copyright_flag is True and not rights_parts:
        rights_parts.append("Copyright indicated by NIST")
    if use_limited is True:
        rights_parts.append("Use limited")

    media_type = _media_type(row, record_name)
    metadata = dict(row)
    metadata["_nist_source_row"] = dict(row)
    metadata["_nist_normalized"] = {
        "asset_reference": asset_reference,
        "record_name": record_name,
        "drive_file_id": drive_id,
        "shot_from": shot_from,
        "date_recorded": date_recorded,
        "end_recording": end_recording,
        "duration": _text(_first(row, "Duration")),
        "time_uncertainty_seconds": _parse_seconds(
            _first(row, "Time Uncertainty (s)", "Time Uncertainty", "TimeUncertainty", "Timing Precision (s)")
        ),
        "view_direction": _text(_first(row, "View Direction", "ViewDirection", "Camera Direction", "Direction")),
        "latitude": _parse_number(_first(row, "Latitude", "Lat", "Shot From Latitude", "Camera Latitude")),
        "longitude": _parse_number(_first(row, "Longitude", "Lon", "Lng", "Shot From Longitude", "Camera Longitude")),
        "location_accuracy_m": _parse_number(_first(row, "Location Accuracy (m)", "Accuracy Radius (m)")),
        "content": _text(_first(row, "Content", "Description")),
        "categories": _text(_first(row, "Categories", "Category")),
        "tags": _first(row, "Tags", "Tag"),
        "copyright_raw": copyright_raw,
        "copyright": copyright_flag,
        "use_limited_raw": use_limited_raw,
        "use_limited": use_limited,
        "rights_context": COLLECTION_RIGHTS_CONTEXT,
    }

    return SourceItem(
        id=f"{SOURCE_ID}:{stable}",
        source_id=SOURCE_ID,
        source_item_id=stable,
        source_url=_record_url(row, stable),
        title_raw=record_name or stable,
        description_raw=_text(_first(row, "Content", "Description")),
        creator_raw=creator,
        date_raw=date_recorded,
        location_raw=shot_from,
        rights_raw="; ".join(rights_parts) or None,
        collection_raw="NIST Organized Photos and Video Clips",
        media_type_raw=media_type,
        metadata_raw=metadata,
        ingested_at=datetime.now(timezone.utc),
    )


def temporal_claim_from_nist_row(item: SourceItem) -> TemporalClaim | None:
    normalized = item.metadata_raw.get("_nist_normalized")
    if not isinstance(normalized, dict):
        return None
    start = _parse_local_datetime(normalized.get("date_recorded"))
    end = _parse_local_datetime(normalized.get("end_recording"))
    if start is not None and end is None and item.media_type_raw == "video":
        duration = _parse_duration_seconds(normalized.get("duration"))
        if duration is not None:
            end = start + timedelta(seconds=duration)
    if start is None and end is None:
        return None
    if start is not None and end is not None and end < start:
        return None
    uncertainty = _parse_seconds(normalized.get("time_uncertainty_seconds"))
    uncertainty_ms = uncertainty * 1000 if uncertainty is not None else None
    time_kind = TimeKind.RECORDING if item.media_type_raw == "video" else TimeKind.CAPTURE
    confidence = 0.95 if uncertainty is not None else 0.8
    return TemporalClaim(
        subject_id=item.id,
        time_kind=time_kind,
        start_time=start,
        end_time=end,
        uncertainty_before_ms=uncertainty_ms,
        uncertainty_after_ms=uncertainty_ms,
        confidence=confidence,
        method="nist_visual_database_timing",
        created_by_agent="nist-organized-importer",
        evidence=[EvidenceRef(
            source_item_id=item.id,
            relationship="nist_timing_metadata",
            note="Timing and uncertainty preserved from NIST organized visual-media metadata.",
            weight=confidence,
        )],
    )


def spatial_claim_from_nist_row(item: SourceItem) -> SpatialClaim | None:
    normalized = item.metadata_raw.get("_nist_normalized")
    if not isinstance(normalized, dict):
        return None
    latitude = normalized.get("latitude")
    longitude = normalized.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        return None
    raw_direction = _text(normalized.get("view_direction"))
    heading = _parse_number(raw_direction)
    numeric_direction = heading is not None
    if heading is None and raw_direction:
        heading = _HEADING.get(" ".join(raw_direction.casefold().replace("-", " ").split()))
    if heading is not None:
        heading %= 360
    return SpatialClaim(
        subject_id=item.id,
        latitude=float(latitude),
        longitude=float(longitude),
        location_kind=LocationKind.CAPTURE,
        accuracy_radius_m=normalized.get("location_accuracy_m"),
        heading_deg=heading,
        heading_uncertainty_deg=None if numeric_direction else (22.5 if heading is not None else None),
        confidence=0.9,
        method="nist_visual_database_location",
        created_by_agent="nist-organized-importer",
        evidence=[EvidenceRef(
            source_item_id=item.id,
            relationship="nist_capture_location_metadata",
            note="Camera position and view direction preserved from NIST organized visual-media metadata.",
            weight=0.9,
        )],
    )


def entity_claim_from_nist_row(item: SourceItem) -> EntityReferenceClaim | None:
    if not item.creator_raw:
        return None
    if _text(_first(item.metadata_raw, "Photographer")):
        role = EntityRole.PHOTOGRAPHER
    elif _text(_first(item.metadata_raw, "Videographer")):
        role = EntityRole.VIDEOGRAPHER
    else:
        role = EntityRole.CREATOR
    confidence = 0.98 if role != EntityRole.CREATOR else 0.9
    return EntityReferenceClaim(
        subject_id=item.id,
        entity_kind=EntityKind.OTHER,
        role=role,
        name_raw=item.creator_raw,
        normalized_name=" ".join(item.creator_raw.split()),
        confidence=confidence,
        method="nist_visual_database_creator",
        created_by_agent="nist-organized-importer",
        evidence=[EvidenceRef(
            source_item_id=item.id,
            relationship="nist_creator_metadata",
            note="Creator/source identity preserved without inferring whether it names a person or organization.",
            weight=confidence,
        )],
    )


class _EmbeddedFolderParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, Any]] = []
        self._entry: dict[str, Any] | None = None
        self._entry_depth = 0
        self._capture: str | None = None
        self._capture_depth = 0
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "div" and "flip-entry" in classes:
            entry_id = values.get("id") or ""
            self._entry = {"drive_file_id": entry_id.removeprefix("entry-")}
            self._entry_depth = 1
        elif tag == "div" and self._entry is not None:
            self._entry_depth += 1
        if self._entry is None:
            return
        if tag == "a" and values.get("href"):
            self._entry["drive_url"] = values["href"]
        if values.get("aria-label"):
            label = values["aria-label"]
            if label == "Folder":
                self._entry["is_folder"] = True
            elif "mime_label" not in self._entry:
                self._entry["mime_label"] = label
        if tag == "img" and values.get("alt") and "mime_label" not in self._entry:
            self._entry["mime_label"] = values["alt"]
        if tag == "div" and "flip-entry-title" in classes:
            self._capture = "name"
            self._capture_depth = self._entry_depth
            self._text_parts = []
        elif tag == "div" and "flip-entry-last-modified" in classes:
            self._capture = "modified_raw"
            self._capture_depth = self._entry_depth
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._entry is not None and self._capture:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or self._entry is None:
            return
        if self._capture and self._entry_depth == self._capture_depth:
            value = " ".join("".join(self._text_parts).split())
            if value:
                self._entry[self._capture] = value
            self._capture = None
            self._text_parts = []
        self._entry_depth -= 1
        if self._entry_depth == 0:
            if self._entry.get("name"):
                self.entries.append(self._entry)
            self._entry = None


def parse_embedded_folder_html(html: str) -> list[dict[str, Any]]:
    parser = _EmbeddedFolderParser()
    parser.feed(html)
    return parser.entries


def load_nist_organized_rows(path: Path | str) -> list[dict[str, Any]]:
    """Load a NIST metadata export without discarding unknown columns."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise NistOrganizedMediaError(f"expected object at {path}:{line_number}")
                rows.append(value)
        return rows
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            for key in ("rows", "records", "items"):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise NistOrganizedMediaError(f"expected a JSON array (or rows/records/items array) in {path}")
        return [dict(row) for row in value]
    raise NistOrganizedMediaError("NIST manifest must be CSV, JSON, JSONL, or NDJSON")


class NistOrganizedMediaAdapter:
    """Inventory NIST's public organized-media Drive hierarchy without media downloads."""

    def __init__(
        self,
        *,
        folder_id: str = DEFAULT_FOLDER_ID,
        user_agent: str = DEFAULT_USER_AGENT,
        request_delay_s: float = 0.25,
        timeout_s: float = 30.0,
    ) -> None:
        self.folder_id = folder_id
        self.user_agent = user_agent
        self.request_delay_s = request_delay_s
        self.timeout_s = timeout_s
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        if self._last_request_at is None or self.request_delay_s <= 0:
            return
        remaining = self.request_delay_s - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def embedded_folder_url(folder_id: str) -> str:
        return f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"

    def fetch_folder_html(self, folder_id: str) -> str:
        self._throttle()
        url = self.embedded_folder_url(folder_id)
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept": "text/html"})
        try:
            with urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 - public NIST Drive folder
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise NistOrganizedMediaFetchError(f"failed to list public NIST Drive folder {folder_id}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()

    @staticmethod
    def _folder_id(entry: Mapping[str, Any]) -> str | None:
        if entry.get("drive_file_id"):
            return str(entry["drive_file_id"])
        url = _text(entry.get("drive_url"))
        if not url:
            return None
        parts = urlparse(url).path.rstrip("/").split("/")
        return parts[-1] if "folders" in parts else None

    def inventory_rows(self, *, limit: int | None = 50) -> list[dict[str, Any]]:
        if limit is not None and limit < 1:
            return []
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(self.folder_id, ())])
        visited: set[str] = set()
        assets: list[dict[str, Any]] = []
        while queue and (limit is None or len(assets) < limit):
            folder_id, parent_path = queue.popleft()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            entries = parse_embedded_folder_html(self.fetch_folder_html(folder_id))
            if not entries and not parent_path:
                raise NistOrganizedMediaFetchError(
                    "NIST organized-media root returned no parseable public Drive entries"
                )
            for entry in entries:
                name = _text(entry.get("name"))
                if not name:
                    continue
                path = (*parent_path, name)
                if entry.get("is_folder"):
                    child_id = self._folder_id(entry)
                    if child_id:
                        queue.append((child_id, path))
                    continue
                if not parent_path or parent_path[0] not in {"Photos", "VideoClips"}:
                    continue
                row = {"_drive_entry": dict(entry), **entry}
                row.update({
                    "Record Name": name,
                    "Asset Reference": "/".join(path),
                    "Media Type": "photo" if parent_path[0] == "Photos" else "video",
                    "source_group": parent_path[1] if len(parent_path) > 1 else None,
                    "folder_path": list(parent_path),
                    "Source URL": entry.get("drive_url"),
                    "Drive File ID": entry.get("drive_file_id"),
                    "repository_folder_id": self.folder_id,
                    "repository_folder_url": DEFAULT_FOLDER_URL,
                    "rights_context": COLLECTION_RIGHTS_CONTEXT,
                    "listing_endpoint": self.embedded_folder_url(folder_id),
                })
                assets.append(row)
                if limit is not None and len(assets) >= limit:
                    break
        if not assets:
            raise NistOrganizedMediaFetchError(
                "NIST organized-media hierarchy returned no photo or video asset records"
            )
        return assets

    def sample(self, *, limit: int = 50) -> list[SourceItem]:
        return [normalize_nist_organized_row(row) for row in self.inventory_rows(limit=limit)]

    def import_manifest(self, path: Path | str, *, limit: int | None = None) -> list[SourceItem]:
        rows = load_nist_organized_rows(path)
        if limit is not None:
            rows = rows[:limit]
        return [normalize_nist_organized_row(row) for row in rows]

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value


def serialize_temporal_claim(claim: TemporalClaim) -> dict[str, Any]:
    value = asdict(claim)
    if claim.start_time is not None:
        value["start_time"] = claim.start_time.isoformat()
    if claim.end_time is not None:
        value["end_time"] = claim.end_time.isoformat()
    value["time_kind"] = claim.time_kind.value
    value["status"] = claim.status.value
    return value
