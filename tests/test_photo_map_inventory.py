from __future__ import annotations

from archive.photo_map_inventory import inventory_photo_map


class FakeAdapter:
    app_id = "1b7d4d22866b445881b181614e25d4d4"

    def discover_feature_layers(self):
        return [
            {
                "web_map_id": "map-a",
                "web_map_title": "9/11 Photo Map",
                "layer_title": "Photos",
                "item_id": "layer-a",
                "url": "https://example.test/FeatureServer/0",
            },
            {
                "web_map_id": "map-a",
                "web_map_title": "9/11 Photo Map",
                "layer_title": "Context",
                "item_id": "layer-b",
                "url": "https://example.test/FeatureServer/1",
            },
        ]

    def query_feature_count(self, url: str):
        return 517 if url.endswith("/0") else 7

    def query_object_ids(self, url: str):
        return list(range(self.query_feature_count(url)))


def test_inventory_summarizes_layer_counts() -> None:
    report = inventory_photo_map(FakeAdapter())

    assert report["feature_layer_count"] == 2
    assert report["total_features_reported"] == 524
    assert report["total_object_ids"] == 524
    assert report["layers"][0]["feature_count"] == 517
    assert report["layers"][1]["object_id_count"] == 7
