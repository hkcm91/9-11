from archive.dedupe import find_candidates
from archive.models import SourceItem


def item(*, item_id: str, source_id: str, title: str, creator: str | None = None,
         description: str | None = None, date: str | None = None) -> SourceItem:
    return SourceItem(
        id=f"{source_id}:{item_id}",
        source_id=source_id,
        source_item_id=item_id,
        source_url=f"https://example.test/{item_id}",
        title_raw=title,
        creator_raw=creator,
        description_raw=description,
        date_raw=date,
    )


def test_generic_broadcast_series_is_not_same_source_duplicate_by_default() -> None:
    first = item(
        item_id="nhk-0900",
        source_id="internet-archive-understanding-911",
        title="NHK News Broadcast",
        creator="NHK",
        description="Continuous television news coverage from Japan.",
        date="2001-09-11",
    )
    second = item(
        item_id="nhk-1300",
        source_id="internet-archive-understanding-911",
        title="NHK News Broadcast",
        creator="NHK",
        description="Continuous television news coverage from Japan.",
        date="2001-09-11",
    )

    assert find_candidates([first, second]) == []


def test_cross_source_same_object_can_be_proposed() -> None:
    left = item(
        item_id="a",
        source_id="archive-a",
        title="View of North Tower from West Broadway",
        creator="Jane Doe",
        description="Photograph of the North Tower from West Broadway after impact.",
        date="2001-09-11 09:48",
    )
    right = item(
        item_id="b",
        source_id="archive-b",
        title="View of North Tower from West Broadway",
        creator="Jane Doe",
        description="Photograph of the North Tower from West Broadway after impact.",
        date="2001-09-11 09:48",
    )

    candidates = find_candidates([left, right])
    assert len(candidates) == 1
    assert candidates[0].left_id == left.id
    assert candidates[0].right_id == right.id


def test_cross_source_title_only_similarity_is_not_enough() -> None:
    left = item(item_id="a", source_id="archive-a", title="World Trade Center")
    right = item(item_id="b", source_id="archive-b", title="World Trade Center")

    assert find_candidates([left, right]) == []


def test_same_source_strict_pass_requires_extra_evidence() -> None:
    first = item(
        item_id="a",
        source_id="archive-a",
        title="Exact photograph title",
        creator="Jane Doe",
        description="Exact description of one historical photograph.",
        date="2001-09-11 09:48",
    )
    second = item(
        item_id="b",
        source_id="archive-a",
        title="Exact photograph title",
        creator="Jane Doe",
        description="Exact description of one historical photograph.",
        date="2001-09-11 09:48",
    )

    candidates = find_candidates([first, second], include_same_source=True)
    assert len(candidates) == 1
