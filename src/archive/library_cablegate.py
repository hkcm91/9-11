"""Bounded Cablegate transport using the repository's existing real-source adapter."""
import json
import re
from pathlib import Path

from archive.library_sources import file_digest
from archive.document_library import now
from evidence_collections.wikileaks.adapters import WikiLeaksPlusDAdapter
from evidence_collections.wikileaks.remote_sources import (
    CABLEGATE_FIELDS, discover_cablegate_csv_url, stream_csv_sample,
)

def valid_cable_row(row: dict) -> bool:
    return (None not in row and all(isinstance(row.get(field), str) for field in CABLEGATE_FIELDS)
        and bool(re.fullmatch(r"\d{2}[A-Z]+\d+(?:_a)?", row["reference"].strip()))
        and bool(row["body"].strip()) and "\ufffd" not in row["body"])


def fetch_cablegate(library, output: Path, limit: int = 1000) -> dict:
    if not 1 <= limit <= 10000:
        raise ValueError("Use a bounded batch between 1 and 10,000 records")
    output.mkdir(parents=True, exist_ok=True)
    url = discover_cablegate_csv_url()
    csv_path = output / "cablegate.csv"
    transport = stream_csv_sample(url, csv_path, limit=limit,
        fieldnames=CABLEGATE_FIELDS, required_any=("reference",), row_filter=valid_cable_row,
        escapechar="\\", strict_csv=True)
    sha = file_digest(csv_path)
    transport.update(transport_mirror="Internet Archive", archive_item="wikileaks-cables-csv",
        fetched_at=now(),
        normalized_csv_sha256=sha, validation="backslash-escaped-strict-csv-v2",
        coverage_note="Bounded sample from mirror; not the entire Cablegate release")
    (output / "transport.json").write_text(json.dumps(transport, indent=2), encoding="utf-8")
    adapter = WikiLeaksPlusDAdapter()
    normalized = output / "cablegate.jsonl"
    with normalized.open("w", encoding="utf-8") as handle:
        for item in adapter.import_file(csv_path):
            reference = item.metadata_raw["reference"].strip()
            reference = reference if reference.endswith("_a") else reference + "_a"
            item.source_url = f"https://wikileaks.org/plusd/cables/{reference}.html"
            item.metadata_raw["content_kind"] = "full_mirror_text"
            item.metadata_raw["transport_url"] = url
            item.metadata_raw["transport_sample_sha256"] = sha
            item.metadata_raw["transport_sample_records"] = transport["records"]
            record = adapter.serialize_source_item(item)
            # Retrieval time lives in transport.json and source observations, not
            # in document identity: re-fetching identical rows must not fork versions.
            record.pop("ingested_at", None)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    results = library.import_records(normalized, "wikileaks", "cablegate-ia-fulltext-v2")
    return {"sampled": transport["records"], "processed": sum(row["status"] == "processed" for row in results),
        "failed": sum(row["status"] == "failed" for row in results),
        "publication": "unpublished; pending source review", "transport": transport}
