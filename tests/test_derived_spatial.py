from __future__ import annotations

from archive.derived import derive_spatial_claims, serialize_spatial_claim
from archive.models import LocationKind, ReviewStatus, SourceItem


def test_archdisk_point_becomes_proposed_capture_location() -> None:
    item = SourceItem(
        id="archdisk:1",
        source_id="archdisk-911-photo-map",
        source_item_id="1",
        source_url="https://archdisk.com/photomap",
        media_type_raw="photo",
        metadata_raw={"resolved_latitude": 40.711, "resolved_longitude": -74.013},
    )

    claims = derive_spatial_claims([item])
    assert len(claims) == 1
    claim = claims[0]
    assert claim.location_kind == LocationKind.CAPTURE
    assert claim.latitude == 40.711
    assert claim.longitude == -74.013
    assert claim.confidence == 0.80
    assert claim.accuracy_radius_m is None
    assert claim.status == ReviewStatus.PROPOSED
    assert claim.method == "archdisk_arcgis_point"


def test_non_archdisk_and_invalid_geometry_are_ignored() -> None:
    other = SourceItem(
        id="other:1",
        source_id="other",
        source_item_id="1",
        source_url="https://example.test",
        metadata_raw={"resolved_latitude": 40.7, "resolved_longitude": -74.0},
    )
    invalid = SourceItem(
        id="archdisk:bad",
        source_id="archdisk-911-photo-map",
        source_item_id="bad",
        source_url="https://archdisk.com/photomap",
        metadata_raw={"resolved_latitude": 1000, "resolved_longitude": -74.0},
    )
    assert derive_spatial_claims([other, invalid]) == []


def test_spatial_claim_serializer_uses_enum_values() -> None:
    item = SourceItem(
        id="archdisk:1",
        source_id="archdisk-911-photo-map",
        source_item_id="1",
        source_url="https://archdisk.com/photomap",
        metadata_raw={"resolved_latitude": 40.711, "resolved_longitude": -74.013},
    )
    claim = derive_spatial_claims([item])[0]
    payload = serialize_spatial_claim(claim)
    assert payload["location_kind"] == "capture_location"
    assert payload["status"] == "proposed"
