"""Jev decision-provider slot.

This is a **slot**, not an integration. No proprietary endpoint, request shape
or authentication scheme is guessed at here, because no stable public API
contract for Jev is known to this repository. What exists is:

* the place a Jev client plugs in (``JevDecisionProvider.transport``);
* the narrow questions Jev would be asked, which are the engine's generic
  ``DecisionQuestion`` set — same event? same entity? supports claim?
  contradicts claim? relevant to thread? firsthand or secondhand? duplicate or
  derivative? route to human review?
* the guarantee that whatever comes back enters the proposal/review pipeline
  and cannot become a verified record.

To wire a real Jev deployment, implement ``JevTransport.ask`` and pass it in.
Without a transport the provider is *unconfigured*: it raises on use and
``available`` is False, so tests and CI never need credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from historical_engine.ai.providers import AiProviderError, validate_decision
from historical_engine.ai.questions import DecisionRequest, DecisionResponse


@runtime_checkable
class JevTransport(Protocol):
    """The one thing a Jev deployment must supply.

    Given a closed question and the evidence ids in scope, return a mapping
    with at least ``answer`` (a string in the question's answer space),
    ``confidence`` (0..1) and ``rationale``. Optional: ``model``,
    ``evidence_ids``.
    """

    def ask(self, request: DecisionRequest) -> dict[str, Any]: ...


@dataclass
class JevDecisionProvider:
    """Decision provider backed by a Jev transport."""

    transport: JevTransport | None = None
    name: str = "jev"
    model: str = "jev-unconfigured"

    @property
    def available(self) -> bool:
        return self.transport is not None

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        if self.transport is None:
            raise AiProviderError(
                "the Jev provider has no transport configured; supply a JevTransport "
                "implementation before asking it questions"
            )
        payload = self.transport.ask(request)
        if not isinstance(payload, dict):
            raise AiProviderError("Jev transport must return a mapping")
        try:
            answer = str(payload["answer"])
            confidence = float(payload["confidence"])
            rationale = str(payload["rationale"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AiProviderError(
                "Jev response must carry answer, confidence and rationale"
            ) from exc

        response = DecisionResponse(
            question=request.question,
            answer=answer,
            confidence=confidence,
            rationale=rationale,
            provider=self.name,
            model=str(payload.get("model") or self.model),
            evidence_ids=[str(value) for value in payload.get("evidence_ids") or request.evidence_ids],
            raw=dict(payload),
        )
        # Validated before it can reach a proposal, so a malformed or
        # out-of-vocabulary answer never becomes a record.
        return validate_decision(response)
