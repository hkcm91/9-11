from __future__ import annotations

import csv
import gzip
import io
import json
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO
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
    accepted_suffixes = (".csv", ".csv.gz", ".csv.zip", ".csv.7z")
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name.lower().endswith(accepted_suffixes):
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        candidates.append((size, name))

    if not candidates:
        visible = [
            str(item.get("name") or "").strip()
            for item in files
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        preview = ", ".join(visible[:20])
        raise BulkSourceError(
            f"no CSV or compressed CSV payload found in Internet Archive item "
            f"{archive_item}; files={preview}"
        )

    _, name = max(candidates, key=lambda row: row[0])
    return f"https://archive.org/download/{archive_item}/{quote(name)}"


def discover_cablegate_csv_url(*, timeout: float = 30.0) -> str:
    return discover_archive_csv_url(CABLEGATE_ARCHIVE_ITEM, timeout=timeout)


def discover_war_diary_csv_url(*, timeout: float = 30.0) -> str:
    return discover_archive_csv_url(WAR_DIARY_ARCHIVE_ITEM, timeout=timeout)


@contextmanager
def _remote_csv_text_stream(
    url: str,
    *,
    timeout: float,
) -> Iterator[TextIO]:
    """Open plain or compressed remote CSV content as a text stream."""

    lower = url.lower()

    if lower.endswith(".csv"):
        response = _open(url, timeout=timeout)
        try:
            stream = io.TextIOWrapper(
                response,
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            )
            yield stream
        finally:
            try:
                response.close()
            except Exception:
                pass
        return

    if lower.endswith(".csv.gz"):
        response = _open(url, timeout=timeout)
        try:
            gz = gzip.GzipFile(fileobj=response)
            stream = io.TextIOWrapper(
                gz,
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            )
            yield stream
        finally:
            try:
                response.close()
            except Exception:
                pass
        return

    with tempfile.TemporaryDirectory(prefix="wikileaks-archive-") as temp_dir:
        temp_root = Path(temp_dir)
        archive_path = temp_root / Path(url).name

        try:
            response = _open(url, timeout=timeout)
            with archive_path.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
        except Exception as exc:
            raise BulkSourceError(f"could not download compressed bulk source {url}: {exc}") from exc
        finally:
            try:
                response.close()
            except Exception:
                pass

        extracted_csv: Path | None = None

        if lower.endswith(".csv.zip"):
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    csv_members = [
                        info
                        for info in archive.infolist()
                        if not info.is_dir() and info.filename.lower().endswith(".csv")
                    ]
                    if not csv_members:
                        raise BulkSourceError(f"ZIP contained no CSV file: {url}")
                    member = max(csv_members, key=lambda info: info.file_size)
                    archive.extract(member, path=temp_root)
                    extracted_csv = temp_root / member.filename
            except BulkSourceError:
                raise
            except Exception as exc:
                raise BulkSourceError(f"could not extract ZIP bulk source {url}: {exc}") from exc

        elif lower.endswith(".csv.7z"):
            try:
                import py7zr
            except ImportError as exc:
                raise BulkSourceError(
                    "reading .7z WikiLeaks archives requires the py7zr package"
                ) from exc

            try:
                with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                    names = [
                        name
                        for name in archive.getnames()
                        if name.lower().endswith(".csv")
                    ]
                    if not names:
                        raise BulkSourceError(f"7z archive contained no CSV file: {url}")
                    target = names[0]
                    archive.extract(path=temp_root, targets=[target])
                    extracted_csv = temp_root / target
            except BulkSourceError:
                raise
            except Exception as exc:
                raise BulkSourceError(f"could not extract 7z bulk source {url}: {exc}") from exc

        else:
            raise BulkSourceError(f"unsupported compressed CSV source: {url}")

        if extracted_csv is None or not extracted_csv.exists():
            raise BulkSourceError(f"CSV extraction produced no file: {url}")

        with extracted_csv.open(
            "r",
            encoding="utf-8-sig",
            errors="replace",
            newline="",
        ) as stream:
            yield stream


def stream_csv_sample(
    url: str,
    output: Path | str,
    *,
    limit: int = 100,
    timeout: float = 60.0,
    fieldnames: list[str] | None = None,
    required_any: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Read only the first N CSV records and write a normalized local sample.

    If fieldnames are supplied, the remote CSV is treated as headerless. This
    is required for the historical Cablegate and Afghan War Diary dumps.
    """

    if limit < 1:
        raise ValueError("limit must be >= 1")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    skipped_invalid = 0
    resolved_fields: list[str] = []

    try:
        with _remote_csv_text_stream(url, timeout=timeout) as text_stream:
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
                        skipped_invalid += 1
                        continue

                    if required_any and not any(
                        str(row.get(field) or "").strip() for field in required_any
                    ):
                        skipped_invalid += 1
                        continue

                    writer.writerow(dict(row))
                    count += 1
                    if count >= limit:
                        break
    except BulkSourceError:
        raise
    except Exception as exc:
        raise BulkSourceError(f"could not sample bulk source {url}: {exc}") from exc

    if count == 0:
        raise BulkSourceError(f"bulk source returned zero CSV records: {url}")

    return {
        "url": url,
        "output": str(output),
        "records": count,
        "columns": resolved_fields,
        "remote_headerless": fieldnames is not None,
        "skipped_invalid_rows": skipped_invalid,
        "required_any": list(required_any),
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
        required_any=("reference",),
    )
    war = stream_csv_sample(
        war_diary_url,
        output_dir / "war-diaries.csv",
        limit=limit,
        timeout=timeout,
        fieldnames=WAR_DIARY_FIELDS,
        required_any=("ReportKey", "TrackingNumber"),
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
