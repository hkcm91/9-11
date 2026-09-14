from __future__ import annotations

import json
import time
from dataclasses import asdict
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


class AdapterError(RuntimeError):
    """Raised when a source cannot be fetched or parsed safely."""


class September11DigitalArchiveAdapter:
    """Metadata-only adapter for the September 11 Digital Archive.

    The archive is an Omeka site whose item browser advertises JSON output.
    This adapter intentionally does not download item media. It retrieves only
    browse/item metadata and preserves the complete source payload on every
    SourceItem in ``metadata_raw``.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        request_delay_s: float = 1.0,
        timeout_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.request_delay_s = request_delay_s
        self.timeout_s = timeout_s
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        if self._last_request_at is None or self.request_delay_s <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.request_delay_s - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"

        req = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json,text/json;q=0.9,*/*;q=0.1",
            },
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310 - fixed public source
                body = response.read().decode("utf-8")
        except Exception as exc:  # urllib exposes several transport exceptions
            raise AdapterError(f"failed to fetch {url}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"source did not return valid JSON for {url}") from exc

    def fetch_browse_page(
        self,
        *,
        page: int = 1,
        collection_id: int | None = None,
        per_page: int | None = None,
    ) -> list[dict[str, Any]]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if per_page is not None and per_page < 1:
            raise ValueError("per_page must be >= 1")

        payload = self._get_json(
            "/items/browse",
            {
                "output": "json",
                "page": page,
                "collection": collection_id,
                "per_page": per_page,
            },
        )
        if not isinstance(payload, list):
            raise AdapterError("expected the Omeka browse JSON output to be a list")
        return [item for item in payload if isinstance(item, dict)]

    def iter_items(
        self,
        *,
        collection_id: int | None = None,
        start_page: int = 1,
        max_items: int | None = None,
        per_page: int | None = None,
        max_pages: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        emitted = 0
        page = start_page
        pages_seen = 0

        while True:
            if max_pages is not None and pages_seen >= max_pages:
                return
            batch = self.fetch_browse_page(
                page=page,
                collection_id=collection_id,
                per_page=per_page,
            )
            pages_seen += 1
            if not batch:
                return

            for item in batch:
                yield item
                emitted += 1
                if max_items is not None and emitted >= max_items:
                    return
            page += 1

    @staticmethod
    def _element_values(item: dict[str, Any]) -> dict[str, list[str]]:
        values: dict[str, list[str]] = {}
        element_texts = item.get("element_texts")
        if not isinstance(element_texts, list):
            return values

        for entry in element_texts:
            if not isinstance(entry, dict):
                continue
            element = entry.get("element") or {}
            if not isinstance(element, dict):
                continue
            name = element.get("name")
            text = entry.get("text")
            if not isinstance(name, str) or text is None:
                continue
            values.setdefault(name.strip().lower(), []).append(str(text).strip())
        return values

    @staticmethod
    def _first(values: dict[str, list[str]], *keys: str) -> str | None:
        for key in keys:
            found = values.get(key.lower())
            if found:
                return found[0]
        return None

    @staticmethod
    def _source_url(item: dict[str, Any], base_url: str) -> str:
        raw_url = item.get("url")
        if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
            return raw_url
        item_id = item.get("id")
        return f"{base_url}/items/show/{item_id}" if item_id is not None else f"{base_url}/items/browse"

    def normalize(self, item: dict[str, Any]) -> SourceItem:
        item_id = item.get("id")
        if item_id is None:
            raise AdapterError("Omeka item is missing its stable id")

        elements = self._element_values(item)
        title = self._first(elements, "title")
        description = self._first(elements, "description", "abstract")
        creator = self._first(elements, "creator", "contributor")
        date = self._first(elements, "date")
        location = self._first(elements, "spatial coverage", "coverage")
        rights = self._first(elements, "rights")

        # Some Omeka exports expose useful fields at top level. We only use
        # these as fallbacks; the untouched payload remains metadata_raw.
        title = title or _coerce_str(item.get("title"))
        creator = creator or _coerce_str(item.get("creator"))
        date = date or _coerce_str(item.get("date")) or _coerce_str(item.get("added"))

        return SourceItem(
            id=f"{SOURCE_ID}:{item_id}",
            source_id=SOURCE_ID,
            source_item_id=str(item_id),
            source_url=self._source_url(item, self.base_url),
            title_raw=title,
            description_raw=description,
            creator_raw=creator,
            date_raw=date,
            location_raw=location,
            rights_raw=rights,
            metadata_raw=item,
            ingested_at=datetime.now(timezone.utc),
        )

    def sample(self, *, limit: int = 50, collection_id: int | None = None) -> list[SourceItem]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return [
            self.normalize(item)
            for item in self.iter_items(collection_id=collection_id, max_items=limit)
        ]

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
