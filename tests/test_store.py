from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from archive.models import SourceItem
from archive.proposals import validate_proposal
from archive.store import SCHEMA_VERSION, ArchiveStore


def make_item(*, title: str, description: str | None = None, metadata: dict | None = None) -> SourceItem:
    return SourceItem(
        id="source:item-1",
        source_id="source",
        source_item_id="item-1",
        source_url="https://example.test/item-1",
        title_raw=title,
        description_raw=description,
        metadata_raw=metadata or {},
        ingested_at=datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc),
    )


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_store_preserves_observations_and_selects_richest_read_model(tmp_path: Path) -> None:
    db = tmp_path / "archive.sqlite"
    sparse = make_item(title="Title", metadata={"id": 1})
    rich = make_item(
        title="Title",
        description="Richer description",
        metadata={"id": 1, "description": "Richer description", "extra": "value"},
    )

    with ArchiveStore(db) as store:
        store.put_source_item(sparse)
        store.put_source_item(rich)
        stats = store.stats()
        row = store.connection.execute(
            "SELECT title_raw, description_raw FROM source_records WHERE id = ?",
            (sparse.id,),
        ).fetchone()

    assert stats["source_records"] == 1
    assert stats["source_observations"] == 2
    assert row["title_raw"] == "Title"
    assert row["description_raw"] == "Richer description"


def test_exact_duplicate_observation_is_not_counted_twice(tmp_path: Path) -> None:
    item = make_item(title="Title", metadata={"id": 1})

    with ArchiveStore(tmp_path / "archive.sqlite") as store:
        store.put_source_item(item)
        store.put_source_item(item)
        stats = store.stats()

    assert stats["source_records"] == 1
    assert stats["source_observations"] == 1


def test_same_raw_payload_with_new_normalization_is_preserved(tmp_path: Path) -> None:
    first = make_item(title="Title", description=None, metadata={"id": 1, "raw": "same"})
    second = make_item(title="Title", description="New parser recovered this", metadata={"id": 1, "raw": "same"})

    with ArchiveStore(tmp_path / "archive.sqlite") as store:
        store.put_source_item(first)
        store.put_source_item(second)
        stats = store.stats()
        digests = store.connection.execute(
            "SELECT raw_digest, normalized_digest FROM source_observations ORDER BY observation_id"
        ).fetchall()

    assert stats["source_records"] == 1
    assert stats["source_observations"] == 2
    assert len({row["raw_digest"] for row in digests}) == 1
    assert len({row["normalized_digest"] for row in digests}) == 2


def test_import_claim_jsonl_populates_claim_tables(tmp_path: Path) -> None:
    temporal = tmp_path / "temporal.jsonl"
    spatial = tmp_path / "spatial.jsonl"
    entity = tmp_path / "entity.jsonl"

    write_jsonl(temporal, [{
        "subject_id": "source:item-1",
        "time_kind": "capture_time",
        "start_time": "2001-09-11T08:40:00-04:00",
        "end_time": "2001-09-11T08:40:00-04:00",
        "confidence": 0.85,
        "status": "proposed",
        "method": "test",
        "evidence": [],
    }])
    write_jsonl(spatial, [{
        "subject_id": "source:item-1",
        "location_kind": "capture_location",
        "latitude": 40.71,
        "longitude": -74.01,
        "confidence": 0.8,
        "status": "proposed",
        "method": "test",
        "evidence": [],
    }])
    write_jsonl(entity, [{
        "subject_id": "source:item-1",
        "entity_kind": "person",
        "role": "photographer",
        "name_raw": "Jane Example",
        "normalized_name": "Jane Example",
        "confidence": 0.9,
        "status": "proposed",
        "method": "test",
        "evidence": [],
    }])

    with ArchiveStore(tmp_path / "archive.sqlite") as store:
        assert store.import_claim_jsonl(temporal, "temporal") == 1
        assert store.import_claim_jsonl(spatial, "spatial") == 1
        assert store.import_claim_jsonl(entity, "entity") == 1
        stats = store.stats()

    assert stats["temporal_claims"] == 1
    assert stats["spatial_claims"] == 1
    assert stats["entity_claims"] == 1


def _proposal():
    return validate_proposal({
        "agent_name": "geolocation-agent",
        "agent_version": "1.0",
        "task_id": "task:resolve_location:abc",
        "subject_id": "source:item-1",
        "proposal_type": "spatial_claim",
        "proposal_value": {
            "location_kind": "capture_location",
            "latitude": 40.71,
            "longitude": -74.01,
        },
        "confidence": 0.8,
        "evidence": [{"source_item_id": "source:item-1", "relationship": "supports"}],
    })


def test_proposal_requires_review_before_verification(tmp_path: Path) -> None:
    proposal = _proposal()
    with ArchiveStore(tmp_path / "archive.sqlite") as store:
        store.put_proposal(proposal)
        with pytest.raises(ValueError, match="reviewed before"):
            store.review_proposal(proposal.proposal_id, reviewer="researcher", new_status="verified")

        first_review = store.review_proposal(
            proposal.proposal_id,
            reviewer="researcher",
            new_status="reviewed",
            note="Evidence checked against source.",
        )
        second_review = store.review_proposal(
            proposal.proposal_id,
            reviewer="senior-reviewer",
            new_status="verified",
            note="Independent verification complete.",
        )
        row = store.connection.execute(
            "SELECT review_status FROM agent_proposals WHERE proposal_id = ?",
            (proposal.proposal_id,),
        ).fetchone()
        stats = store.stats()

    assert first_review.startswith("review:")
    assert second_review.startswith("review:")
    assert row["review_status"] == "verified"
    assert stats["agent_proposals"] == 1
    assert stats["proposal_reviews"] == 2


def test_rejected_proposal_is_terminal(tmp_path: Path) -> None:
    proposal = _proposal()
    with ArchiveStore(tmp_path / "archive.sqlite") as store:
        store.put_proposal(proposal)
        store.review_proposal(proposal.proposal_id, reviewer="researcher", new_status="rejected")
        with pytest.raises(ValueError, match="terminal"):
            store.review_proposal(proposal.proposal_id, reviewer="researcher", new_status="reviewed")


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "archive.sqlite") as store:
        version = store.connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()[0]

    # Schema 4 added the evidence-graph tables. The migration is additive, so
    # the version is asserted against the constant rather than pinned to 3.
    assert version == str(SCHEMA_VERSION)
