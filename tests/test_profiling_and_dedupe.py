from __future__ import annotations

from archive.dedupe import compare, find_candidates
from archive.models import SourceItem
from archive.profiling import profile_records


def _item(identifier: str, **kwargs) -> SourceItem:
    return SourceItem(
        id=identifier,
        source_id=kwargs.pop("source_id", "source-a"),
        source_item_id=identifier,
        source_url=f"https://example.test/{identifier}",
        **kwargs,
    )


def test_profile_records_counts_field_coverage() -> None:
    profile = profile_records([
        _item("1", title_raw="One", creator_raw="A", metadata_raw={"title": "One"}),
        _item("2", title_raw="Two", description_raw="Desc", metadata_raw={"title": "Two", "files": []}),
    ])

    assert profile.total_records == 2
    assert profile.populated_counts["title_raw"] == 2
    assert profile.populated_percent["creator_raw"] == 50.0
    assert profile.raw_metadata_keys["title"] == 2


def test_compare_proposes_close_metadata_without_declaring_duplicate() -> None:
    left = _item(
        "a",
        title_raw="View of North Tower after impact",
        creator_raw="Jane Smith",
        description_raw="Looking south from West Broadway",
    )
    right = _item(
        "b",
        source_id="source-b",
        title_raw="View of North Tower after impact",
        creator_raw="Jane Smith",
        description_raw="Looking south from West Broadway.",
    )

    candidate = compare(left, right)
    assert candidate.score > 0.9
    assert "near-identical title" in candidate.reasons


def test_find_candidates_ignores_unrelated_records() -> None:
    rows = [
        _item("a", title_raw="North Tower photograph", creator_raw="A"),
        _item("b", title_raw="Pentagon oral history", creator_raw="B"),
    ]
    assert find_candidates(rows) == []
