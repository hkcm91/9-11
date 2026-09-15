from __future__ import annotations

from archive.adapters.september11digital import (
    SOURCE_ID,
    AdapterError,
    September11DigitalArchiveAdapter,
)


SAMPLE_ENUM_ITEM = {
    "id": 12345,
    "collection_id": 267,
    "item_type_id": 30,
    "added": "2014-01-16 12:31:31",
}

SAMPLE_DCMES = b'''<?xml version="1.0" encoding="UTF-8"?>
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>A sample title</dc:title>
  <dc:creator>Jane Doe</dc:creator>
  <dc:description>Original source description</dc:description>
  <dc:date>2001-09-11</dc:date>
  <dc:coverage>Lower Manhattan</dc:coverage>
  <dc:rights>Rights statement from source</dc:rights>
  <dc:type>moving image</dc:type>
</oai_dc:dc>'''


def test_normalize_preserves_live_enumeration_metadata() -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    item = adapter.normalize(SAMPLE_ENUM_ITEM)

    assert item.id == f"{SOURCE_ID}:12345"
    assert item.source_item_id == "12345"
    assert item.source_url.endswith("/items/show/12345")
    assert item.date_raw is None
    assert item.archive_added_raw == "2014-01-16 12:31:31"
    assert item.collection_raw == "267"
    assert item.media_type_raw == "item_type_id:30"
    assert item.metadata_raw is SAMPLE_ENUM_ITEM


def test_fetch_browse_page_accepts_current_omeka_envelope(monkeypatch) -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    monkeypatch.setattr(
        adapter,
        "_get_json",
        lambda *args, **kwargs: {
            "items": [{"id": 96746, "collection_id": 267}, {"id": 96745, "collection_id": 267}],
            "total_results": 517,
        },
    )
    rows = adapter.fetch_browse_page(collection_id=267)
    assert [row["id"] for row in rows] == [96746, 96745]
    assert rows[0]["collection_id"] == 267


def test_fetch_dcmes_parses_repeating_dublin_core_fields(monkeypatch) -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    monkeypatch.setattr(adapter, "_get_bytes", lambda *args, **kwargs: SAMPLE_DCMES)
    values = adapter.fetch_dcmes(12345)
    assert values["title"] == ["A sample title"]
    assert values["creator"] == ["Jane Doe"]
    assert values["type"] == ["moving image"]


def test_enrich_promotes_historical_date_without_overwriting_archive_added(monkeypatch) -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    base = adapter.normalize(SAMPLE_ENUM_ITEM)
    monkeypatch.setattr(
        adapter,
        "fetch_dcmes",
        lambda item_id: {
            "title": ["A sample title"],
            "creator": ["Jane Doe"],
            "description": ["Original source description"],
            "date": ["2001-09-11"],
            "coverage": ["Lower Manhattan"],
            "rights": ["Rights statement from source"],
            "type": ["moving image"],
        },
    )

    item = adapter.enrich(base)
    assert item.title_raw == "A sample title"
    assert item.creator_raw == "Jane Doe"
    assert item.description_raw == "Original source description"
    assert item.date_raw == "2001-09-11"
    assert item.archive_added_raw == "2014-01-16 12:31:31"
    assert item.location_raw == "Lower Manhattan"
    assert item.rights_raw == "Rights statement from source"
    assert item.media_type_raw == "moving image"
    assert item.metadata_raw["_dcmes"]["title"] == ["A sample title"]
    assert base.metadata_raw is SAMPLE_ENUM_ITEM


def test_missing_stable_id_is_rejected() -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    try:
        adapter.normalize({})
    except AdapterError as exc:
        assert "stable id" in str(exc)
    else:
        raise AssertionError("expected AdapterError")


def test_iter_items_stops_at_limit_without_extra_pages(monkeypatch) -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    calls: list[int] = []

    def fake_fetch(*, page: int, collection_id=None, per_page=None):
        calls.append(page)
        return [{"id": page * 10 + i} for i in range(5)]

    monkeypatch.setattr(adapter, "fetch_browse_page", fake_fetch)
    items = list(adapter.iter_items(max_items=7))
    assert len(items) == 7
    assert calls == [1, 2]


def test_serialize_source_item_makes_timestamp_json_safe() -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    item = adapter.normalize(SAMPLE_ENUM_ITEM)
    payload = adapter.serialize_source_item(item)
    assert isinstance(payload["ingested_at"], str)
    assert payload["metadata_raw"]["id"] == 12345
