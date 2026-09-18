"""The narrow questions the engine asks a decision provider.

Deliberately narrow. A decision provider is never asked "what happened here?";
it is asked a closed question with a defined answer space, so the answer can be
checked, routed, and turned into a proposal that a human reviews.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DecisionQuestion(StrEnum):
    SAME_EVENT = "same_event"
    SAME_ENTITY = "same_entity"
    SUPPORTS_CLAIM = "supports_claim"
    CONTRADICTS_CLAIM = "contradicts_claim"
    RELEVANT_TO_THREAD = "relevant_to_thread"
    FIRSTHAND_OR_SECONDHAND = "firsthand_or_secondhand"
    DUPLICATE_OR_DERIVATIVE = "duplicate_or_derivative"
    ROUTE_TO_HUMAN_REVIEW = "route_to_human_review"


#: Answer vocabulary per question. A provider answering outside its question's
#: vocabulary is rejected before anything is recorded.
ANSWER_SPACE: dict[DecisionQuestion, frozenset[str]] = {
    DecisionQuestion.SAME_EVENT: frozenset({"same", "different", "unknown"}),
    DecisionQuestion.SAME_ENTITY: frozenset({"same", "different", "unknown"}),
    DecisionQuestion.SUPPORTS_CLAIM: frozenset({"supports", "does_not_support", "unknown"}),
    DecisionQuestion.CONTRADICTS_CLAIM: frozenset({"contradicts", "does_not_contradict", "unknown"}),
    DecisionQuestion.RELEVANT_TO_THREAD: frozenset({"relevant", "not_relevant", "unknown"}),
    DecisionQuestion.FIRSTHAND_OR_SECONDHAND: frozenset({"firsthand", "secondhand", "unknown"}),
    DecisionQuestion.DUPLICATE_OR_DERIVATIVE: frozenset(
        {"duplicate", "derivative", "unrelated", "unknown"}
    ),
    DecisionQuestion.ROUTE_TO_HUMAN_REVIEW: frozenset({"route", "do_not_route", "unknown"}),
}

#: Which proposal type a positive answer would feed, when it feeds one at all.
PROPOSAL_TYPE_FOR_QUESTION: dict[DecisionQuestion, str] = {
    DecisionQuestion.SAME_EVENT: "event_link",
    DecisionQuestion.SAME_ENTITY: "entity_resolution",
    DecisionQuestion.SUPPORTS_CLAIM: "claim_relation",
    DecisionQuestion.CONTRADICTS_CLAIM: "claim_relation",
    DecisionQuestion.DUPLICATE_OR_DERIVATIVE: "duplicate_link",
    DecisionQuestion.FIRSTHAND_OR_SECONDHAND: "source_classification",
    DecisionQuestion.RELEVANT_TO_THREAD: "source_classification",
}


@dataclass(slots=True)
class DecisionRequest:
    """One closed question about specific, identified material."""

    question: DecisionQuestion
    subject_id: str
    object_id: str | None = None
    task_type: str = "ai_decision"
    collection_id: str | None = None
    #: The material the provider may look at. Evidence ids, never free prose
    #: standing in for a source.
    evidence_ids: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DecisionResponse:
    """A provider's answer. Never a fact — an input to the proposal pipeline."""

    question: DecisionQuestion
    answer: str
    confidence: float
    rationale: str
    provider: str
    model: str
    #: Evidence the provider says it relied on. Required for a proposal.
    evidence_ids: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": str(self.question),
            "answer": self.answer,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "provider": self.provider,
            "model": self.model,
            "evidence_ids": list(self.evidence_ids),
        }
