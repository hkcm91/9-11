from __future__ import annotations

from archive.adapters.nist_organized import normalize_nist_organized_row, temporal_claim_from_nist_row


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


def test_temporal_claim_is_absent_without_timing_metadata() -> None:
    item = normalize_nist_organized_row({"Record Name": "photo-2.jpg", "Photographer": "X"})
    assert temporal_claim_from_nist_row(item) is None
