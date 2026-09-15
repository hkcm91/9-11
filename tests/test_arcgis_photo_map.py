from __future__ import annotations

import pytest

from archive.adapters.arcgis_photo_map import ArcGisPhotoMapAdapter, ArcGisPhotoMapError


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


def test_current_archdisk_fields_promote_name_address_and_time() -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    feature = {
        "attributes": {
            "OBJECTID": 7,
            "Name": "John Labriola",
            "Address": "Washington St.",
            "timeTaken": "07:40:00",
            "sourceURL": "https://example.test/source",
            "notesExtended": "Mapped from a published photo sequence.",
        },
        "geometry": {"x": -8239153.2582, "y": 4969697.5296},
    }
    layer = {
        "web_map_id": "0123456789abcdef0123456789abcdef",
        "url": "https://services.arcgis.com/example/FeatureServer/0",
    }

    item = adapter.normalize_feature(feature, layer=layer, spatial_reference={"wkid": 102100})

    assert item.creator_raw == "John Labriola"
    assert item.location_raw == "Washington St."
    assert item.date_raw == "07:40:00"
    assert item.description_raw == "Mapped from a published photo sequence."
    assert item.metadata_raw["external_source_url"] == "https://example.test/source"


def test_polygon_context_feature_is_not_normalized_as_photo() -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    feature = {
        "attributes": {"OBJECTID": 8, "Name": "WTC5"},
        "geometry": {"rings": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    }
    layer = {"web_map_id": "0123456789abcdef0123456789abcdef", "url": "https://example.test/FeatureServer/0"}

    with pytest.raises(ArcGisPhotoMapError):
        adapter.normalize_feature(feature, layer=layer)


def test_feature_id_fallback_is_deterministic() -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    feature = {"attributes": {"Photographer": "Anonymous"}, "geometry": {"x": -74.0, "y": 40.7}}
    layer = {"web_map_id": "0123456789abcdef0123456789abcdef", "url": "https://example.test/FeatureServer/0"}

    first = adapter.normalize_feature(feature, layer=layer)
    second = adapter.normalize_feature(feature, layer=layer)
    assert first.source_item_id == second.source_item_id


def test_feature_count_and_object_ids_use_transfer_limit_safe_queries(monkeypatch) -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    calls: list[dict] = []

    def fake_get(url: str, params=None):
        calls.append(dict(params or {}))
        if params and params.get("returnCountOnly") == "true":
            return {"count": 517}
        if params and params.get("returnIdsOnly") == "true":
            return {"objectIdFieldName": "OBJECTID", "objectIds": [3, 1, 2, 2]}
        raise AssertionError("unexpected query")

    monkeypatch.setattr(adapter, "_get_json_url", fake_get)

    assert adapter.query_feature_count("https://example.test/FeatureServer/0") == 517
    assert adapter.query_object_ids("https://example.test/FeatureServer/0") == [1, 2, 3]
    assert calls[0]["returnCountOnly"] == "true"
    assert calls[1]["returnIdsOnly"] == "true"


def test_iter_feature_pages_chunks_complete_object_id_set(monkeypatch) -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    monkeypatch.setattr(adapter, "query_object_ids", lambda url: [1, 2, 3, 4, 5])
    requested: list[list[int | str]] = []

    def fake_query(layer_url: str, *, limit=50, offset=0, object_ids=None):
        requested.append(list(object_ids or []))
        return {
            "features": [
                {"attributes": {"OBJECTID": value}, "geometry": {"x": -74.0, "y": 40.7}}
                for value in (object_ids or [])
            ]
        }

    monkeypatch.setattr(adapter, "query_features", fake_query)
    pages = list(adapter.iter_feature_pages("https://example.test/FeatureServer/0", page_size=2))

    assert requested == [[1, 2], [3, 4], [5]]
    assert [len(page["features"]) for page in pages] == [2, 2, 1]


def test_iter_feature_pages_falls_back_to_offsets_when_ids_unavailable(monkeypatch) -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)

    def no_ids(url: str):
        raise ArcGisPhotoMapError("ids unsupported")

    monkeypatch.setattr(adapter, "query_object_ids", no_ids)
    offsets: list[int] = []

    def fake_query(layer_url: str, *, limit=50, offset=0, object_ids=None):
        offsets.append(offset)
        count = 2 if offset == 0 else 1
        return {
            "features": [
                {"attributes": {"OBJECTID": offset + i}, "geometry": {"x": -74.0, "y": 40.7}}
                for i in range(count)
            ]
        }

    monkeypatch.setattr(adapter, "query_features", fake_query)
    pages = list(adapter.iter_feature_pages("https://example.test/FeatureServer/0", page_size=2))

    assert offsets == [0, 2]
    assert [len(page["features"]) for page in pages] == [2, 1]


def test_sample_reads_across_multiple_feature_pages(monkeypatch) -> None:
    adapter = ArcGisPhotoMapAdapter(request_delay_s=0)
    layer = {
        "web_map_id": "0123456789abcdef0123456789abcdef",
        "url": "https://example.test/FeatureServer/0",
    }
    monkeypatch.setattr(adapter, "discover_feature_layers", lambda: [layer])

    def fake_pages(url: str, *, page_size: int):
        yield {
            "features": [
                {"attributes": {"OBJECTID": 1, "Name": "A"}, "geometry": {"x": -74.0, "y": 40.70}},
                {"attributes": {"OBJECTID": 2, "Name": "B"}, "geometry": {"x": -74.0, "y": 40.71}},
            ]
        }
        yield {
            "features": [
                {"attributes": {"OBJECTID": 3, "Name": "C"}, "geometry": {"x": -74.0, "y": 40.72}},
            ]
        }

    monkeypatch.setattr(adapter, "iter_feature_pages", fake_pages)
    records = adapter.sample(limit=3)

    assert [record.creator_raw for record in records] == ["A", "B", "C"]
    assert len({record.id for record in records}) == 3
