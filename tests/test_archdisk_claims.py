from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from archive.derived import derive_entity_claims, derive_spatial_claims, derive_temporal_claims
from archive.models import EntityRole, SourceItem, TimeKind


def make_archdisk(*, creator: str = "Jane Example", time_taken: str | None = None,
                  folder: str | None = None, address: str = "3rd Ave. - Facing West") -> SourceItem:
    metadata = {
        "resolved_latitude": 40.73,
        "resolved_longitude": -73.98,
        "mapped_address": address,
        "time_taken_raw": time_taken,
        "folder_path": folder,
    }
    return SourceItem(
        id="archdisk-911-photo-map:test",
        source_id="archdisk-911-photo-map",
        source_item_id="test",
        source_url="https://archdisk.com/photomap",
        title_raw=creator,
        creator_raw=creator,
        date_raw=time_taken,
        location_raw=address,
        collection_raw="archDisk 9/11 Photo Map",
        media_type_raw="photo",
        metadata_raw=metadata,
    )


def test_archdisk_exact_time_becomes_capture_claim_on_september_11() -> None:
    item = make_archdisk(time_taken="08:40:00", folder="Before 8:46AM")
    claim = derive_temporal_claims([item])[0]

    assert claim.time_kind == TimeKind.CAPTURE
    assert claim.start_time == datetime(2001, 9, 11, 8, 40, tzinfo=ZoneInfo("America/New_York"))
    assert claim.end_time - claim.start_time == timedelta(microseconds=999999)
    assert claim.method == "archdisk_time_taken"


def test_archdisk_folder_bucket_gives_upper_bound_when_exact_time_missing() -> None:
    item = make_archdisk(time_taken=None, folder="Before 8:46AM")
    claim = derive_temporal_claims([item])[0]

    assert claim.time_kind == TimeKind.CAPTURE
    assert claim.start_time is None
    assert claim.end_time == datetime(2001, 9, 11, 8, 46, tzinfo=ZoneInfo("America/New_York"))
    assert claim.method == "archdisk_folder_time_bucket"


def test_archdisk_facing_direction_becomes_heading() -> None:
    item = make_archdisk(address="3rd Ave. - Facing West")
    claim = derive_spatial_claims([item])[0]

    assert claim.heading_deg == 270.0
    assert claim.heading_uncertainty_deg == 22.5


def test_archdisk_name_becomes_photographer_entity_claim() -> None:
    item = make_archdisk(creator="John Labriola")
    claim = derive_entity_claims([item])[0]

    assert claim.role == EntityRole.PHOTOGRAPHER
    assert claim.name_raw == "John Labriola"
    assert claim.confidence == 0.90


def test_minute_notation_does_not_claim_second_precision():
    claim = derive_temporal_claims([make_archdisk(time_taken="09:15")])[0]
    assert claim.end_time - claim.start_time == timedelta(seconds=60, microseconds=-1)
    assert "accuracy is unknown" in claim.evidence[0].note


def test_range_bucket_preserves_interval_and_provenance():
    item = make_archdisk(folder="9:03-9:59AM")
    claim = derive_temporal_claims([item])[0]
    assert claim.start_time.isoformat() == "2001-09-11T09:03:00-04:00"
    assert claim.end_time.isoformat() == "2001-09-11T09:59:00-04:00"
    assert claim.status == "proposed"
    assert item.metadata_raw["folder_path"] in claim.evidence[0].note


def test_after_bucket_is_open_ended_and_event_labels_are_not_exact_times():
    claim = derive_temporal_claims([make_archdisk(folder="After 10:28AM")])[0]
    assert claim.start_time.hour == 10
    assert claim.end_time is None
    for label in ("10:28AM - WTC1 Collapse", "Unknown", "5:20PM - WTC7 Collapse"):
        assert derive_temporal_claims([make_archdisk(folder=label)]) == []
