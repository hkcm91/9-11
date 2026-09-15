from __future__ import annotations

import json
from pathlib import Path

from archive.adapters.nist_organized import (
    NistOrganizedMediaAdapter,
    entity_claim_from_nist_row,
    load_nist_organized_rows,
    normalize_nist_organized_row,
    parse_embedded_folder_html,
    spatial_claim_from_nist_row,
    temporal_claim_from_nist_row,
)
from archive.models import EntityKind, EntityRole, LocationKind, ReviewStatus, TimeKind


def test_normalize_video_row_preserves_nist_fields() -> None:
    item = normalize_nist_organized_row({
        "Record Name": "clip-001.mov",
        "Asset Reference": "Videos/clip-001.mov",
        "Videographer": "Example Source",
        "Content": "WTC 9/11 Footage",
        "Shot From": "West Street",
        "Date Recorded": "2001-09-11 09:45:12",
        "End Recording": "2001-09-11 09:46:02",
        "Duration": "50",
        "Time Uncertainty (s)": "3",
        "View Direction": "East",
        "Copyright": "yes",
        "Use Limited": "no",
    })

    assert item.media_type_raw == "video"
    assert item.creator_raw == "Example Source"
    assert item.location_raw == "West Street"
    assert item.rights_raw == "Copyright indicated by NIST"
    assert item.metadata_raw["_nist_normalized"]["time_uncertainty_seconds"] == 3
    assert item.metadata_raw["Use Limited"] == "no"
    assert item.metadata_raw["_nist_source_row"]["Use Limited"] == "no"


def test_temporal_claim_uses_new_york_time_and_uncertainty() -> None:
    item = normalize_nist_organized_row({
        "Record Name": "photo-1.jpg",
        "Photographer": "Example Photographer",
        "Date Recorded": "09/11/2001 09:58:20",
        "Time Uncertainty (s)": "2",
        "View Direction": "Southwest",
    })

    claim = temporal_claim_from_nist_row(item)
    assert claim is not None
    assert claim.start_time is not None
    assert claim.start_time.isoformat().endswith("-04:00")
    assert claim.uncertainty_before_ms == 2000
    assert claim.uncertainty_after_ms == 2000
    assert claim.confidence == 0.95
    assert claim.time_kind == TimeKind.CAPTURE
    assert claim.status == ReviewStatus.PROPOSED


def test_temporal_claim_is_absent_without_timing_metadata() -> None:
    item = normalize_nist_organized_row({"Record Name": "photo-2.jpg", "Photographer": "X"})
    assert temporal_claim_from_nist_row(item) is None


def test_video_timing_is_recording_interval_and_duration_can_supply_end() -> None:
    item = normalize_nist_organized_row({
        "Record Name": "clip.avi",
        "Media Type": "video",
        "Start Time": "2001-09-11 09:00:00",
        "Duration": "01:30",
    })
    claim = temporal_claim_from_nist_row(item)
    assert claim is not None
    assert claim.time_kind == TimeKind.RECORDING
    assert claim.start_time is not None and claim.end_time is not None
    assert (claim.end_time - claim.start_time).total_seconds() == 90


def test_nist_coordinates_direction_and_creator_become_proposed_claims() -> None:
    item = normalize_nist_organized_row({
        "Record Name": "photo.jpg",
        "Photographer": "Example Studio",
        "Shot From": "West Street",
        "Latitude": "40.711",
        "Longitude": "-74.013",
        "View Direction": "Southwest",
        "Location Accuracy (m)": "20",
    })
    spatial = spatial_claim_from_nist_row(item)
    entity = entity_claim_from_nist_row(item)
    assert spatial is not None
    assert spatial.location_kind == LocationKind.CAPTURE
    assert spatial.heading_deg == 225.0
    assert spatial.heading_uncertainty_deg == 22.5
    assert spatial.status == ReviewStatus.PROPOSED
    assert entity is not None
    assert entity.entity_kind == EntityKind.OTHER
    assert entity.role == EntityRole.PHOTOGRAPHER
    assert entity.status == ReviewStatus.PROPOSED


def test_public_drive_listing_is_parsed_without_downloading_media() -> None:
    html = """
    <div class="flip-entry" id="entry-folder1"><div class="flip-entry-info">
      <a href="https://drive.google.com/drive/folders/folder1">
        <div aria-label="Folder"></div><div class="flip-entry-title">Photos</div>
      </a></div><div class="flip-entry-last-modified"><div>12/3/19</div></div></div>
    <div class="flip-entry" id="entry-file1"><div class="flip-entry-info">
      <a href="https://drive.google.com/file/d/file1/view"><img alt="Image">
        <div class="flip-entry-title">photo.jpg</div>
      </a></div><div class="flip-entry-last-modified"><div>11/22/19</div></div></div>
    """
    rows = parse_embedded_folder_html(html)
    assert rows == [
        {
            "drive_file_id": "folder1",
            "drive_url": "https://drive.google.com/drive/folders/folder1",
            "is_folder": True,
            "name": "Photos",
            "modified_raw": "12/3/19",
        },
        {
            "drive_file_id": "file1",
            "drive_url": "https://drive.google.com/file/d/file1/view",
            "mime_label": "Image",
            "name": "photo.jpg",
            "modified_raw": "11/22/19",
        },
    ]


def test_recursive_inventory_preserves_drive_ids_paths_and_source_groups() -> None:
    pages = {
        "root": '<div class="flip-entry" id="entry-photos"><a href="https://drive.google.com/drive/folders/photos"><div aria-label="Folder"></div><div class="flip-entry-title">Photos</div></a></div>',
        "photos": '<div class="flip-entry" id="entry-creator"><a href="https://drive.google.com/drive/folders/creator"><div aria-label="Folder"></div><div class="flip-entry-title">Jane Example</div></a></div>',
        "creator": '<div class="flip-entry" id="entry-asset"><a href="https://drive.google.com/file/d/asset/view"><img alt="Image"><div class="flip-entry-title">frame.jpg</div></a></div>',
    }
    adapter = NistOrganizedMediaAdapter(folder_id="root", request_delay_s=0)
    adapter.fetch_folder_html = pages.__getitem__  # type: ignore[method-assign]
    records = adapter.sample(limit=1)
    assert len(records) == 1
    item = records[0]
    assert item.source_item_id == "asset"
    assert item.source_url == "https://drive.google.com/file/d/asset/view"
    assert item.creator_raw == "Jane Example"
    assert item.media_type_raw == "photo"
    assert item.rights_raw is None
    assert item.metadata_raw["folder_path"] == ["Photos", "Jane Example"]
    assert item.metadata_raw["_drive_entry"]["drive_file_id"] == "asset"
    assert item.metadata_raw["rights_context"].startswith("NIST states")


def test_combined_sample_splits_limit_between_photos_and_videos() -> None:
    adapter = NistOrganizedMediaAdapter(folder_id="root", request_delay_s=0)
    calls = []

    def fake_inventory(*, limit, media_type):
        calls.append((limit, media_type))
        extension = "jpg" if media_type == "photo" else "avi"
        return [
            {
                "Record Name": f"{media_type}-{index}.{extension}",
                "Drive File ID": f"{media_type}-{index}",
                "Media Type": media_type,
            }
            for index in range(limit)
        ]

    adapter.inventory_rows = fake_inventory  # type: ignore[method-assign]
    records = adapter.sample(limit=5)
    assert calls == [(3, "photo"), (2, "video")]
    assert [record.media_type_raw for record in records] == ["photo"] * 3 + ["video"] * 2


def test_manifest_loaders_preserve_unknown_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "nist.csv"
    csv_path.write_text("Record Name,Unmapped Field\nphoto.jpg,verbatim\n", encoding="utf-8")
    json_path = tmp_path / "nist.json"
    json_path.write_text(json.dumps({"records": [{"Record Name": "clip.avi", "Other": 7}]}), encoding="utf-8")
    assert load_nist_organized_rows(csv_path)[0]["Unmapped Field"] == "verbatim"
    assert load_nist_organized_rows(json_path)[0]["Other"] == 7
