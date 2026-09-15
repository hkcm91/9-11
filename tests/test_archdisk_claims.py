from datetime import datetime
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
    assert claim.end_time == claim.start_time
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
