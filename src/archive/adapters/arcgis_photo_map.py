from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator
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
    """Resolve the public archDisk ArcGIS app into geospatial photo metadata.

    Point features become evidence records and public ArcGIS attachments are
    preserved as remote media references. Building footprints and other context
    geometry remain UI reference layers rather than historical media records.
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
            with urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310
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
            try:
                item = self.fetch_item(item_id)
            except ArcGisPhotoMapError:
                # Instant Apps can retain stale/private item references.
                continue
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
                    try:
                        item = self.fetch_item(item_id)
                    except ArcGisPhotoMapError:
                        continue
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

    def _layer_zero_url(self, service_url: str) -> str:
        trimmed = service_url.rstrip("/")
        tail = trimmed.rsplit("/", 1)[-1]
        if tail.isdigit():
            return trimmed
        return f"{trimmed}/0"

    def query_feature_count(self, layer_url: str) -> int:
        endpoint = f"{self._layer_zero_url(layer_url)}/query"
        payload = self._get_json_url(
            endpoint,
            {"where": "1=1", "returnCountOnly": "true", "f": "json"},
        )
        count = payload.get("count") if isinstance(payload, dict) else None
        if not isinstance(count, int) or count < 0:
            raise ArcGisPhotoMapError("ArcGIS count query did not return a non-negative integer")
        return count

    def query_object_ids(self, layer_url: str) -> list[int | str]:
        """Return the complete stable object-id set, unaffected by transfer limits."""
        endpoint = f"{self._layer_zero_url(layer_url)}/query"
        payload = self._get_json_url(
            endpoint,
            {"where": "1=1", "returnIdsOnly": "true", "f": "json"},
        )
        object_ids = payload.get("objectIds") if isinstance(payload, dict) else None
        if not isinstance(object_ids, list):
            raise ArcGisPhotoMapError("ArcGIS ID query did not return objectIds")
        # Keep IDs exactly as the service returns them but deduplicate while
        # using string order as a stable fallback for mixed numeric/string IDs.
        unique: dict[str, int | str] = {}
        for object_id in object_ids:
            if isinstance(object_id, (int, str)) and str(object_id).strip():
                unique[str(object_id)] = object_id
        return [unique[key] for key in sorted(unique, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))]

    def query_features(
        self,
        layer_url: str,
        *,
        limit: int = 50,
        offset: int = 0,
        object_ids: list[int | str] | None = None,
    ) -> dict[str, Any]:
        if limit < 1 or limit > 2000:
            raise ValueError("limit must be between 1 and 2000")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        endpoint = f"{self._layer_zero_url(layer_url)}/query"
        params: dict[str, Any] = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "json",
        }
        if object_ids is not None:
            if not object_ids:
                return {"features": []}
            params["objectIds"] = ",".join(str(value) for value in object_ids)
        else:
            params["resultRecordCount"] = limit
            params["resultOffset"] = offset
        payload = self._get_json_url(endpoint, params)
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise ArcGisPhotoMapError("ArcGIS feature query did not return a features array")
        return payload

    @staticmethod
    def _layer_advertises_attachments(layer: dict[str, Any]) -> bool:
        raw_layer = layer.get("raw_layer") if isinstance(layer.get("raw_layer"), dict) else {}
        popup = raw_layer.get("popupInfo") if isinstance(raw_layer.get("popupInfo"), dict) else {}
        if popup.get("showAttachments") is True:
            return True
        elements = popup.get("popupElements")
        return isinstance(elements, list) and any(
            isinstance(element, dict) and element.get("type") == "attachments"
            for element in elements
        )

    def query_attachments(
        self,
        layer_url: str,
        object_ids: list[int | str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Return public media attachments keyed by parent object id.

        The archive stores remote ArcGIS URLs and metadata only; attachment
        bytes are never mirrored into the corpus.
        """
        if not object_ids:
            return {}
        endpoint = f"{self._layer_zero_url(layer_url)}/queryAttachments"
        payload = self._get_json_url(
            endpoint,
            {"objectIds": ",".join(str(value) for value in object_ids), "f": "json"},
        )
        groups = payload.get("attachmentGroups") if isinstance(payload, dict) else None
        if not isinstance(groups, list):
            raise ArcGisPhotoMapError("ArcGIS attachment query did not return attachmentGroups")

        base_url = self._layer_zero_url(layer_url)
        result: dict[str, list[dict[str, Any]]] = {}
        for group in groups:
            if not isinstance(group, dict):
                continue
            parent = group.get("parentObjectId")
            infos = group.get("attachmentInfos")
            if parent is None or not isinstance(infos, list):
                continue
            normalized: list[dict[str, Any]] = []
            for info in infos:
                if not isinstance(info, dict):
                    continue
                attachment_id = info.get("id")
                if attachment_id is None:
                    continue
                content_type = str(info.get("contentType") or "").strip()
                if not content_type.startswith(("image/", "video/", "audio/")):
                    continue
                normalized.append(
                    {
                        "id": attachment_id,
                        "name": str(info.get("name") or "").strip() or None,
                        "content_type": content_type or None,
                        "size": info.get("size"),
                        "url": f"{base_url}/{parent}/attachments/{attachment_id}",
                    }
                )
            if normalized:
                result[str(parent)] = normalized
        return result

    def iter_feature_pages(
        self,
        layer_url: str,
        *,
        page_size: int = 250,
    ) -> Iterator[dict[str, Any]]:
        """Yield complete feature pages, preferring stable ID chunks.

        `returnIdsOnly` is not subject to the normal feature transfer limit on
        ArcGIS services, so chunking the returned IDs prevents silent omission
        when the photo layer grows beyond the service's page size.
        """
        if page_size < 1 or page_size > 2000:
            raise ValueError("page_size must be between 1 and 2000")
        try:
            object_ids = self.query_object_ids(layer_url)
        except ArcGisPhotoMapError:
            object_ids = []

        if object_ids:
            for start in range(0, len(object_ids), page_size):
                chunk = object_ids[start : start + page_size]
                yield self.query_features(layer_url, limit=len(chunk), object_ids=chunk)
            return

        # Fallback for older/nonstandard services that do not support IDs-only.
        offset = 0
        while True:
            page = self.query_features(layer_url, limit=page_size, offset=offset)
            yield page
            features = page.get("features") or []
            if len(features) < page_size and not page.get("exceededTransferLimit"):
                return
            offset += len(features)
            if not features:
                return

    @staticmethod
    def _mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
        lon = x / 20037508.34 * 180.0
        lat = y / 20037508.34 * 180.0
        lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
        return lat, lon

    @classmethod
    def _geometry_wgs84(cls, geometry: Any, spatial_reference: Any = None) -> tuple[float | None, float | None]:
        if not cls._is_point_geometry(geometry):
            return None, None
        assert isinstance(geometry, dict)
        x, y = geometry.get("x"), geometry.get("y")
        sr = geometry.get("spatialReference") or spatial_reference or {}
        wkid = (sr.get("latestWkid") or sr.get("wkid")) if isinstance(sr, dict) else None
        if wkid in {3857, 102100, 102113}:
            return cls._mercator_to_wgs84(float(x), float(y))
        if wkid in {4326, 4269} or (-180 <= x <= 180 and -90 <= y <= 90):
            return float(y), float(x)
        return None, None

    @staticmethod
    def _is_point_geometry(geometry: Any) -> bool:
        return (
            isinstance(geometry, dict)
            and isinstance(geometry.get("x"), (int, float))
            and isinstance(geometry.get("y"), (int, float))
        )

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
        attachments: list[dict[str, Any]] | None = None,
    ) -> SourceItem:
        attrs = feature.get("attributes") if isinstance(feature.get("attributes"), dict) else {}
        geometry = feature.get("geometry")
        if not self._is_point_geometry(geometry):
            raise ArcGisPhotoMapError("photo-map feature is not point geometry")

        lat, lon = self._geometry_wgs84(geometry, spatial_reference)
        object_id = self._first_attr(attrs, ("OBJECTID", "FID", "ObjectId", "GlobalID"))
        stable_material = json.dumps([layer.get("url"), attrs, geometry], sort_keys=True, default=str)
        fallback_id = hashlib.sha256(stable_material.encode("utf-8")).hexdigest()[:20]
        source_item_id = f"{layer.get('item_id') or layer.get('web_map_id')}:{object_id or fallback_id}"

        # The current public archDisk layer uses Name for photographer, Address
        # for the mapped camera position, and timeTaken for source-supplied time.
        creator = self._first_attr(attrs, ("Photographer", "Creator", "Author", "Name", "Source", "Credit"))
        title = self._first_attr(attrs, ("Title", "Photo", "Filename", "FileName", "Name"))
        date = self._first_attr(attrs, ("Date", "PhotoDate", "CaptureDate", "timeTaken", "Time", "Timestamp"))
        address = self._first_attr(attrs, ("Address", "Location"))
        description = self._first_attr(attrs, ("notesExtended", "Description", "Caption", "Notes", "Comments"))
        rights = self._first_attr(attrs, ("Rights", "Copyright", "License", "Credit"))
        source_reference = self._first_attr(attrs, ("sourceURL", "SourceURL", "URL"))

        lowered_attrs = {str(key).lower(): value for key, value in attrs.items()}

        def flagged(name: str) -> bool:
            value = lowered_attrs.get(name.lower())
            return str(value or "").strip().lower() in {"1", "true", "yes", "y"}

        metadata = {
            "arcgis_feature": feature,
            "arcgis_layer": layer,
            "resolved_latitude": lat,
            "resolved_longitude": lon,
            "mapped_address": address,
            "external_source_url": source_reference,
            "time_taken_raw": self._first_attr(attrs, ("timeTaken",)),
            "folder_path": self._first_attr(attrs, ("FolderPath",)),
            "media_attachments": list(attachments or []),
            "sensitivity_flags": {
                "gore": flagged("containsGore"),
                "falling_person": flagged("containsFallingPerson"),
            },
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
            location_raw=address or (f"{lat:.7f},{lon:.7f}" if lat is not None and lon is not None else None),
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
        seen_ids: set[str] = set()
        for layer in layers:
            if len(records) >= limit:
                break
            try:
                # Larger ID lists exceed the hosted service's GET URL limit.
                # Keep both feature and attachment requests small at scale.
                pages = self.iter_feature_pages(str(layer["url"]), page_size=min(250, max(50, limit)))
                for payload in pages:
                    spatial_reference = payload.get("spatialReference")
                    features = payload["features"]
                    attachments_by_object: dict[str, list[dict[str, Any]]] = {}
                    if self._layer_advertises_attachments(layer):
                        object_ids = []
                        for candidate in features:
                            attrs = candidate.get("attributes") if isinstance(candidate, dict) else None
                            if not isinstance(attrs, dict):
                                continue
                            object_id = self._first_attr(attrs, ("OBJECTID", "FID", "ObjectId"))
                            if object_id is not None:
                                object_ids.append(object_id)
                        try:
                            attachments_by_object = self.query_attachments(str(layer["url"]), object_ids)
                        except ArcGisPhotoMapError:
                            # Metadata collection should remain useful even if
                            # a public attachment endpoint is temporarily down.
                            attachments_by_object = {}

                    for feature in features:
                        if len(records) >= limit:
                            break
                        if not isinstance(feature, dict) or not self._is_point_geometry(feature.get("geometry")):
                            continue
                        attrs = feature.get("attributes") if isinstance(feature.get("attributes"), dict) else {}
                        object_id = self._first_attr(attrs, ("OBJECTID", "FID", "ObjectId"))
                        try:
                            record = self.normalize_feature(
                                feature,
                                layer=layer,
                                spatial_reference=spatial_reference,
                                attachments=attachments_by_object.get(str(object_id), []),
                            )
                        except ArcGisPhotoMapError:
                            continue
                        if record.id in seen_ids:
                            continue
                        seen_ids.add(record.id)
                        records.append(record)
                    if len(records) >= limit:
                        break
            except ArcGisPhotoMapError:
                continue
        if not records:
            raise ArcGisPhotoMapError("public FeatureServer layers resolved but no point photo features were returned")
        return records

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value
