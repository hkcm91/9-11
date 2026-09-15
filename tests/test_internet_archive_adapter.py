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
    item = adapter.normalize({"identifier": "x", "collection": ["TV-NHK", "911", "tvarchive", "fav-someone"]})
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


def test_file_summary_tracks_formats_originals_and_lengths() -> None:
    payload = {
        "files": [
            {"name": "a.mp4", "format": "MPEG4", "source": "original", "length": "00:30:00"},
            {"name": "a.ogv", "format": "Ogg Video", "source": "derivative", "length": "1800"},
        ]
    }
    summary = InternetArchiveAdapter._file_summary(payload)

    assert summary["file_count"] == 2
    assert summary["original_file_count"] == 1
    assert summary["formats"] == ["MPEG4", "Ogg Video"]
    assert summary["duration_candidates"] == ["00:30:00", "1800"]


def test_enrich_search_item_merges_full_metadata(monkeypatch) -> None:
    adapter = InternetArchiveAdapter(request_delay_s=0)

    def fake_fetch(identifier: str):
        assert identifier == "sample-item"
        return {
            "metadata": {"identifier": identifier, "title": "Detailed title", "date": "2001-09-11"},
            "files": [{"format": "MPEG4", "source": "original", "length": "60"}],
        }

    monkeypatch.setattr(adapter, "fetch_item_metadata", fake_fetch)
    enriched = adapter.enrich_search_item({"identifier": "sample-item", "title": "Search title"})

    assert enriched["title"] == "Detailed title"
    assert enriched["_file_summary"]["original_file_count"] == 1
