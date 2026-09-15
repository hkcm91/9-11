from __future__ import annotations

from archive.derived import derive_temporal_claims
from archive.heuristics import document_coverage_claim_from_title
from archive.models import SourceItem, TimeKind


def make_item(title: str) -> SourceItem:
    return SourceItem(
        id=f"item:{title}",
        source_id="september-11-digital-archive",
        source_item_id="1",
        source_url="https://example.test/1",
        title_raw=title,
    )


def test_fdny_date_range_becomes_document_coverage_claim() -> None:
    item = make_item("Incident Action Plan: 10/16/01 - 10/17/01")
    claim = document_coverage_claim_from_title(item)

    assert claim is not None
    assert claim.time_kind == TimeKind.DOCUMENT_COVERAGE
    assert claim.start_time is not None and claim.start_time.date().isoformat() == "2001-10-16"
    assert claim.end_time is not None and claim.end_time.date().isoformat() == "2001-10-17"
    assert claim.confidence == 0.99
    assert claim.method == "explicit_title_date_range"


def test_single_day_fdny_plan_becomes_single_day_coverage() -> None:
    claim = document_coverage_claim_from_title(make_item("Incident Action Plan: 10/28/01"))
    assert claim is not None
    assert claim.start_time is not None and claim.end_time is not None
    assert claim.start_time.date() == claim.end_time.date()


def test_generic_date_title_is_not_interpreted() -> None:
    assert document_coverage_claim_from_title(make_item("Photographs from 9/11/01")) is None


def test_derive_temporal_claims_keeps_raw_date_untouched() -> None:
    item = make_item("Incident Action Plan: 9/29/01 - 9/30/01")
    claims = derive_temporal_claims([item])

    assert len(claims) == 1
    assert item.date_raw is None
    assert claims[0].time_kind == TimeKind.DOCUMENT_COVERAGE
