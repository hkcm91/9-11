"""Ask a provider, route the confidence, emit a proposal — or don't.

This is the only sanctioned path from an AI answer to the database, and it has
exactly three possible outcomes:

* ``accept_as_proposal`` → a validated ``ProposalEnvelope`` with status
  ``proposed``, which a human must still review;
* ``escalate`` / ``human_review`` → a proposal is still recorded so the
  reasoning is inspectable, flagged for a person;
* ``weak_candidate`` / ``discard`` → no proposal.

There is no fourth outcome, and none of them writes a claim, a relationship or
a verified record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from historical_engine.ai.providers import (
    DecisionProvider,
    proposal_from_decision,
    validate_decision,
)
from historical_engine.ai.questions import DecisionRequest, DecisionResponse
from historical_engine.collection import Collection
from historical_engine.proposals import ProposalEnvelope
from historical_engine.routing import (
    ConfidenceRouter,
    RoutingDecision,
    RoutingOutcome,
)


@dataclass(slots=True)
class AssistedDecision:
    """The full, inspectable record of one AI-assisted decision."""

    request: DecisionRequest
    response: DecisionResponse
    outcome: RoutingOutcome
    proposal: ProposalEnvelope | None

    @property
    def needs_human(self) -> bool:
        return self.proposal is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": str(self.request.question),
            "subject_id": self.request.subject_id,
            "object_id": self.request.object_id,
            "response": self.response.to_dict(),
            "routing": self.outcome.to_dict(),
            "proposal_id": self.proposal.proposal_id if self.proposal else None,
            "review_status": self.proposal.review_status if self.proposal else None,
        }


def run_decision(
    provider: DecisionProvider,
    request: DecisionRequest,
    *,
    collection: Collection | None = None,
    router: ConfidenceRouter | None = None,
    agent_version: str = "0",
    task_id: str | None = None,
    sensitive: bool | None = None,
) -> AssistedDecision:
    """Ask one question and route the answer."""

    response = validate_decision(provider.decide(request))

    active_router = router
    if active_router is None and collection is not None:
        active_router = ConfidenceRouter(
            default_policy=collection.routing_policy(request.task_type),
            policies={request.task_type: collection.routing_policy(request.task_type)},
        )
    active_router = active_router or ConfidenceRouter()

    is_sensitive = sensitive
    if is_sensitive is None and collection is not None:
        is_sensitive = collection.ontology.sensitive.requires_human_review(
            task_type=request.task_type
        )
    outcome = active_router.route(
        task_type=request.task_type,
        confidence=response.confidence,
        sensitive=bool(is_sensitive),
    )

    proposal: ProposalEnvelope | None = None
    if outcome.decision in {
        RoutingDecision.ACCEPT_AS_PROPOSAL,
        RoutingDecision.ESCALATE,
        RoutingDecision.HUMAN_REVIEW,
    }:
        proposal = proposal_from_decision(
            request,
            response,
            agent_version=agent_version,
            task_id=task_id,
        )
        # Belt and braces: validate_proposal already forbids anything else.
        assert proposal.review_status == "proposed"

    return AssistedDecision(
        request=request, response=response, outcome=outcome, proposal=proposal
    )
