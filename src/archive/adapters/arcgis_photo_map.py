from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from archive.models import SourceItem

SOURCE_ID = "archdisk-911-photo-map"
DEFAULT_APP_ID = "1b7d4d22866b445881b181614e25d4d4"
DEFAULT_ARCGIS_ROOT = "https://www.arcgis.com/sharing/rest"
DEFAULT_USER_AGENT = "nine-eleven-archive/0.1 metadata-research; contact=https://github.com/hkcm91/9-11"
_ITEM_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")


class ArcGisPhotoMapError(RuntimeError):
    pass


class ArcGisPhotoMapAdapter:
    """Resolve a public ArcGIS Instant App into geospatial feature metadata.

    The adapter is intentionally attachment-free: it inventories app/web-map
    structure and queries point-feature attributes + geometry only. Photograph
    attachments remain at the custodial source unless a later rights-aware
    stage explicitly decides otherwise.
    """

    def __init__(
        self,
        *,
        app_id: str = DEFAULT_APP_ID,
        arcgis_root: str = DEFAULT_ARCGIS_ROOT,
        user_agent: str = DEFAULT_USER_AGENT,
        request_delay_s: float = 0.25,
        timeout_s: float = 30.0,
    ) -> None:
        if not _ITEM_ID_RE.match(app_id):
            raise ValueError("app_id must be a 32-character ArcGIS item id")
        self.app_id = app_id
        self.arcgis_root = arcgis_root.rstrip("/")
        self.user_agent = user_agent
        self.request_delay_s = request_delay_s
        self.timeout_s = timeout_s
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        if self._last_request_at is None or self.request_delay_s <= 0:
            return
        remaining = self.request_delay_s - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _get_json_url(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        query = urlencode(params or {}, doseq=True)
        request_url = f"{url}{'&' if '?' in url else '?'}{query}" if query else url
        req = Request(request_url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310 - public configured endpoints
                body = response.read().decode("utf-8")
        except Exception as exc:
            raise ArcGisPhotoMapError(f"failed to fetch {request_url}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ArcGisPhotoMapError(f"ArcGIS endpoint did not return JSON: {request_url}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise ArcGisPhotoMapError(f"ArcGIS error for {request_url}: {payload['error']}")
        return payload

    def fetch_item(self, item_id: str) -> dict[str, Any]:
        payload = self._get_json_url(f"{self.arcgis_root}/content/items/{item_id}", {"f": "json"})
        if not isinstance(payload, dict):
            raise ArcGisPhotoMapError("ArcGIS item response must be an object")
        return payload

    def fetch_item_data(self, item_id: str) -> dict[str, Any]:
        payload = self._get_json_url(f"{self.arcgis_root}/content/items/{item_id}/data", {"f": "json"})
        if not isinstance(payload, dict):
            raise ArcGisPhotoMapError("ArcGIS item-data response must be an object")
        return payload

    @staticmethod
    def _candidate_ids(value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for nested in value.values():
                found.update(ArcGisPhotoMapAdapter._candidate_ids(nested))
        elif isinstance(value, list):
            for nested in value:
                found.update(ArcGisPhotoMapAdapter._candidate_ids(nested))
        elif isinstance(value, str) and _ITEM_ID_RE.match(value.strip()):
            found.add(value.strip())
        return found

    def discover_web_maps(self) -> list[dict[str, Any]]:
        app_data = self.fetch_item_data(self.app_id)
        candidates = self._candidate_ids(app_data)
        results: list[dict[str, Any]] = []
        for item_id in sorted(candidates):
            item = self.fetch_item(item_id)
            if str(item.get("type") or "").lower() == "web map":
                results.append(item)
        return results

    @staticmethod
    def _walk_layers(value: Any) -> Iterable[dict[str, Any]]:
        if not isinstance(value, dict):
            return
        layers = value.get("operationalLayers")
        if isinstance(layers, list):
            for layer in layers:
                if isinstance(layer, dict):
                    yield layer
                    yield from ArcGisPhotoMapAdapter._walk_layers(layer)
        nested = value.get("layers")
        if isinstance(nested, list):
            for layer in nested:
                if isinstance(layer, dict):
                    yield layer
                    yield from ArcGisPhotoMapAdapter._walk_layers(layer)

    def discover_feature_layers(self) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for web_map in self.discover_web_maps():
            web_map_id = str(web_map.get("id"))
            data = self.fetch_item_data(web_map_id)
            for layer in self._walk_layers(data):
                url = layer.get("url")
                item_id = layer.get("itemId")
                if isinstance(url, str) and "featureserver" in url.lower():
                    key = url.rstrip("/")
                    found[key] = {
                        "web_map_id": web_map_id,
                        "web_map_title": web_map.get("title"),
                        "layer_title": layer.get("title"),
                        "item_id": item_id,
                        "url": key,
                        "raw_layer": layer,
                    }
                elif isinstance(item_id, str) and _ITEM_ID_RE.match(item_id):
                    item = self.fetch_item(item_id)
                    service_url = item.get("url")
                    if isinstance(service_url, str) and "featureserver" in service_url.lower():
                        key = service_url.rstrip("/")
                        found[key] = {
                            "web_map_id": web_map_id,
                            "web_map_title": web_map.get("title"),
                            "layer_title": layer.get("title") or item.get("title"),
                            "item_id": item_id,
                            "url": key,
                            "raw_layer": layer,
                            "raw_item": item,
                        }
        return list(found.values())

    @staticmethod
    def _layer_zero_url(service_url: str) -> str:
        trimmed = service_url.rstrip("/")
        tail = trimmed.rsplit("/", 1)[-1]
        return trimmed if tail.isdigit() else f"{trimmed}/0"

    def query_features(self, layer_url: str, *, limit: int = 50) -> dict[str, Any]:
        if limit < 1 or limit > 2000:
            raise ValueError("limit must be between 1 and 2000")
        endpoint = f"{self._layer_zero_url(layer_url)}/query"
        payload = self._get_json_url(
            endpoint,
            {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "resultRecordCount": limit,
                "f": "json",
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise ArcGisPhotoMapError("ArcGIS feature query did not return a features array")
        return payload

    @staticmethod
    def _mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
        lon = x / 20037508.34 * 180.0
        lat = y / 20037508.34 * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return lat, lon

    @classmethod
    def _geometry_wgs84(cls, geometry: Any, spatial_reference: Any = None) -> tuple[float | None, float | None]:
        if not isinstance(geometry, dict):
            return None, None
        x, y = geometry.get("x"), geometry.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None, None
        sr = geometry.get("spatialReference") or spatial_reference or {}
        wkid = (sr.get("latestWkid") or sr.get("wkid")) if isinstance(sr, dict) else None
        if wkid in {3857, 102100, 102113}:
            return cls._mercator_to_wgs84(float(x), float(y))
        if wkid in {4326, 4269} or (-180 <= x <= 180 and -90 <= y <= 90):
            return float(y), float(x)
        return None, None

    @staticmethod
    def _first_attr(attrs: dict[str, Any], names: tuple[str, ...]) -> str | None:
        lowered = {str(k).lower(): v for k, v in attrs.items()}
        for name in names:
            value = lowered.get(name.lower())
            if value not in (None, ""):
                return str(value).strip() or None
        return None

    def normalize_feature(
        self,
        feature: dict[str, Any],
        *,
        layer: dict[str, Any],
        spatial_reference: Any = None,
    ) -> SourceItem:
        attrs = feature.get("attributes") if isinstance(feature.get("attributes"), dict) else {}
        geometry = feature.get("geometry")
        lat, lon = self._geometry_wgs84(geometry, spatial_reference)
        object_id = self._first_attr(attrs, ("OBJECTID", "FID", "ObjectId", "GlobalID"))
        stable_material = json.dumps([layer.get("url"), attrs, geometry], sort_keys=True, default=str)
        fallback_id = hashlib.sha256(stable_material.encode("utf-8")).hexdigest()[:20]
        source_item_id = f"{layer.get('item_id') or layer.get('web_map_id')}:{object_id or fallback_id}"
        title = self._first_attr(attrs, ("Title", "Name", "Photo", "Photographer", "Filename", "FileName"))
        creator = self._first_attr(attrs, ("Photographer", "Creator", "Author", "Source", "Credit"))
        date = self._first_attr(attrs, ("Date", "PhotoDate", "CaptureDate", "Time", "Timestamp"))
        description = self._first_attr(attrs, ("Description", "Caption", "Notes", "Comments"))
        rights = self._first_attr(attrs, ("Rights", "Copyright", "License", "Credit"))
        metadata = {
            "arcgis_feature": feature,
            "arcgis_layer": layer,
            "resolved_latitude": lat,
            "resolved_longitude": lon,
        }
        return SourceItem(
            id=f"{SOURCE_ID}:{source_item_id}",
            source_id=SOURCE_ID,
            source_item_id=source_item_id,
            source_url="https://archdisk.com/photomap",
            title_raw=title,
            description_raw=description,
            creator_raw=creator,
            date_raw=date,
            location_raw=(f"{lat:.7f},{lon:.7f}" if lat is not None and lon is not None else None),
            rights_raw=rights,
            collection_raw="archDisk 9/11 Photo Map",
            media_type_raw="photo",
            metadata_raw=metadata,
            ingested_at=datetime.now(timezone.utc),
        )

    def sample(self, *, limit: int = 50) -> list[SourceItem]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        layers = self.discover_feature_layers()
        if not layers:
            raise ArcGisPhotoMapError("no public FeatureServer layer could be resolved from the ArcGIS app")
        records: list[SourceItem] = []
        remaining = limit
        for layer in layers:
            if remaining <= 0:
                break
            payload = self.query_features(str(layer["url"]), limit=remaining)
            spatial_reference = payload.get("spatialReference")
            for feature in payload["features"]:
                if not isinstance(feature, dict):
                    continue
                records.append(self.normalize_feature(feature, layer=layer, spatial_reference=spatial_reference))
                remaining -= 1
                if remaining <= 0:
                    break
        return records

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value
