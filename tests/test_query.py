from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from archive.models import SourceItem
from archive.query import ArchiveQuery
from archive.store import ArchiveStore


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def build_database(tmp_path: Path) -> Path:
    db = tmp_path / "archive.sqlite"
    photo = SourceItem(
        id="photo:1",
        source_id="photos",
        source_item_id="1",
        source_url="https://example.test/photo/1",
        title_raw="Lower Manhattan photograph",
        creator_raw="Jane Example",
        media_type_raw="photo",
        metadata_raw={"original": True},
        ingested_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    document = SourceItem(
        id="document:1",
        source_id="documents",
        source_item_id="1",
        source_url="https://example.test/document/1",
        title_raw="Incident Action Plan",
        media_type_raw="document",
        metadata_raw={},
        ingested_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    temporal = tmp_path / "temporal.jsonl"
    spatial = tmp_path / "spatial.jsonl"
    entity = tmp_path / "entity.jsonl"
    write_jsonl(temporal, [
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
    ])
    write_jsonl(spatial, [{
        "subject_id": "photo:1",
        "location_kind": "capture_location",
        "latitude": 40.711,
        "longitude": -74.012,
        "heading_deg": 270.0,
        "confidence": 0.8,
        "status": "proposed",
        "method": "test_map",
        "evidence": [],
    }])
    write_jsonl(entity, [{
        "subject_id": "photo:1",
        "entity_kind": "person",
        "role": "photographer",
        "name_raw": "Jane Example",
        "normalized_name": "Jane Example",
        "confidence": 0.9,
        "status": "proposed",
        "method": "test_entity",
        "evidence": [],
    }])

    with ArchiveStore(db) as store:
        store.put_source_items([photo, document])
        store.import_claim_jsonl(temporal, "temporal")
        store.import_claim_jsonl(spatial, "spatial")
        store.import_claim_jsonl(entity, "entity")
    return db


def test_item_bundle_contains_record_claims_and_observations(tmp_path: Path) -> None:
    db = build_database(tmp_path)
    with ArchiveQuery(db) as query:
        bundle = query.item_bundle("photo:1")

    assert bundle is not None
    assert bundle["record"]["title_raw"] == "Lower Manhattan photograph"
    assert len(bundle["temporal_claims"]) == 1
    assert len(bundle["spatial_claims"]) == 1
    assert bundle["entity_claims"][0]["role"] == "photographer"
    assert len(bundle["observations"]) == 1


def test_timeline_semantic_filter_excludes_document_coverage(tmp_path: Path) -> None:
    db = build_database(tmp_path)
    start = datetime.fromisoformat("2001-09-11T08:00:00-04:00")
    end = datetime.fromisoformat("2001-09-11T09:00:00-04:00")

    with ArchiveQuery(db) as query:
        rows = query.timeline(start, end, kinds={"capture_time"})

    assert len(rows) == 1
    assert rows[0]["subject_id"] == "photo:1"
    assert rows[0]["time_kind"] == "capture_time"


def test_timeline_without_kind_can_return_multiple_semantic_times(tmp_path: Path) -> None:
    db = build_database(tmp_path)
    start = datetime.fromisoformat("2001-09-11T08:00:00-04:00")
    end = datetime.fromisoformat("2001-09-11T09:00:00-04:00")

    with ArchiveQuery(db) as query:
        rows = query.timeline(start, end)

    assert {row["subject_id"] for row in rows} == {"photo:1", "document:1"}


def test_nearby_returns_capture_point_with_distance_and_heading(tmp_path: Path) -> None:
    db = build_database(tmp_path)
    with ArchiveQuery(db) as query:
        rows = query.nearby(40.7111, -74.0121, 100, kinds={"capture_location"})

    assert len(rows) == 1
    assert rows[0].subject_id == "photo:1"
    assert rows[0].distance_m < 20
    assert rows[0].heading_deg == 270.0
    assert rows[0].record["creator_raw"] == "Jane Example"


def test_nearby_respects_radius(tmp_path: Path) -> None:
    db = build_database(tmp_path)
    with ArchiveQuery(db) as query:
        rows = query.nearby(40.75, -74.05, 100, kinds={"capture_location"})

    assert rows == []
