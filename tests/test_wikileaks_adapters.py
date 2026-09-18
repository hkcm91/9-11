import csv
import json

from archive.adapters.wikileaks import (
    WikiLeaksPlusDAdapter,
    WikiLeaksWarDiariesAdapter,
    load_tabular_records,
)
from archive.quality import EnrichmentPriority
from archive.work_queue import tasks_for_item


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
            "source_url": "https://www.wikileaks.org/plusd/cables/09STATE122615_a.html",
        }
    )

    assert item.source_id == "wikileaks-plusd"
    assert item.source_item_id == "09STATE122615_a"
    assert item.media_type_raw == "document"
    assert item.date_raw == "2009-11-30"
    assert item.metadata_raw["classification"] == "UNCLASSIFIED"
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

    records = WikiLeaksPlusDAdapter().import_file(path)
    assert len(records) == 1
    item = records[0]
    assert item.creator_raw == "STATE"
    assert item.metadata_raw["destinations"] == ["CAIRO", "LONDON"]
    assert item.metadata_raw["tags"] == ["PHUM", "PREL"]
    assert item.metadata_raw["references_to"] == ["06CAIRO2202", "07CAIRO2202"]
    assert item.description_raw == "Sample cable body."


def test_war_diary_record_maps_to_event_oriented_source_item() -> None:
    item = WikiLeaksWarDiariesAdapter().normalize(
        {
            "public_id": "1B1110F6-B914-2120-2FF934168143F1D2",
            "tracking_number": "20070422193038RMA9170036600",
            "release": "Iraq",
            "type": "Enemy Action",
            "category": "Indirect Fire",
            "region": "MND-C",
            "reporting_unit": "MND CS LNO",
            "unit_name": "FOB ECHO",
            "unit_type": "Coalition Forces",
            "total_casualties": 4,
            "friendly_wounded": 1,
            "friendly_killed": 1,
            "civilian_wounded": 1,
            "civilian_killed": 1,
            "mgrs": "38RMA917366",
            "classification": "SECRET",
            "affiliation": "ENEMY",
            "title": "INDIRECT FIRE (Rocket) ON FOB ECHO",
            "event_time": "2007-04-22 17:30:00",
            "narrative": "Rocket attack took place on Camp ECHO.",
        }
    )

    assert item.source_id == "wikileaks-war-diaries"
    assert item.source_item_id == "1B1110F6-B914-2120-2FF934168143F1D2"
    assert item.media_type_raw == "event_record"
    assert item.date_raw == "2007-04-22 17:30:00"
    assert item.metadata_raw["category"] == "Indirect Fire"
    assert item.metadata_raw["casualties"]["total"] == 4
    assert "38RMA917366" in item.location_raw


def test_war_diary_accepts_original_style_headers(tmp_path) -> None:
    path = tmp_path / "war.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ReportKey", "TrackingNumber", "Title", "Summary", "Type", "Category",
                "Region", "ReportingUnit", "TypeOfUnit", "FriendlyKIA", "CivilianKIA",
                "MGRS", "Classification",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ReportKey": "ABC-123",
                "TrackingNumber": "TRACK-001",
                "Title": "TEST INCIDENT",
                "Summary": "Narrative text",
                "Type": "Enemy Action",
                "Category": "Direct Fire",
                "Region": "MND-BAGHDAD",
                "ReportingUnit": "UNIT X",
                "TypeOfUnit": "Coalition Forces",
                "FriendlyKIA": "1",
                "CivilianKIA": "2",
                "MGRS": "38SMB123456",
                "Classification": "SECRET",
            }
        )

    item = WikiLeaksWarDiariesAdapter().import_file(path)[0]
    assert item.source_item_id == "ABC-123"
    assert item.creator_raw == "UNIT X"
    assert item.metadata_raw["casualties"]["friendly_killed"] == "1"
    assert item.metadata_raw["casualties"]["civilian_killed"] == "2"


def test_event_record_generates_event_semantic_research_tasks() -> None:
    item = WikiLeaksWarDiariesAdapter().normalize(
        {
            "ReportKey": "ABC-123",
            "TrackingNumber": "TRACK-001",
            "Title": "TEST INCIDENT",
            "Summary": "Narrative",
            "Region": "MND-BAGHDAD",
        }
    )
    priority = EnrichmentPriority(
        item_id=item.id,
        source_id=item.source_id,
        completeness_score=0.2,
        enrichment_priority=1.0,
        missing_fields=["date_raw", "location_raw", "creator_raw"],
        present_fields=["title_raw", "description_raw"],
        reasons=["fixture"],
    )
    tasks = {task.task_type: task for task in tasks_for_item(item, priority)}

    assert tasks["resolve_time"].record_role == "event_record"
    assert tasks["resolve_time"].expected_claim_kind == "event_time"
    assert tasks["resolve_location"].expected_claim_kind == "event_location"


def test_json_object_with_records_is_supported(tmp_path) -> None:
    path = tmp_path / "records.json"
    path.write_text(json.dumps({"records": [{"id": "one"}, {"id": "two"}]}), encoding="utf-8")
    assert [row["id"] for row in load_tabular_records(path, limit=1)] == ["one"]
