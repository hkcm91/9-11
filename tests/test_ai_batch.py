import json
from pathlib import Path

from historical_engine.ai.batch import (
    load_decision_requests,
    request_from_dict,
    run_decision_batch,
    write_decision_batch,
)
from historical_engine.ai.fakes import FakeDecisionProvider
from historical_engine.ai.questions import DecisionQuestion
from historical_engine.collection_registry import get_collection


def _request_rows() -> list[dict]:
    return [
        {
            "question": "same_entity",
            "subject_id": "entity:1",
            "object_id": "entity:2",
            "task_type": "entity_resolution",
            "collection_id": "wikileaks",
            "evidence_ids": ["cable:1", "cable:2"],
            "context": {"candidate_score": 0.95},
        },
        {
            "question": "same_event",
            "subject_id": "event:1",
            "object_id": "event:2",
            "task_type": "event_link",
            "collection_id": "wikileaks",
            "evidence_ids": ["warlog:1", "warlog:2"],
            "context": {"candidate_score": 0.80},
        },
    ]


def test_load_decision_requests_round_trips_candidate_schema(tmp_path: Path) -> None:
    path = tmp_path / "requests.jsonl"
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in _request_rows()),
        encoding="utf-8",
    )

    requests = load_decision_requests(path)

    assert [request.question for request in requests] == [
        DecisionQuestion.SAME_ENTITY,
        DecisionQuestion.SAME_EVENT,
    ]
    assert requests[0].evidence_ids == ["cable:1", "cable:2"]
    assert requests[1].context["candidate_score"] == 0.80


def test_batch_runner_keeps_model_answers_as_proposals(tmp_path: Path) -> None:
    collection = get_collection("wikileaks")
    provider = FakeDecisionProvider()
    provider.script(
        DecisionQuestion.SAME_ENTITY,
        "entity:1",
        "same",
        0.99,
        object_id="entity:2",
        rationale="same normalized mission name in two cables",
    )
    provider.script(
        DecisionQuestion.SAME_EVENT,
        "event:1",
        "same",
        0.95,
        object_id="event:2",
        rationale="same event type, place, and near-identical time",
    )

    request_path = tmp_path / "requests.jsonl"
    request_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _request_rows()),
        encoding="utf-8",
    )
    output_path = tmp_path / "decisions.jsonl"
    proposal_path = tmp_path / "proposals.jsonl"

    summary = write_decision_batch(
        provider,
        request_path,
        output_path,
        collection=collection,
        agent_version="test-v1",
        proposal_output=proposal_path,
    )

    assert summary["requests"] == 2
    assert summary["decisions"] == 2
    assert summary["proposals"] == 2

    proposals = [
        json.loads(line)
        for line in proposal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {proposal["proposal_type"] for proposal in proposals} == {
        "entity_resolution",
        "event_link",
    }
    assert {proposal["review_status"] for proposal in proposals} == {"proposed"}
    assert all(proposal["evidence"] for proposal in proposals)


def test_batch_rejects_cross_collection_request() -> None:
    collection = get_collection("wikileaks")
    provider = FakeDecisionProvider()
    request = request_from_dict(
        {
            "question": "same_entity",
            "subject_id": "entity:1",
            "object_id": "entity:2",
            "task_type": "entity_resolution",
            "collection_id": "september11",
            "evidence_ids": ["source:1"],
        }
    )

    try:
        run_decision_batch(provider, [request], collection=collection)
    except ValueError as exc:
        assert "does not match active collection" in str(exc)
    else:
        raise AssertionError("cross-collection request should be rejected")
