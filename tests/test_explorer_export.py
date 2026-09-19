from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from archive.explorer_export import build_explorer_payload, write_explorer_payload
from archive.models import SourceItem
from archive.store import ArchiveStore


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _build_database(tmp_path: Path) -> Path:
    db = tmp_path / "archive.sqlite"
    photo = SourceItem(
        id="photo:1",
        source_id="photos",
        source_item_id="1",
        source_url="https://example.test/photo/1",
        title_raw="Lower Manhattan photograph",
        creator_raw="Jane Example",
        rights_raw="source terms apply",
        media_type_raw="photo",
        metadata_raw={"original": True},
        ingested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    document = SourceItem(
        id="document:1",
        source_id="documents",
        source_item_id="1",
        source_url="https://example.test/document/1",
        title_raw="Incident Action Plan",
        media_type_raw="document",
        metadata_raw={},
        ingested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )

    temporal = tmp_path / "temporal.jsonl"
    spatial = tmp_path / "spatial.jsonl"
    entity = tmp_path / "entity.jsonl"
    _write_jsonl(
        temporal,
        [
            {
                "subject_id": "photo:1",
                "time_kind": "capture_time",
                "start_time": "2001-09-11T08:40:00-04:00",
                "end_time": "2001-09-11T08:40:00-04:00",
                "confidence": 0.85,
                "status": "proposed",
                "method": "test_capture",
                "evidence": [],
            },
            {
                "subject_id": "document:1",
                "time_kind": "document_coverage",
                "start_time": "2001-09-11T00:00:00-04:00",
                "end_time": "2001-09-12T00:00:00-04:00",
                "confidence": 0.99,
                "status": "proposed",
                "method": "test_document",
                "evidence": [],
            },
        ],
    )
    _write_jsonl(
        spatial,
        [
            {
                "subject_id": "photo:1",
                "location_kind": "capture_location",
                "latitude": 40.711,
                "longitude": -74.012,
                "heading_deg": 270.0,
                "confidence": 0.8,
                "status": "proposed",
                "method": "test_map",
                "evidence": [],
            }
        ],
    )
    _write_jsonl(
        entity,
        [
            {
                "subject_id": "photo:1",
                "entity_kind": "person",
                "role": "photographer",
                "name_raw": "Jane Example",
                "normalized_name": "Jane Example",
                "confidence": 0.9,
                "status": "proposed",
                "method": "test_entity",
                "evidence": [],
            }
        ],
    )

    with ArchiveStore(db) as store:
        store.put_source_items([photo, document])
        store.import_claim_jsonl(temporal, "temporal")
        store.import_claim_jsonl(spatial, "spatial")
        store.import_claim_jsonl(entity, "entity")
    return db


def test_exporter_keeps_claim_provenance_and_excludes_document_date_as_timeline_position(
    tmp_path: Path,
) -> None:
    db = _build_database(tmp_path)
    payload = build_explorer_payload(
        db,
        start=datetime.fromisoformat("2001-09-11T08:00:00-04:00"),
        end=datetime.fromisoformat("2001-09-11T12:00:00-04:00"),
    )

    assert payload["schema_version"] == 1
    assert payload["item_count"] == 1
    item = payload["items"][0]
    assert item["id"] == "photo:1"
    assert item["time"]["time_kind"] == "capture_time"
    assert item["time"]["status"] == "proposed"
    assert item["time"]["method"] == "test_capture"
    assert item["location"]["location_kind"] == "capture_location"
    assert item["location"]["heading_deg"] == 270.0
    assert item["entities"][0]["role"] == "photographer"
    assert item["rights"] == "source terms apply"


def test_exporter_respects_confidence_threshold(tmp_path: Path) -> None:
    db = _build_database(tmp_path)
    payload = build_explorer_payload(
        db,
        start=datetime.fromisoformat("2001-09-11T08:00:00-04:00"),
        end=datetime.fromisoformat("2001-09-11T12:00:00-04:00"),
        min_confidence=0.86,
    )

    assert payload["items"] == []


def test_write_explorer_payload_creates_json_file(tmp_path: Path) -> None:
    db = _build_database(tmp_path)
    output = tmp_path / "site" / "data" / "explorer.json"
    payload = write_explorer_payload(
        db,
        output,
        start=datetime.fromisoformat("2001-09-11T08:00:00-04:00"),
        end=datetime.fromisoformat("2001-09-11T12:00:00-04:00"),
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["item_count"] == payload["item_count"] == 1
    assert saved["items"][0]["source_url"] == "https://example.test/photo/1"
