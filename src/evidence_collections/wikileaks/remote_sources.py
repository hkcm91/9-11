from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

CABLEGATE_ARCHIVE_ITEM = "wikileaks-cables-csv"
WAR_DIARY_ARCHIVE_ITEM = "WikileaksWarDiaryCsv"

CABLEGATE_FIELDS = [
    "row_id",
    "date",
    "reference",
    "origin",
    "classification",
    "references_to",
    "routing_header",
    "body",
]

WAR_DIARY_FIELDS = [
    "ReportKey",
    "DateOccurred",
    "Type",
    "Category",
    "TrackingNumber",
    "Title",
    "Summary",
    "Region",
    "AttackOn",
    "ComplexAttack",
    "ReportingUnit",
    "UnitName",
    "TypeOfUnit",
    "FriendlyWIA",
    "FriendlyKIA",
    "HostNationWIA",
    "HostNationKIA",
    "CivilianWIA",
    "CivilianKIA",
    "EnemyWIA",
    "EnemyKIA",
    "EnemyDetained",
    "MGRS",
    "Latitude",
    "Longitude",
    "OriginatorGroup",
    "UpdatedByGroup",
    "CCIR",
    "Sigact",
    "Affiliation",
    "DColor",
    "Classification",
]

USER_AGENT = "historical-evidence-engine/0.1 (+https://github.com/hkcm91/9-11)"


class BulkSourceError(RuntimeError):
    pass


def _open(url: str, *, timeout: float = 30.0):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    return urlopen(request, timeout=timeout)


def discover_archive_csv_url(archive_item: str, *, timeout: float = 30.0) -> str:
    metadata_url = f"https://archive.org/metadata/{archive_item}"
    try:
        with _open(metadata_url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise BulkSourceError(
            f"could not read Internet Archive metadata for {archive_item}: {exc}"
        ) from exc

    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise BulkSourceError(
            f"Internet Archive metadata for {archive_item} did not contain files"
        )

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
        raise BulkSourceError(f"no CSV file found in Internet Archive item {archive_item}")

    _, name = max(candidates, key=lambda row: row[0])
    return f"https://archive.org/download/{archive_item}/{quote(name)}"


def discover_cablegate_csv_url(*, timeout: float = 30.0) -> str:
    return discover_archive_csv_url(CABLEGATE_ARCHIVE_ITEM, timeout=timeout)


def discover_war_diary_csv_url(*, timeout: float = 30.0) -> str:
    return discover_archive_csv_url(WAR_DIARY_ARCHIVE_ITEM, timeout=timeout)


def stream_csv_sample(
    url: str,
    output: Path | str,
    *,
    limit: int = 100,
    timeout: float = 60.0,
    fieldnames: list[str] | None = None,
) -> dict[str, Any]:
    """Read only the first N CSV records and write a normalized local sample.

    If fieldnames are supplied, the remote CSV is treated as headerless. This
    is required for the historical Cablegate and Afghan War Diary dumps.
    """

    if limit < 1:
        raise ValueError("limit must be >= 1")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        response = _open(url, timeout=timeout)
    except Exception as exc:
        raise BulkSourceError(f"could not open bulk source {url}: {exc}") from exc

    count = 0
    resolved_fields: list[str] = []
    try:
        text_stream = io.TextIOWrapper(
            response,
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        )
        reader = csv.DictReader(text_stream, fieldnames=fieldnames)
        resolved_fields = list(reader.fieldnames or [])
        if not resolved_fields:
            raise BulkSourceError(f"bulk source had no usable CSV schema: {url}")

        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=resolved_fields,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in reader:
                if not any(str(value or "").strip() for value in row.values()):
                    continue
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
        "columns": resolved_fields,
        "remote_headerless": fieldnames is not None,
    }


def fetch_default_real_samples(
    output_dir: Path | str,
    *,
    limit: int = 100,
    timeout: float = 60.0,
) -> dict[str, dict[str, Any]]:
    """Fetch bounded real samples from full-schema public archive mirrors."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cablegate_url = discover_cablegate_csv_url(timeout=timeout)
    war_diary_url = discover_war_diary_csv_url(timeout=timeout)

    plusd = stream_csv_sample(
        cablegate_url,
        output_dir / "plusd.csv",
        limit=limit,
        timeout=timeout,
        fieldnames=CABLEGATE_FIELDS,
    )
    war = stream_csv_sample(
        war_diary_url,
        output_dir / "war-diaries.csv",
        limit=limit,
        timeout=timeout,
        fieldnames=WAR_DIARY_FIELDS,
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
            "canonical_source": "WikiLeaks Afghan War Diary, 2004-2010",
            "transport_mirror": "Internet Archive",
            "archive_item": WAR_DIARY_ARCHIVE_ITEM,
        },
    }
