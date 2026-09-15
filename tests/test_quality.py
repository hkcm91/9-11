from __future__ import annotations

from archive.models import SourceItem
from archive.quality import prioritize_item, prioritize_records


def make_item(**kwargs) -> SourceItem:
    base = dict(
        id="x",
        source_id="september-11-digital-archive",
        source_item_id="1",
        source_url="https://example.test/1",
    )
    base.update(kwargs)
    return SourceItem(**base)


def test_missing_time_and_location_raise_priority() -> None:
    sparse = make_item(title_raw="A title")
    rich = make_item(
        id="y",
        source_item_id="2",
        title_raw="A title",
        creator_raw="A creator",
        date_raw="2001-09-11 09:58",
        location_raw="West Street",
        rights_raw="Known",
        collection_raw="Collection",
        media_type_raw="video",
        description_raw="Description",
    )

    sparse_priority = prioritize_item(sparse)
    rich_priority = prioritize_item(rich)

    assert sparse_priority.enrichment_priority > rich_priority.enrichment_priority
    assert "missing historical time/date" in sparse_priority.reasons
    assert "missing map location" in sparse_priority.reasons


def test_nist_and_file_metadata_are_explained() -> None:
    item = make_item(
        metadata_raw={
            "_nist_normalized": {"time_uncertainty_seconds": 3},
            "_file_summary": {"file_count": 4},
        }
    )
    result = prioritize_item(item)
    assert "NIST structured visual metadata available" in result.reasons
    assert "media-file metadata available for deeper analysis" in result.reasons


def test_prioritize_records_sorts_highest_first() -> None:
    sparse = make_item(id="sparse", source_item_id="1", title_raw="Only title")
    rich = make_item(
        id="rich",
        source_item_id="2",
        title_raw="Title",
        creator_raw="Creator",
        date_raw="2001-09-11",
        location_raw="NYC",
        rights_raw="Known",
        collection_raw="Collection",
        media_type_raw="photo",
        description_raw="Description",
    )
    results = prioritize_records([rich, sparse])
    assert results[0].item_id == "sparse"
