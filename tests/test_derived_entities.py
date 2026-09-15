from __future__ import annotations

from archive.derived import derive_entity_claims, serialize_entity_claim
from archive.models import EntityKind, EntityRole, SourceItem


def test_voices_filename_becomes_interviewee_reference() -> None:
    item = SourceItem(
        id="911da:96746",
        source_id="september-11-digital-archive",
        source_item_id="96746",
        source_url="https://911digitalarchive.org/items/show/96746",
        title_raw="V1004 Lei Hennessy.mov.mp4",
        metadata_raw={"collection_id": 267},
    )
    claims = derive_entity_claims([item])
    assert len(claims) == 1
    claim = claims[0]
    assert claim.entity_kind == EntityKind.PERSON
    assert claim.role == EntityRole.INTERVIEWEE
    assert claim.name_raw == "Lei Hennessy"
    assert claim.confidence == 0.95


def test_non_voices_filename_is_not_interpreted_as_person() -> None:
    item = SourceItem(
        id="911da:other",
        source_id="september-11-digital-archive",
        source_item_id="other",
        source_url="https://example.test",
        title_raw="V1004 Lei Hennessy.mov.mp4",
        metadata_raw={"collection_id": 23},
    )
    assert derive_entity_claims([item]) == []


def test_internet_archive_contributor_becomes_broadcaster_reference() -> None:
    item = SourceItem(
        id="ia:nhk",
        source_id="internet-archive-understanding-911",
        source_item_id="nhk",
        source_url="https://archive.org/details/nhk",
        creator_raw="NHK",
        metadata_raw={"contributor": "NHK"},
    )
    claims = derive_entity_claims([item])
    assert len(claims) == 1
    claim = claims[0]
    assert claim.entity_kind == EntityKind.ORGANIZATION
    assert claim.role == EntityRole.BROADCASTER
    assert claim.name_raw == "NHK"


def test_entity_serializer_uses_enum_values() -> None:
    item = SourceItem(
        id="ia:nhk",
        source_id="internet-archive-understanding-911",
        source_item_id="nhk",
        source_url="https://archive.org/details/nhk",
        metadata_raw={"contributor": "NHK"},
    )
    payload = serialize_entity_claim(derive_entity_claims([item])[0])
    assert payload["entity_kind"] == "organization"
    assert payload["role"] == "broadcaster"
    assert payload["status"] == "proposed"
