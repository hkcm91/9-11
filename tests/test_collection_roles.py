"""Role classification: the riskiest part of the refactor.

The original ``_record_role`` was one ordered ``if`` chain that interleaved
September 11 tests with generic media tests. These tests pin the order, so a
future rearrangement that looks harmless but changes an answer fails loudly.
"""

from __future__ import annotations

import pytest

from archive.models import SourceItem
from historical_engine.collection import BaseCollection
from historical_engine.collection_registry import get_collection


def _item(**kwargs) -> SourceItem:
    payload = {
        "id": "item:1",
        "source_id": "some-source",
        "source_item_id": "1",
        "source_url": "https://example.test/1",
    }
    payload.update(kwargs)
    return SourceItem(**payload)


@pytest.fixture()
def september11():
    return get_collection("september11")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"source_id": "internet-archive-understanding-911"}, "broadcast"),
        ({"source_id": "archdisk-911-photo-map"}, "photo"),
        ({"source_id": "nist-wtc-disaster-repository"}, "repository"),
        (
            {"source_id": "september-11-digital-archive", "metadata_raw": {"collection_id": 11}},
            "document",
        ),
        (
            {"source_id": "september-11-digital-archive", "metadata_raw": {"collection_id": 267}},
            "testimony",
        ),
        (
            {"source_id": "september-11-digital-archive", "metadata_raw": {"collection_id": 266}},
            "audio",
        ),
        ({"title_raw": "Incident Action Plan: 9/14/01 - 9/15/01"}, "document"),
        ({"collection_raw": "Voices of 9.11"}, "testimony"),
        ({"collection_raw": "Sonic Memorial Project"}, "audio"),
    ],
)
def test_september11_specific_roles(september11, kwargs, expected) -> None:
    assert september11.classify_record(_item(**kwargs)) == expected


@pytest.mark.parametrize(
    ("media", "expected"),
    [
        ("repository_entry", "repository"),
        ("application/pdf", "document"),
        ("oral_history", "testimony"),
        ("sound recording", "audio"),
        ("still image", "photo"),
        ("video/mp4", "video"),
        ("", "unknown"),
    ],
)
def test_generic_roles_need_no_collection_knowledge(media, expected) -> None:
    generic = BaseCollection(id="generic", name="Generic")
    assert generic.classify_record(_item(media_type_raw=media)) == expected


def test_image_beats_film_as_it_always_has() -> None:
    """Preserved Phase-0 quirk, pinned deliberately.

    "moving image film" matches the photo rule first because `image` is tested
    before `film`. That is how the pipeline has always classified it, so
    changing it would silently reclassify existing corpora.
    """

    generic = BaseCollection(id="generic", name="Generic")
    assert generic.classify_record(_item(media_type_raw="moving image film")) == "photo"


def test_generic_collection_does_not_know_september11_sources() -> None:
    """9/11 knowledge must not leak into the engine's default behaviour."""

    generic = BaseCollection(id="generic", name="Generic")
    assert generic.classify_record(_item(source_id="archdisk-911-photo-map")) == "unknown"
    assert (
        generic.classify_record(_item(source_id="internet-archive-understanding-911")) == "unknown"
    )
    assert generic.classify_record(_item(collection_raw="Voices of 9.11")) == "unknown"


def test_generic_document_media_still_beats_a_later_collection_rule(september11) -> None:
    """Ordering guard.

    A PDF inside a "Voices of 9.11" collection was a *document* in the original
    chain, because the generic document-media rule sits above the Voices rule.
    Hoisting all collection rules to the top would silently make it testimony.
    """

    item = _item(media_type_raw="application/pdf", collection_raw="Voices of 9.11")
    assert september11.classify_record(item) == "document"


def test_source_rule_still_beats_generic_media(september11) -> None:
    """The mirror case: a source-level rule does sit above generic media."""

    item = _item(source_id="archdisk-911-photo-map", media_type_raw="moving image")
    assert september11.classify_record(item) == "photo"


def test_unrecognized_digital_archive_collection_falls_through(september11) -> None:
    item = _item(
        source_id="september-11-digital-archive",
        metadata_raw={"collection_id": 9999},
        media_type_raw="still image",
    )
    assert september11.classify_record(item) == "photo"


def test_junk_collection_id_does_not_raise(september11) -> None:
    item = _item(
        source_id="september-11-digital-archive",
        metadata_raw={"collection_id": "not-a-number"},
        media_type_raw="still image",
    )
    assert september11.classify_record(item) == "photo"
