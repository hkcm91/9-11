from __future__ import annotations

from datetime import datetime, timezone

from archive.corpus import reconcile_source_snapshots
from archive.models import SourceItem


def make_item(*, item_id: str, title: str | None = None, creator: str | None = None, metadata=None, second: int = 0):
    return SourceItem(
        id=item_id,
        source_id="source",
        source_item_id=item_id,
        source_url=f"https://example.test/{item_id}",
        title_raw=title,
        creator_raw=creator,
        metadata_raw=metadata or {},
        ingested_at=datetime(2026, 1, 1, 0, 0, second, tzinfo=timezone.utc),
    )


def test_reconciliation_counts_same_source_item_once() -> None:
    search = make_item(item_id="item:1", title="Title", metadata={"identifier": "1"})
    detailed = make_item(
        item_id="item:1",
        title="Title",
        creator="Broadcaster",
        metadata={"identifier": "1", "_archive_metadata": {"contributor": "Broadcaster"}, "_file_summary": {"file_count": 3}},
        second=1,
    )

    reconciled = reconcile_source_snapshots([search, detailed])
    assert len(reconciled) == 1
    assert reconciled[0].creator_raw == "Broadcaster"
    assert "_file_summary" in reconciled[0].metadata_raw


def test_reconciliation_preserves_first_seen_order_across_unique_ids() -> None:
    a1 = make_item(item_id="a", title="A")
    b = make_item(item_id="b", title="B")
    a2 = make_item(item_id="a", title="A", creator="Richer")

    reconciled = reconcile_source_snapshots([a1, b, a2])
    assert [item.id for item in reconciled] == ["a", "b"]
    assert reconciled[0].creator_raw == "Richer"
