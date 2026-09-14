from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from archive.models import SourceItem


SOURCE_ID = "september-11-digital-archive"
DEFAULT_BASE_URL = "https://911digitalarchive.org"
DEFAULT_USER_AGENT = (
    "nine-eleven-archive/0.1 metadata-research; "
    "contact=https://github.com/hkcm91/9-11"
)
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"


class AdapterError(RuntimeError):
    """Raised when a source cannot be fetched or parsed safely."""


class September11DigitalArchiveAdapter:
    """Metadata-first adapter for the September 11 Digital Archive.

    Browse JSON is used only to enumerate stable IDs/collection IDs. Richer
    descriptive metadata is fetched on demand through each item's DCMES XML
    export. Archive import timestamps remain separate from historical dates.
    """

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL, user_agent: str = DEFAULT_USER_AGENT,
                 request_delay_s: float = 1.0, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
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

    def _get_bytes(self, path: str, params: dict[str, Any] | None = None, *, accept: str = "*/*") -> bytes:
        self._throttle()
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        req = Request(url, headers={"User-Agent": self.user_agent, "Accept": accept})
        try:
            with urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310
                return response.read()
        except Exception as exc:
            raise AdapterError(f"failed to fetch {url}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        body = self._get_bytes(path, params, accept="application/json,text/json;q=0.9,*/*;q=0.1")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterError(f"source did not return valid JSON for {path}") from exc

    def fetch_browse_page(self, *, page: int = 1, collection_id: int | None = None,
                          per_page: int | None = None) -> list[dict[str, Any]]:
        if page < 1:
            raise ValueError("page must be >= 1")
        payload = self._get_json("/items/browse", {
            "output": "json", "page": page, "collection": collection_id, "per_page": per_page,
        })
        if isinstance(payload, dict):
            payload = payload.get("items")
        if not isinstance(payload, list):
            raise AdapterError("expected Omeka browse JSON items list")
        return [item for item in payload if isinstance(item, dict)]

    def iter_items(self, *, collection_id: int | None = None, start_page: int = 1,
                   max_items: int | None = None, per_page: int | None = None,
                   max_pages: int | None = None) -> Iterable[dict[str, Any]]:
        emitted = 0
        page = start_page
        pages_seen = 0
        while True:
            if max_pages is not None and pages_seen >= max_pages:
                return
            batch = self.fetch_browse_page(page=page, collection_id=collection_id, per_page=per_page)
            pages_seen += 1
            if not batch:
                return
            for item in batch:
                yield item
                emitted += 1
                if max_items is not None and emitted >= max_items:
                    return
            page += 1

    def fetch_dcmes(self, item_id: str | int) -> dict[str, list[str]]:
        body = self._get_bytes(
            f"/items/show/{item_id}", {"output": "dcmes-xml"},
            accept="application/rdf+xml,application/xml,text/xml;q=0.9,*/*;q=0.1",
        )
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError(f"invalid DCMES XML for item {item_id}") from exc
        values: dict[str, list[str]] = {}
        for element in root.iter():
            if not isinstance(element.tag, str) or not element.tag.startswith(f"{{{DC_NAMESPACE}}}"):
                continue
            key = element.tag.split("}", 1)[1].lower()
            text = (element.text or "").strip()
            if text:
                values.setdefault(key, []).append(text)
        return values

    @staticmethod
    def _first_map(values: dict[str, list[str]], *keys: str) -> str | None:
        for key in keys:
            found = values.get(key.lower())
            if found:
                return found[0]
        return None

    @staticmethod
    def _collection_value(item: dict[str, Any]) -> str | None:
        collection = item.get("collection")
        if isinstance(collection, dict):
            label = collection.get("name") or collection.get("title") or collection.get("id")
            return _coerce_str(label)
        if collection is not None:
            return _coerce_str(collection)
        return _coerce_str(item.get("collection_id"))

    def normalize(self, item: dict[str, Any]) -> SourceItem:
        item_id = item.get("id")
        if item_id is None:
            raise AdapterError("Omeka item is missing its stable id")
        return SourceItem(
            id=f"{SOURCE_ID}:{item_id}",
            source_id=SOURCE_ID,
            source_item_id=str(item_id),
            source_url=f"{self.base_url}/items/show/{item_id}",
            title_raw=_coerce_str(item.get("title")),
            creator_raw=_coerce_str(item.get("creator")),
            date_raw=_coerce_str(item.get("date")),
            archive_added_raw=_coerce_str(item.get("added")),
            collection_raw=self._collection_value(item),
            media_type_raw=(f"item_type_id:{item['item_type_id']}" if item.get("item_type_id") is not None else None),
            metadata_raw=item,
            ingested_at=datetime.now(timezone.utc),
        )

    def enrich(self, item: SourceItem) -> SourceItem:
        dc = self.fetch_dcmes(item.source_item_id)
        metadata = dict(item.metadata_raw)
        metadata["_dcmes"] = dc
        return replace(
            item,
            title_raw=item.title_raw or self._first_map(dc, "title"),
            description_raw=item.description_raw or self._first_map(dc, "description"),
            creator_raw=item.creator_raw or self._first_map(dc, "creator", "contributor"),
            date_raw=item.date_raw or self._first_map(dc, "date"),
            location_raw=item.location_raw or self._first_map(dc, "coverage"),
            rights_raw=item.rights_raw or self._first_map(dc, "rights"),
            media_type_raw=(self._first_map(dc, "type") or item.media_type_raw),
            metadata_raw=metadata,
        )

    def sample(self, *, limit: int = 50, collection_id: int | None = None,
               enrich: bool = False) -> list[SourceItem]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        records = [self.normalize(item) for item in self.iter_items(collection_id=collection_id, max_items=limit)]
        if enrich:
            records = [self.enrich(item) for item in records]
        return records

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip() or None
    return None
