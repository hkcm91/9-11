from __future__ import annotations

import pytest

from archive.proposals import ProposalValidationError, validate_proposal


def valid_payload() -> dict:
    return {
        "agent_name": "geolocation-agent",
        "agent_version": "1.0",
        "task_id": "task:resolve_location:abc",
        "subject_id": "photo:1",
        "proposal_type": "spatial_claim",
        "proposal_value": {
            "location_kind": "capture_location",
            "latitude": 40.711,
            "longitude": -74.012,
            "accuracy_radius_m": 25,
        },
        "confidence": 0.82,
        "evidence": [
            {
                "source_item_id": "photo:1",
                "relationship": "visible_landmark_geometry",
                "weight": 0.8,
                "note": "Building alignment matches the proposed intersection.",
            }
        ],
        "source_ids": ["archive-a"],
    }


def test_valid_proposal_gets_stable_generated_id() -> None:
    first = validate_proposal(valid_payload())
    second = validate_proposal(valid_payload())

    assert first.proposal_id == second.proposal_id
    assert first.proposal_id.startswith("proposal:")
    assert first.review_status == "proposed"
    assert first.confidence == 0.82


def test_agent_cannot_mark_own_proposal_verified() -> None:
    payload = valid_payload()
    payload["review_status"] = "verified"

    with pytest.raises(ProposalValidationError, match="only submit proposals"):
        validate_proposal(payload)


def test_evidence_is_required() -> None:
    payload = valid_payload()
    payload["evidence"] = []

    with pytest.raises(ProposalValidationError, match="evidence"):
        validate_proposal(payload)


def test_confidence_must_be_between_zero_and_one() -> None:
    payload = valid_payload()
    payload["confidence"] = 1.4

    with pytest.raises(ProposalValidationError, match="between 0 and 1"):
        validate_proposal(payload)


def test_evidence_weight_must_be_bounded() -> None:
    payload = valid_payload()
    payload["evidence"][0]["weight"] = -0.1

    with pytest.raises(ProposalValidationError, match="weight"):
        validate_proposal(payload)
