from __future__ import annotations

import csv
import json

from archive.quality import prioritize_item
from historical_engine.collection_registry import get_collection
from historical_engine.work_queue import tasks_for_item
from evidence_collections.wikileaks.adapters import (
    WikiLeaksPlusDAdapter,
    WikiLeaksWarDiariesAdapter,
    load_tabular_records,
)


def test_wikileaks_collection_is_registered() -> None:
    collection = get_collection("wikileaks")
    assert collection.id == "wikileaks"
    assert {source.id for source in collection.sources()} == {
        "wikileaks-plusd",
        "wikileaks-war-diaries",
    }


def test_plusd_record_maps_to_shared_source_item() -> None:
    item = WikiLeaksPlusDAdapter().normalize(
        {
            "reference": "09STATE122615_a",
            "subject": "SAMPLE CABLE SUBJECT",
            "origin": "Secretary of State, Washington",
            "destinations": ["Embassy Cairo"],
            "date": "2009-11-30",
            "classification": "UNCLASSIFIED",
            "tags": ["PHUM", "PREL"],
            "references_to": ["06CAIRO2202", "07CAIRO2202"],
        }
    )
    assert item.source_id == "wikileaks-plusd"
    assert item.media_type_raw == "document"
    assert item.metadata_raw["references_to"] == ["06CAIRO2202", "07CAIRO2202"]


def test_plusd_accepts_common_bulk_export_headers(tmp_path) -> None:
    path = tmp_path / "cables.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["MRN", "SUBJECT", "FROM", "TO", "DATE", "CLASSIFICATION", "TAGS", "REF", "CONTENT"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "MRN": "09STATE122615_a",
                "SUBJECT": "Sample subject",
                "FROM": "STATE",
                "TO": "CAIRO|LONDON",
                "DATE": "2009-11-30",
                "CLASSIFICATION": "UNCLASSIFIED",
                "TAGS": "PHUM|PREL",
                "REF": "06CAIRO2202|07CAIRO2202",
                "CONTENT": "Sample cable body.",
            }
        )

    item = WikiLeaksPlusDAdapter().import_file(path)[0]
    assert item.creator_raw == "STATE"
    assert item.metadata_raw["destinations"] == ["CAIRO", "LONDON"]
    assert item.metadata_raw["tags"] == ["PHUM", "PREL"]
    assert item.description_raw == "Sample cable body."


def test_war_diary_is_collection_specific_event_record() -> None:
    item = WikiLeaksWarDiariesAdapter().normalize(
        {
            "ReportKey": "ABC-123",
            "TrackingNumber": "TRACK-001",
            "Title": "TEST INCIDENT",
            "Summary": "Narrative text",
            "Region": "MND-BAGHDAD",
            "ReportingUnit": "UNIT X",
            "MGRS": "38SMB123456",
            "Classification": "SECRET",
        }
    )
    collection = get_collection("wikileaks")

    assert collection.classify_record(item) == "event_record"
    assert item.location_raw is None
    assert item.metadata_raw["mgrs"] == "38SMB123456"

    priority = prioritize_item(item, collection=collection)
    tasks = {task.task_type: task for task in tasks_for_item(item, collection, priority)}

    assert tasks["resolve_location"].expected_claim_kind == "event_location"
    assert tasks["resolve_location"].requires_human_review is True
    assert "original grid/location notation" in tasks["resolve_location"].instructions


def test_json_object_with_records_is_supported(tmp_path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps({"records": [{"id": "one"}, {"id": "two"}]}), encoding="utf-8")
    assert [row["id"] for row in load_tabular_records(path, limit=1)] == ["one"]
