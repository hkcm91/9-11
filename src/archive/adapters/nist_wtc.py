from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from archive.models import SourceItem

SOURCE_ID = "nist-wtc-disaster-repository"
DEFAULT_LANDING_URL = "https://www.nist.gov/world-trade-center-investigation/photos-videos-and-simulations"
DEFAULT_USER_AGENT = "nine-eleven-archive/0.1 metadata-research; contact=https://github.com/hkcm91/9-11"

TARGET_LABELS = (
    "Organized Photos and Video Clips",
    "Original Video from Tapes",
    "Other Photos and Videos",
    "Images of Collected Steel",
    "Computer Simulations",
    "Fire Tests and Analysis",
)

_TARGET_LABEL_TOKENS = (
    ("organizedphotos", "Organized Photos and Video Clips"),
    ("originalvideo", "Original Video from Tapes"),
    ("otherphotos", "Other Photos and Videos"),
    ("imagesofcollectedsteel", "Images of Collected Steel"),
    ("computersimulations", "Computer Simulations"),
    ("firetests", "Fire Tests and Analysis"),
)


class NistWtcAdapterError(RuntimeError):
    pass


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = dict(attrs)
        if tag == "img" and self.current_href is not None and values.get("alt"):
            self.current_text.append(values["alt"] or "")
            return
        if tag != "a":
            return
        self.current_href = values.get("href")
        self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self.current_href is None:
            return
        text = " ".join("".join(self.current_text).split())
        self.links.append((text, self.current_href))
        self.current_href = None
        self.current_text = []


class NistWtcRepositoryAdapter:
    """Inventory the public NIST WTC repository entry points.

    NIST's public landing page points into a repository hosted in NIST's Google
    Workspace. This adapter intentionally inventories repository/category links
    only. It does not download photos, videos, documents, or Google Drive files.
    """

    def __init__(
        self,
        *,
        landing_url: str = DEFAULT_LANDING_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        request_delay_s: float = 0.5,
        timeout_s: float = 30.0,
    ) -> None:
        self.landing_url = landing_url
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

    def fetch_landing_html(self) -> str:
        self._throttle()
        req = Request(
            self.landing_url,
            headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"},
        )
        try:
            with urlopen(req, timeout=self.timeout_s) as response:  # noqa: S310 - fixed public source
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise NistWtcAdapterError(f"failed to fetch {self.landing_url}: {exc}") from exc
        finally:
            self._last_request_at = time.monotonic()

    @staticmethod
    def _stable_id(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _canonical_label(text: str) -> str | None:
        exact = {label.casefold(): label for label in TARGET_LABELS}.get(text.casefold())
        if exact:
            return exact
        compact = re.sub(r"[^a-z0-9]+", "", text.casefold())
        for token, label in _TARGET_LABEL_TOKENS:
            if token in compact:
                return label
        return None

    def extract_repository_links(self, html: str) -> list[dict[str, Any]]:
        parser = _AnchorParser()
        parser.feed(html)
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for text, href in parser.links:
            absolute = urljoin(self.landing_url, href)
            if absolute in seen:
                continue
            text_norm = " ".join(text.split())
            host = urlparse(absolute).netloc.lower()
            is_google_repository = (
                host.endswith("drive.google.com")
                or host.endswith("docs.google.com")
                or host.endswith("googledrive.nist.gov")
            )
            exact_label = {value.casefold(): value for value in TARGET_LABELS}.get(text_norm.casefold())
            label = exact_label or (self._canonical_label(text_norm) if is_google_repository else None)
            if label is None and not is_google_repository:
                continue
            seen.add(absolute)
            row = {
                "label": label or text_norm or host,
                "url": absolute,
                "host": host,
                "source_page": self.landing_url,
            }
            if label and text_norm and label != text_norm:
                row["source_label"] = text_norm
            results.append(row)

        # Some CMS/rendering changes can hide the actual repository hrefs from
        # server-side HTML. Preserve the documented category inventory anyway,
        # but point those fallback records to the authoritative landing page.
        found_labels = {row["label"] for row in results}
        for label in TARGET_LABELS:
            if label not in found_labels:
                results.append(
                    {
                        "label": label,
                        "url": f"{self.landing_url}#{label.lower().replace(' ', '-')}",
                        "host": urlparse(self.landing_url).netloc,
                        "source_page": self.landing_url,
                        "fallback": True,
                    }
                )
        return results

    def normalize(self, row: dict[str, Any]) -> SourceItem:
        url = str(row["url"])
        label = str(row.get("label") or "NIST WTC repository entry")
        return SourceItem(
            id=f"{SOURCE_ID}:{self._stable_id(url)}",
            source_id=SOURCE_ID,
            source_item_id=self._stable_id(url),
            source_url=url,
            title_raw=label,
            description_raw="Public NIST World Trade Center Disaster Investigation repository entry point.",
            rights_raw="Item-specific review required; NIST notes that repository materials may include third-party copyrighted material.",
            collection_raw="NIST World Trade Center Disaster Investigation Materials",
            media_type_raw="repository_entry",
            metadata_raw=row,
            ingested_at=datetime.now(timezone.utc),
        )

    def sample(self) -> list[SourceItem]:
        html = self.fetch_landing_html()
        return [self.normalize(row) for row in self.extract_repository_links(html)]

    @staticmethod
    def serialize_source_item(item: SourceItem) -> dict[str, Any]:
        value = asdict(item)
        value["ingested_at"] = item.ingested_at.isoformat()
        return value
