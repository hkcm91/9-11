from __future__ import annotations

from archive.adapters.internet_archive import (
    SOURCE_ID,
    InternetArchiveAdapter,
    InternetArchiveAdapterError,
)


def test_normalize_preserves_metadata() -> None:
    adapter = InternetArchiveAdapter(request_delay_s=0)
    raw = {
        "identifier": "sample-item",
        "title": "Sample broadcast",
        "creator": "Sample Network",
        "date": "2001-09-11",
        "description": "Archive description",
        "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
        "mediatype": "movies",
        "collection": ["911", "tvarchive", "fav-example"],
    }

    item = adapter.normalize(raw)

    assert item.id == f"{SOURCE_ID}:sample-item"
    assert item.source_item_id == "sample-item"
    assert item.title_raw == "Sample broadcast"
    assert item.creator_raw == "Sample Network"
    assert item.date_raw == "2001-09-11"
    assert item.rights_raw == "https://creativecommons.org/licenses/by/4.0/"
    assert item.collection_raw == "911"
    assert item.metadata_raw["collection"] == ["911", "tvarchive", "fav-example"]
    assert item.source_url.endswith("/details/sample-item")


def test_configured_collection_is_lineage_even_with_auxiliary_memberships() -> None:
    adapter = InternetArchiveAdapter(collection="TV-NHK", request_delay_s=0)
    item = adapter.normalize(
        {
            "identifier": "x",
            "collection": ["TV-NHK", "911", "tvarchive", "fav-someone"],
        }
    )
    assert item.collection_raw == "TV-NHK"


def test_list_values_are_joined() -> None:
    adapter = InternetArchiveAdapter(request_delay_s=0)
    item = adapter.normalize({"identifier": "x", "creator": ["A", "B"]})
    assert item.creator_raw == "A; B"


def test_missing_identifier_is_rejected() -> None:
    adapter = InternetArchiveAdapter(request_delay_s=0)
    try:
        adapter.normalize({"title": "No identifier"})
    except InternetArchiveAdapterError as exc:
        assert "identifier" in str(exc)
    else:
        raise AssertionError("expected InternetArchiveAdapterError")


def test_iter_items_stops_at_limit(monkeypatch) -> None:
    adapter = InternetArchiveAdapter(request_delay_s=0)
    calls: list[int] = []

    def fake_search(*, page: int, rows: int):
        calls.append(page)
        return [{"identifier": f"{page}-{i}"} for i in range(rows)]

    monkeypatch.setattr(adapter, "search_page", fake_search)
    results = list(adapter.iter_items(max_items=7, rows=5))

    assert len(results) == 7
    assert calls == [1, 2]
