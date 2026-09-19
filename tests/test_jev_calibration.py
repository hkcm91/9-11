import json
from pathlib import Path

from historical_engine.ai.calibration import analyze_calibration, render_markdown
from historical_engine.ai.batch import write_decision_batch
from historical_engine.ai.fakes import FakeDecisionProvider
from historical_engine.ai.questions import DecisionQuestion
from historical_engine.collection_registry import get_collection


def test_calibration_report_summarizes_confidence_and_routing() -> None:
    report = analyze_calibration(
        [
            {
                "question": "same_entity",
                "answer": "same",
                "confidence": 0.98,
                "routing": {"decision": "human_review"},
                "proposal_id": "proposal:1",
                "subject_id": "entity:1",
                "object_id": "entity:2",
                "context": {
                    "candidate_score": 0.95,
                    "subject_name": "U.S. Embassy Cairo",
                    "object_name": "US Embassy Cairo",
                },
            },
            {
                "question": "same_event",
                "answer": "same",
                "confidence": 0.67,
                "routing": {"decision": "weak_candidate"},
                "proposal_id": None,
                "subject_id": "event:1",
                "object_id": "event:2",
                "context": {"candidate_score": 0.81},
            },
            {
                "question": "same_event",
                "answer": "different",
                "confidence": 0.99,
                "routing": {"decision": "accept_as_proposal"},
                "proposal_id": "proposal:2",
                "subject_id": "event:3",
                "object_id": "event:4",
                "context": {"candidate_score": 0.05},
            },
        ]
    )

    assert report["decisions"] == 3
    assert report["answer_counts"] == {"different": 1, "same": 2}
    assert report["routing_counts"] == {
        "accept_as_proposal": 1,
        "human_review": 1,
        "weak_candidate": 1,
    }
    assert report["confidence_bands"]["0.95-1.00"] == 2
    assert report["confidence_bands"]["0.40-0.69"] == 1
    assert len(report["manual_review_priority"]) == 2

    rendered = render_markdown(report)
    assert "# Jev Calibration Report" in rendered
    assert "Manual-review priority" in rendered


def test_write_decision_batch_honors_limit(tmp_path: Path) -> None:
    rows = []
    provider = FakeDecisionProvider()
    for index in range(5):
        subject = f"entity:{index}"
        object_id = f"entity:{index}:other"
        rows.append(
            {
                "question": "same_entity",
                "subject_id": subject,
                "object_id": object_id,
                "task_type": "entity_resolution",
                "collection_id": "wikileaks",
                "evidence_ids": [f"source:{index}"],
                "context": {"candidate_score": 0.9},
            }
        )
        provider.script(
            DecisionQuestion.SAME_ENTITY,
            subject,
            "same",
            0.99,
            object_id=object_id,
        )

    requests = tmp_path / "requests.jsonl"
    requests.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = write_decision_batch(
        provider,
        requests,
        tmp_path / "decisions.jsonl",
        collection=get_collection("wikileaks"),
        max_requests=2,
    )

    assert summary["requests"] == 2
    assert summary["decisions"] == 2
    assert len(provider.calls) == 2
    assert len((tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()) == 2
