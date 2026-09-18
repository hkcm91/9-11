from archive.adapters.wikileaks import WikiLeaksPlusDAdapter, WikiLeaksWarDiariesAdapter


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
