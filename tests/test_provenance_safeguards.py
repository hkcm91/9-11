"""The safeguards that outrank architectural purity.

Raw observations are immutable. Derived information is separate. No machine
pathway reaches ``verified``. If a future refactor has to choose between these
and a cleaner abstraction, these win.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from archive.models import SourceItem
from archive.store import ArchiveStore
from historical_engine.proposals import (
    ALLOWED_PROPOSAL_TYPES,
    CONSEQUENTIAL_PROPOSAL_TYPES,
    ProposalValidationError,
    validate_proposal,
)


def _item(**kwargs) -> SourceItem:
    payload = {
        "id": "item:1",
        "source_id": "some-source",
        "source_item_id": "1",
        "source_url": "https://example.test/1",
        "ingested_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    payload.update(kwargs)
    return SourceItem(**payload)


def _proposal(**overrides) -> dict:
    payload = {
        "agent_name": "agent",
        "agent_version": "1.0",
        "subject_id": "item:1",
        "proposal_type": "temporal_claim",
        "proposal_value": {"start_time": "2001-09-11T08:46:00-04:00"},
        "confidence": 0.8,
        "evidence": [{"source_item_id": "item:1", "relationship": "supports"}],
    }
    payload.update(overrides)
    return payload


# --- raw observations --------------------------------------------------------


def test_every_ingestion_is_preserved_as_its_own_observation(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "a.sqlite") as store:
        store.put_source_items([_item(title_raw="First snapshot")])
        store.put_source_items([_item(title_raw="Richer snapshot", creator_raw="Someone")])
        observations = store.connection.execute(
            "SELECT normalized_json FROM source_observations WHERE record_id = 'item:1'"
        ).fetchall()

    titles = {json.loads(row["normalized_json"])["title_raw"] for row in observations}
    assert titles == {"First snapshot", "Richer snapshot"}


def test_a_poorer_snapshot_never_overwrites_a_richer_read_model(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "a.sqlite") as store:
        store.put_source_items([_item(title_raw="Rich", creator_raw="Someone", date_raw="2001")])
        store.put_source_items([_item(title_raw="Sparse")])
        row = store.connection.execute(
            "SELECT title_raw, creator_raw FROM source_records WHERE id = 'item:1'"
        ).fetchone()

    assert row["title_raw"] == "Rich"
    assert row["creator_raw"] == "Someone"


def test_derived_claims_never_touch_the_source_record(tmp_path: Path) -> None:
    """A claim about a record leaves the record itself byte-identical."""

    claim_path = tmp_path / "claims.jsonl"
    claim_path.write_text(
        json.dumps(
            {
                "subject_id": "item:1",
                "time_kind": "capture_time",
                "start_time": "2001-09-11T09:03:00-04:00",
                "confidence": 0.9,
                "status": "proposed",
                "evidence": [{"source_item_id": "item:1"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with ArchiveStore(tmp_path / "a.sqlite") as store:
        store.put_source_items([_item(title_raw="Untouched", date_raw=None)])
        before = dict(
            store.connection.execute("SELECT * FROM source_records WHERE id = 'item:1'").fetchone()
        )
        store.import_claim_jsonl(claim_path, "temporal")
        after = dict(
            store.connection.execute("SELECT * FROM source_records WHERE id = 'item:1'").fetchone()
        )

    assert before == after
    assert after["date_raw"] is None


# --- proposals ---------------------------------------------------------------


def test_the_original_guarantees_still_hold() -> None:
    for missing in ("agent_name", "agent_version", "proposal_type", "subject_id"):
        with pytest.raises(ProposalValidationError):
            validate_proposal(_proposal(**{missing: ""}))
    with pytest.raises(ProposalValidationError):
        validate_proposal(_proposal(proposal_value={}))
    with pytest.raises(ProposalValidationError):
        validate_proposal(_proposal(confidence=None))
    with pytest.raises(ProposalValidationError):
        validate_proposal(_proposal(evidence=[]))


@pytest.mark.parametrize("status", ["reviewed", "verified", "rejected", "disputed"])
def test_an_agent_may_not_review_or_verify_its_own_proposal(status: str) -> None:
    with pytest.raises(ProposalValidationError):
        validate_proposal(_proposal(review_status=status))


@pytest.mark.parametrize(
    "proposal_type",
    ["event_link", "relationship_link", "entity_resolution", "claim_relation", "source_classification"],
)
def test_new_proposal_types_are_accepted(proposal_type: str) -> None:
    proposal = validate_proposal(_proposal(proposal_type=proposal_type))
    assert proposal.proposal_type == proposal_type
    assert proposal.review_status == "proposed"


def test_the_original_proposal_vocabulary_survived_the_extension() -> None:
    assert {
        "temporal_claim",
        "spatial_claim",
        "entity_claim",
        "metadata_enrichment",
        "duplicate_link",
    } <= ALLOWED_PROPOSAL_TYPES


@pytest.mark.parametrize("proposal_type", sorted(CONSEQUENTIAL_PROPOSAL_TYPES))
def test_evidence_is_still_required_for_consequential_proposals(proposal_type: str) -> None:
    with pytest.raises(ProposalValidationError):
        validate_proposal(_proposal(proposal_type=proposal_type, evidence=[]))


# --- the review lifecycle ----------------------------------------------------


def test_verification_still_requires_a_prior_human_review(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "a.sqlite") as store:
        proposal = validate_proposal(_proposal())
        store.put_proposal(proposal)
        with pytest.raises(ValueError):
            store.review_proposal(proposal.proposal_id, reviewer="r", new_status="verified")
        store.review_proposal(proposal.proposal_id, reviewer="r", new_status="reviewed")
        store.review_proposal(proposal.proposal_id, reviewer="r", new_status="verified")
        history = store.connection.execute(
            "SELECT reviewer, previous_status, new_status FROM proposal_reviews ORDER BY created_at"
        ).fetchall()

    assert [(row["previous_status"], row["new_status"]) for row in history] == [
        ("proposed", "reviewed"),
        ("reviewed", "verified"),
    ]


def test_a_review_needs_a_named_reviewer(tmp_path: Path) -> None:
    with ArchiveStore(tmp_path / "a.sqlite") as store:
        proposal = validate_proposal(_proposal())
        store.put_proposal(proposal)
        with pytest.raises(ValueError):
            store.review_proposal(proposal.proposal_id, reviewer="   ", new_status="reviewed")
