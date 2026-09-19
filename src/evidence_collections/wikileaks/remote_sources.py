from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

CABLEGATE_ARCHIVE_ITEM = "wikileaks-cables-csv"
CABLEGATE_METADATA_URL = f"https://archive.org/metadata/{CABLEGATE_ARCHIVE_ITEM}"
WAR_DIARIES_SAMPLE_URL = "https://raw.githubusercontent.com/FreGeh/iraq-war-logs/main/iraq1.csv"

USER_AGENT = "historical-evidence-engine/0.1 (+https://github.com/hkcm91/9-11)"


class BulkSourceError(RuntimeError):
    pass


def _open(url: str, *, timeout: float = 30.0):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    return urlopen(request, timeout=timeout)


def discover_cablegate_csv_url(*, timeout: float = 30.0) -> str:
    """Resolve a CSV payload from the Internet Archive Cablegate item at runtime."""

    try:
        with _open(CABLEGATE_METADATA_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise BulkSourceError(f"could not read Cablegate Internet Archive metadata: {exc}") from exc

    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise BulkSourceError("Cablegate Internet Archive metadata did not contain files")

    candidates: list[tuple[int, str]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name.lower().endswith(".csv"):
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        candidates.append((size, name))

    if not candidates:
        raise BulkSourceError("no CSV file found in the Cablegate Internet Archive item")

    # Prefer the largest CSV because derived/checksum CSVs, when present, are
    # usually much smaller than the actual cable export.
    _, name = max(candidates, key=lambda row: row[0])
    return f"https://archive.org/download/{CABLEGATE_ARCHIVE_ITEM}/{quote(name)}"


def stream_csv_sample(
    url: str,
    output: Path | str,
    *,
    limit: int = 100,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Read only the first N CSV records from a remote source and write a local sample."""

    if limit < 1:
        raise ValueError("limit must be >= 1")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = _open(url, timeout=timeout)
    except Exception as exc:
        raise BulkSourceError(f"could not open bulk source {url}: {exc}") from exc

    count = 0
    fieldnames: list[str] | None = None
    try:
        # newline="" is important for CSV fields containing embedded newlines.
        text_stream = io.TextIOWrapper(response, encoding="utf-8-sig", errors="replace", newline="")
        reader = csv.DictReader(text_stream)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise BulkSourceError(f"bulk source had no CSV header: {url}")

        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in reader:
                writer.writerow(dict(row))
                count += 1
                if count >= limit:
                    break
    finally:
        try:
            response.close()
        except Exception:
            pass

    if count == 0:
        raise BulkSourceError(f"bulk source returned zero CSV records: {url}")

    return {
        "url": url,
        "output": str(output),
        "records": count,
        "columns": fieldnames,
    }


def fetch_default_real_samples(
    output_dir: Path | str,
    *,
    limit: int = 100,
    timeout: float = 60.0,
) -> dict[str, dict[str, Any]]:
    """Fetch bounded real-data samples from stable public mirrors.

    Cablegate remains canonically attributed to WikiLeaks; the Internet Archive
    copy is used here as a transport mirror. War Diaries uses a public parsed CSV
    mirror for validation only. Source URLs are returned for provenance.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cablegate_url = discover_cablegate_csv_url(timeout=timeout)
    plusd = stream_csv_sample(
        cablegate_url,
        output_dir / "plusd.csv",
        limit=limit,
        timeout=timeout,
    )
    war = stream_csv_sample(
        WAR_DIARIES_SAMPLE_URL,
        output_dir / "war-diaries.csv",
        limit=limit,
        timeout=timeout,
    )

    return {
        "plusd": {
            **plusd,
            "canonical_source": "WikiLeaks Cablegate / PlusD",
            "transport_mirror": "Internet Archive",
            "archive_item": CABLEGATE_ARCHIVE_ITEM,
        },
        "war_diaries": {
            **war,
            "canonical_source": "WikiLeaks Iraq War Logs",
            "transport_mirror": "FreGeh/iraq-war-logs GitHub mirror",
        },
    }
