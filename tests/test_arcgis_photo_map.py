from __future__ import annotations

from archive.adapters.arcgis_photo_map import ArcGisPhotoMapAdapter


def test_candidate_ids_are_found_recursively() -> None:
    payload = {
        "values": {
            "webmap": "0123456789abcdef0123456789abcdef",
            "nested": [{"itemId": "fedcba9876543210fedcba9876543210"}],
        }
    }
    found = ArcGisPhotoMapAdapter._candidate_ids(payload)
    assert found == {
        "0123456789abcdef0123456789abcdef",
        "fedcba9876543210fedcba9876543210",
    }


def test_web_mercator_conversion_is_close_to_lower_manhattan() -> None:
    # Approximate Web Mercator coordinates for lower Manhattan.
    lat, lon = ArcGisPhotoMapAdapter._geometry_wgs84(
        {"x": -8238307.34, "y": 4970071.58},
        {"wkid": 102100},
    )
    assert lat is not None and lon is not None
    assert 40.6 < lat < 40.9
    assert -74.2 < lon < -73.8


def test_normalize_feature_preserves_geometry_and_creator() -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    feature = {
        "attributes": {
            "OBJECTID": 42,
            "Photographer": "Jane Example",
            "Caption": "Looking south",
            "Date": "2001-09-11",
        },
        "geometry": {"x": -74.01, "y": 40.71, "spatialReference": {"wkid": 4326}},
    }
    layer = {
        "web_map_id": "0123456789abcdef0123456789abcdef",
        "item_id": "fedcba9876543210fedcba9876543210",
        "url": "https://services.arcgis.com/example/FeatureServer/0",
        "layer_title": "Photos",
    }

    item = adapter.normalize_feature(feature, layer=layer)

    assert item.creator_raw == "Jane Example"
    assert item.description_raw == "Looking south"
    assert item.date_raw == "2001-09-11"
    assert item.location_raw == "40.7100000,-74.0100000"
    assert item.media_type_raw == "photo"
    assert item.source_item_id.endswith(":42")


def test_feature_id_fallback_is_deterministic() -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    feature = {"attributes": {"Photographer": "Anonymous"}, "geometry": {"x": -74.0, "y": 40.7}}
    layer = {"web_map_id": "0123456789abcdef0123456789abcdef", "url": "https://example.test/FeatureServer/0"}

    first = adapter.normalize_feature(feature, layer=layer)
    second = adapter.normalize_feature(feature, layer=layer)
    assert first.source_item_id == second.source_item_id
