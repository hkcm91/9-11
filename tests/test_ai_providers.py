"""AI boundaries.

The load-bearing assertion in this file is negative: no AI pathway can mark
anything verified, and no AI answer reaches the database except as a proposal.
"""

from __future__ import annotations

import pytest

from historical_engine.ai import (
    AiProposalError,
    AiProviderError,
    DecisionQuestion,
    DecisionRequest,
    DecisionResponse,
    FakeDecisionProvider,
    FakeEmbeddingProvider,
    FakeGenerativeProvider,
    FakeTranscriptionProvider,
    FakeVisionProvider,
    JevDecisionProvider,
    ProviderRegistry,
    proposal_from_decision,
    run_decision,
    validate_decision,
)
from historical_engine.collection_registry import get_collection
from historical_engine.proposals import ProposalValidationError, validate_proposal
from historical_engine.routing import RoutingDecision


def _request(**kwargs) -> DecisionRequest:
    payload = {
        "question": DecisionQuestion.SAME_EVENT,
        "subject_id": "item:a",
        "object_id": "item:b",
        "task_type": "event_link",
        "evidence_ids": ["item:a", "item:b"],
    }
    payload.update(kwargs)
    return DecisionRequest(**payload)


# --- provider stubs ----------------------------------------------------------


def test_fakes_need_no_credentials_and_are_deterministic() -> None:
    embeddings = FakeEmbeddingProvider()
    assert embeddings.embed(["hello"]) == embeddings.embed(["hello"])
    assert len(embeddings.embed(["hello"])[0]) == embeddings.dimensions
    assert FakeGenerativeProvider().generate("summarize this").startswith("[fake:")
    assert FakeVisionProvider().describe_image("img:1")
    assert FakeTranscriptionProvider().transcribe("media:1")["segments"]


def test_unscripted_question_defaults_to_unknown_at_zero_confidence() -> None:
    response = FakeDecisionProvider().decide(_request())
    assert response.answer == "unknown"
    assert response.confidence == 0.0


def test_answers_outside_the_question_vocabulary_are_rejected() -> None:
    response = DecisionResponse(
        question=DecisionQuestion.SAME_EVENT,
        answer="probably-ish",
        confidence=0.99,
        rationale="because",
        provider="p",
        model="m",
    )
    with pytest.raises(AiProviderError):
        validate_decision(response)


def test_a_decision_without_a_rationale_is_rejected() -> None:
    response = DecisionResponse(
        question=DecisionQuestion.SAME_EVENT,
        answer="same",
        confidence=0.99,
        rationale="   ",
        provider="p",
        model="m",
    )
    with pytest.raises(AiProviderError):
        validate_decision(response)


def test_provider_registry_injects_and_rejects_duplicates() -> None:
    registry = ProviderRegistry()
    provider = FakeDecisionProvider()
    registry.register("decision", "fake", provider)
    assert registry.get("decision", "fake") is provider
    assert registry.names("decision") == ["fake"]
    with pytest.raises(AiProviderError):
        registry.register("decision", "fake", FakeDecisionProvider())
    with pytest.raises(AiProviderError):
        registry.get("decision", "missing")


# --- the Jev slot ------------------------------------------------------------


def test_jev_is_a_slot_and_is_unconfigured_by_default() -> None:
    jev = JevDecisionProvider()
    assert jev.available is False
    with pytest.raises(AiProviderError):
        jev.decide(_request())


def test_jev_answers_flow_through_the_same_validation() -> None:
    class Transport:
        def ask(self, request):
            return {"answer": "same", "confidence": 0.99, "rationale": "fixture transport"}

    jev = JevDecisionProvider(transport=Transport())
    assert jev.available is True
    response = jev.decide(_request())
    assert response.provider == "jev"

    class BadTransport:
        def ask(self, request):
            return {"answer": "definitely", "confidence": 1.0, "rationale": "nonsense"}

    with pytest.raises(AiProviderError):
        JevDecisionProvider(transport=BadTransport()).decide(_request())


# --- the proposal boundary ---------------------------------------------------


def test_ai_output_becomes_a_proposal_and_nothing_else() -> None:
    provider = FakeDecisionProvider()
    provider.script(DecisionQuestion.SAME_EVENT, "item:a", "same", 0.99, object_id="item:b")
    proposal = proposal_from_decision(
        _request(), provider.decide(_request()), agent_version="1"
    )
    assert proposal.review_status == "proposed"
    assert proposal.proposal_type == "event_link"
    assert proposal.evidence


def test_ai_output_without_evidence_cannot_be_proposed() -> None:
    provider = FakeDecisionProvider()
    provider.script(DecisionQuestion.SAME_EVENT, "item:a", "same", 0.99, object_id="item:b")
    request = _request(evidence_ids=[])
    with pytest.raises(AiProposalError):
        proposal_from_decision(request, provider.decide(request), agent_version="1")


def test_no_ai_pathway_can_mark_a_claim_verified() -> None:
    """Three doors, all locked."""

    provider = FakeDecisionProvider()
    provider.script(DecisionQuestion.SAME_EVENT, "item:a", "same", 1.0, object_id="item:b")

    # 1. The routing outcome never claims verification.
    decision = run_decision(provider, _request(), agent_version="1")
    assert decision.outcome.marks_verified is False
    assert decision.proposal is not None
    assert decision.proposal.review_status == "proposed"

    # 2. The proposal validator refuses any other status outright.
    with pytest.raises(ProposalValidationError):
        validate_proposal(
            {
                "agent_name": "agent",
                "agent_version": "1",
                "subject_id": "item:a",
                "proposal_type": "event_link",
                "proposal_value": {"answer": "same"},
                "confidence": 1.0,
                "evidence": [{"source_item_id": "item:a"}],
                "review_status": "verified",
            }
        )

    # 3. Even a perfect score only produces a proposal.
    assert decision.outcome.decision == RoutingDecision.ACCEPT_AS_PROPOSAL
    assert decision.needs_human is True


def test_low_confidence_produces_no_proposal_at_all() -> None:
    provider = FakeDecisionProvider()
    provider.script(DecisionQuestion.SAME_EVENT, "item:a", "different", 0.05, object_id="item:b")
    decision = run_decision(provider, _request(), agent_version="1")
    assert decision.proposal is None
    assert decision.outcome.decision == RoutingDecision.WEAK_CANDIDATE


def test_collection_policy_forces_human_review_regardless_of_confidence() -> None:
    provider = FakeDecisionProvider()
    provider.script(DecisionQuestion.SAME_ENTITY, "item:a", "same", 1.0, object_id="item:b")
    request = _request(question=DecisionQuestion.SAME_ENTITY, task_type="entity_resolution")
    decision = run_decision(
        provider, request, collection=get_collection("september11"), agent_version="1"
    )
    assert decision.outcome.decision == RoutingDecision.HUMAN_REVIEW
    assert decision.proposal is not None
    assert decision.proposal.review_status == "proposed"
