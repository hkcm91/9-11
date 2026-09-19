from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from historical_engine.ai.pipeline import AssistedDecision, run_decision
from historical_engine.ai.providers import DecisionProvider
from historical_engine.ai.questions import DecisionQuestion, DecisionRequest
from historical_engine.collection import Collection


def request_from_dict(payload: dict[str, Any]) -> DecisionRequest:
    return DecisionRequest(
        question=DecisionQuestion(str(payload["question"])),
        subject_id=str(payload["subject_id"]),
        object_id=(
            str(payload["object_id"])
            if payload.get("object_id") is not None
            else None
        ),
        task_type=str(payload.get("task_type") or "ai_decision"),
        collection_id=(
            str(payload["collection_id"])
            if payload.get("collection_id") is not None
            else None
        ),
        evidence_ids=[str(value) for value in payload.get("evidence_ids") or []],
        context=dict(payload.get("context") or {}),
    )


def load_decision_requests(path: Path | str) -> list[DecisionRequest]:
    requests: list[DecisionRequest] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid decision-request JSONL at {path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"expected decision-request object at {path}:{line_number}")
            requests.append(request_from_dict(payload))
    return requests


def decision_to_dict(decision: AssistedDecision) -> dict[str, Any]:
    payload = decision.to_dict()
    payload["subject_id"] = decision.request.subject_id
    payload["object_id"] = decision.request.object_id
    payload["task_type"] = decision.request.task_type
    payload["collection_id"] = decision.request.collection_id
    payload["evidence_ids"] = list(decision.request.evidence_ids)
    payload["context"] = dict(decision.request.context)
    payload["answer"] = decision.response.answer
    payload["confidence"] = decision.response.confidence
    payload["rationale"] = decision.response.rationale
    payload["provider"] = decision.response.provider
    payload["model"] = decision.response.model
    if decision.proposal is not None:
        payload["proposal"] = decision.proposal.to_dict()
    return payload


def run_decision_batch(
    provider: DecisionProvider,
    requests: Iterable[DecisionRequest],
    *,
    collection: Collection,
    agent_version: str = "0",
) -> list[AssistedDecision]:
    decisions: list[AssistedDecision] = []
    for request in requests:
        if request.collection_id not in (None, collection.id):
            raise ValueError(
                f"request collection '{request.collection_id}' does not match active collection '{collection.id}'"
            )
        decisions.append(
            run_decision(
                provider,
                request,
                collection=collection,
                agent_version=agent_version,
            )
        )
    return decisions


def write_decision_batch(
    provider: DecisionProvider,
    requests_path: Path | str,
    output_path: Path | str,
    *,
    collection: Collection,
    agent_version: str = "0",
    proposal_output: Path | str | None = None,
) -> dict[str, int]:
    requests = load_decision_requests(requests_path)
    decisions = run_decision_batch(
        provider,
        requests,
        collection=collection,
        agent_version=agent_version,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision_to_dict(decision), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    proposals = [decision.proposal for decision in decisions if decision.proposal is not None]
    if proposal_output is not None:
        proposal_path = Path(proposal_output)
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        with proposal_path.open("w", encoding="utf-8") as handle:
            for proposal in proposals:
                handle.write(json.dumps(proposal.to_dict(), ensure_ascii=False, sort_keys=True))
                handle.write("\n")

    return {
        "requests": len(requests),
        "decisions": len(decisions),
        "proposals": len(proposals),
        "discarded_or_weak": len(decisions) - len(proposals),
    }
