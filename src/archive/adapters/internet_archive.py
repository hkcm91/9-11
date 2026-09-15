from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from archive.models import SourceItem

SOURCE_ID = "internet-archive-understanding-911"
DEFAULT_BASE_URL = "https://archive.org"
DEFAULT_USER_AGENT = "nine-eleven-archive/0.1 metadata-research; contact=https://github.com/hkcm91/9-11"


class InternetArchiveAdapterError(RuntimeError):
    pass


class InternetArchiveAdapter:
    def __init__(self, *, collection: str = "911", base_url: str = DEFAULT_BASE_URL,
                 user_agent: str = DEFAULT_USER_AGENT, request_delay_s: float = 0.5,
                 timeout_s: float = 30.0) -> None:
        self.collection = collection
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

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        query = urlencode(params or {}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        req = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except Exception as exc:
            raise InternetArchiveAdapterError(f"failed to fetch {url}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise InternetArchiveAdapterError(f"invalid JSON returned for {url}") from exc

    def search_page(self, *, page: int = 1, rows: int = 50) -> list[dict[str, Any]]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if rows < 1 or rows > 1000:
            raise ValueError("rows must be between 1 and 1000")
        payload = self._get_json("/advancedsearch.php", {
            "q": f"collection:{self.collection}",
            "fl[]": ["identifier", "title", "creator", "date", "description", "rights",
                     "licenseurl", "mediatype", "collection", "publicdate"],
            "rows": rows, "page": page, "output": "json",
        })
        response = payload.get("response") if isinstance(payload, dict) else None
        docs = response.get("docs") if isinstance(response, dict) else None
        if not isinstance(docs, list):
            raise InternetArchiveAdapterError("expected response.docs list from Internet Archive search")
        return [doc for doc in docs if isinstance(doc, dict)]

    def iter_items(self, *, max_items: int | None = None, rows: int = 50) -> Iterable[dict[str, Any]]:
        emitted = 0
        page = 1
        while True:
            batch = self.search_page(page=page, rows=rows)
            if not batch:
                return
            for item in batch:
                yield item
                emitted += 1
                if max_items is not None and emitted >= max_items:
                    return
            if len(batch) < rows:
                return
            page += 1

    def fetch_item_metadata(self, identifier: str) -> dict[str, Any]:
        if not identifier.strip():
            raise ValueError("identifier is required")
        payload = self._get_json(f"/metadata/{identifier.strip()}")
        if not isinstance(payload, dict):
            raise InternetArchiveAdapterError("expected item metadata object")
        return payload

    @staticmethod
    def _string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            return "; ".join(str(v) for v in value if v is not None) or None
        if isinstance(value, (str, int, float, bool)):
            return str(value).strip() or None
        return None

    @staticmethod
    def _file_summary(payload: dict[str, Any]) -> dict[str, Any]:
        files = payload.get("files")
        if not isinstance(files, list):
            return {"file_count": 0, "formats": [], "duration_candidates": []}
        formats: set[str] = set()
        durations: list[str] = []
        original_count = 0
        for file in files:
            if not isinstance(file, dict):
                continue
            fmt = file.get("format")
            if isinstance(fmt, str) and fmt.strip():
                formats.add(fmt.strip())
            if file.get("source") == "original":
                original_count += 1
            length = file.get("length")
            if isinstance(length, (str, int, float)) and str(length).strip():
                durations.append(str(length).strip())
        return {
            "file_count": len(files),
            "original_file_count": original_count,
            "formats": sorted(formats),
            "duration_candidates": durations[:25],
        }

    def enrich_search_item(self, item: dict[str, Any]) -> dict[str, Any]:
        identifier = self._string(item.get("identifier"))
        if not identifier:
            raise InternetArchiveAdapterError("Internet Archive item is missing identifier")
        payload = self.fetch_item_metadata(identifier)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        merged = dict(item)
        merged.update(metadata)
        merged["_archive_metadata"] = metadata
        merged["_file_summary"] = self._file_summary(payload)
        return merged

    def normalize(self, item: dict[str, Any]) -> SourceItem:
        identifier = self._string(item.get("identifier"))
        if not identifier:
            raise InternetArchiveAdapterError("Internet Archive item is missing identifier")
        rights = self._string(item.get("rights")) or self._string(item.get("licenseurl"))
        return SourceItem(
            id=f"{SOURCE_ID}:{identifier}",
            source_id=SOURCE_ID,
            source_item_id=identifier,
            source_url=f"{self.base_url}/details/{identifier}",
            title_raw=self._string(item.get("title")),
            description_raw=self._string(item.get("description")),
            creator_raw=self._string(item.get("creator")),
            date_raw=self._string(item.get("date")),
            archive_added_raw=self._string(item.get("publicdate")),
            rights_raw=rights,
            collection_raw=self.collection,
            media_type_raw=self._string(item.get("mediatype")),
            metadata_raw=item,
            ingested_at=datetime.now(timezone.utc),
        )

    def sample(self, *, limit: int = 50, enrich: bool = False) -> list[SourceItem]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        records: list[SourceItem] = []
        for item in self.iter_items(max_items=limit):
            if enrich:
                item = self.enrich_search_item(item)
            records.append(self.normalize(item))
        return records

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value
