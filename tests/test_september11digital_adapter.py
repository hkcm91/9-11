from __future__ import annotations

from archive.adapters.september11digital import (
    SOURCE_ID,
    AdapterError,
    September11DigitalArchiveAdapter,
)


SAMPLE_ITEM = {
    "id": 12345,
    "url": "https://911digitalarchive.org/api/items/12345",
    "added": "2004-01-01T12:00:00+00:00",
    "element_texts": [
        {"element": {"name": "Title"}, "text": "A sample title"},
        {"element": {"name": "Creator"}, "text": "Jane Doe"},
        {"element": {"name": "Description"}, "text": "Original source description"},
        {"element": {"name": "Date"}, "text": "2001-09-11"},
        {"element": {"name": "Coverage"}, "text": "Lower Manhattan"},
        {"element": {"name": "Rights"}, "text": "Rights statement from source"},
    ],
    "files": {"count": 1, "url": "https://911digitalarchive.org/api/files?item=12345"},
}


def test_normalize_preserves_raw_payload() -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)

    item = adapter.normalize(SAMPLE_ITEM)

    assert item.id == f"{SOURCE_ID}:12345"
    assert item.source_item_id == "12345"
    assert item.title_raw == "A sample title"
    assert item.creator_raw == "Jane Doe"
    assert item.description_raw == "Original source description"
    assert item.date_raw == "2001-09-11"
    assert item.location_raw == "Lower Manhattan"
    assert item.rights_raw == "Rights statement from source"
    assert item.metadata_raw is SAMPLE_ITEM


def test_normalize_falls_back_to_top_level_fields() -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)
    item = adapter.normalize(
        {
            "id": 7,
            "title": "Fallback title",
            "creator": "Fallback creator",
            "added": "2005-02-03",
        }
    )

    assert item.title_raw == "Fallback title"
    assert item.creator_raw == "Fallback creator"
    assert item.date_raw == "2005-02-03"
    assert item.source_url.endswith("/items/show/7")


def test_missing_stable_id_is_rejected() -> None:
    adapter = September11DigitalArchiveAdapter(request_delay_s=0)

    try:
        adapter.normalize({"element_texts": []})
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
    item = adapter.normalize(SAMPLE_ITEM)

    payload = adapter.serialize_source_item(item)

    assert isinstance(payload["ingested_at"], str)
    assert payload["metadata_raw"]["id"] == 12345
