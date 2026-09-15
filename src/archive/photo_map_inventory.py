from __future__ import annotations

import argparse
import json
from pathlib import Path

from archive.adapters.arcgis_photo_map import ArcGisPhotoMapAdapter, ArcGisPhotoMapError


def inventory_photo_map(adapter: ArcGisPhotoMapAdapter) -> dict:
    layers = adapter.discover_feature_layers()
    report_layers: list[dict] = []
    for layer in layers:
        url = str(layer.get("url") or "")
        entry = {
            "web_map_id": layer.get("web_map_id"),
            "web_map_title": layer.get("web_map_title"),
            "layer_title": layer.get("layer_title"),
            "item_id": layer.get("item_id"),
            "url": url,
            "feature_count": None,
            "object_id_count": None,
            "count_error": None,
            "ids_error": None,
        }
        try:
            entry["feature_count"] = adapter.query_feature_count(url)
        except ArcGisPhotoMapError as exc:
            entry["count_error"] = str(exc)
        try:
            entry["object_id_count"] = len(adapter.query_object_ids(url))
        except ArcGisPhotoMapError as exc:
            entry["ids_error"] = str(exc)
        report_layers.append(entry)

    return {
        "app_id": adapter.app_id,
        "feature_layer_count": len(report_layers),
        "layers": report_layers,
        "total_features_reported": sum(
            int(layer["feature_count"])
            for layer in report_layers
            if isinstance(layer.get("feature_count"), int)
        ),
        "total_object_ids": sum(
            int(layer["object_id_count"])
            for layer in report_layers
            if isinstance(layer.get("object_id_count"), int)
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-photo-map-info")
    parser.add_argument("--app-id", default="1b7d4d22866b445881b181614e25d4d4")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = ArcGisPhotoMapAdapter(app_id=args.app_id, request_delay_s=args.delay)
    report = inventory_photo_map(adapter)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
