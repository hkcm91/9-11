"""AI provider interfaces.

The engine depends on these protocols, never on a vendor SDK. Providers are
injected, so tests run with deterministic fakes and no credentials.

The hard boundary: **a provider produces a proposal, never a record.** The only
way a provider's output reaches the database is through
``historical_engine.proposals.validate_proposal``, which refuses any status
other than ``proposed``, and from there through human review. Nothing in this
module can write a verified claim, and ``AiProposalError`` is raised if a caller
tries to build one.
"""

from __future__ import annotations

from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

from historical_engine.ai.questions import (
    ANSWER_SPACE,
    PROPOSAL_TYPE_FOR_QUESTION,
    DecisionRequest,
    DecisionResponse,
)
from historical_engine.proposals import ProposalEnvelope, validate_proposal


class AiProviderError(RuntimeError):
    """Raised when a provider is unavailable or returns an unusable answer."""


class AiProposalError(ValueError):
    """Raised when AI output would be turned into something other than a proposal."""


@runtime_checkable
class DecisionProvider(Protocol):
    """Answers a closed question about identified material."""

    name: str
    model: str

    def decide(self, request: DecisionRequest) -> DecisionResponse: ...


@runtime_checkable
class GenerativeProvider(Protocol):
    """Produces text — summaries, descriptions, research notes."""

    name: str
    model: str

    def generate(self, prompt: str, *, max_tokens: int | None = None, **kwargs: Any) -> str: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Produces vectors for similarity search and clustering."""

    name: str
    model: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@runtime_checkable
class VisionProvider(Protocol):
    """Describes or compares images.

    Face recognition and identification of individuals are explicitly out of
    scope for this project; a provider implementation must not offer them.
    """

    name: str
    model: str

    def describe_image(self, image_ref: str, *, prompt: str | None = None) -> str: ...


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Transcribes audio or video into text with timing where available."""

    name: str
    model: str

    def transcribe(self, media_ref: str, *, language: str | None = None) -> dict[str, Any]: ...


class ProviderRegistry:
    """Dependency-injection container for providers.

    Nothing resolves a provider by importing a vendor module; callers ask the
    registry, and tests register fakes.
    """

    def __init__(self) -> None:
        self._providers: dict[str, dict[str, Any]] = {}

    def register(self, kind: str, name: str, provider: Any, *, replace: bool = False) -> Any:
        slot = self._providers.setdefault(kind, {})
        if name in slot and not replace:
            raise AiProviderError(f"{kind} provider '{name}' is already registered")
        slot[name] = provider
        return provider

    def get(self, kind: str, name: str) -> Any:
        try:
            return self._providers[kind][name]
        except KeyError:
            raise AiProviderError(f"no {kind} provider named '{name}'") from None

    def names(self, kind: str) -> list[str]:
        return sorted(self._providers.get(kind, {}))

    def clear(self) -> None:
        self._providers.clear()


def validate_decision(response: DecisionResponse) -> DecisionResponse:
    """Reject answers outside the question's declared answer space."""

    allowed = ANSWER_SPACE.get(response.question)
    if allowed is None:
        raise AiProviderError(f"unknown decision question: {response.question}")
    if response.answer not in allowed:
        raise AiProviderError(
            f"answer '{response.answer}' is not valid for {response.question}; "
            f"expected one of {sorted(allowed)}"
        )
    try:
        confidence = float(response.confidence)
    except (TypeError, ValueError) as exc:
        raise AiProviderError("confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise AiProviderError("confidence must be between 0 and 1")
    if not response.rationale.strip():
        raise AiProviderError("a decision must carry a rationale")
    return response


def proposal_from_decision(
    request: DecisionRequest,
    response: DecisionResponse,
    *,
    agent_version: str,
    task_id: str | None = None,
    proposal_type: str | None = None,
    evidence: Iterable[dict[str, Any]] | None = None,
) -> ProposalEnvelope:
    """Turn a validated AI decision into a *proposal*.

    The result always has ``review_status='proposed'``. There is no parameter
    for any other status, and ``validate_proposal`` rejects one anyway.
    """

    validate_decision(response)
    resolved_type = proposal_type or PROPOSAL_TYPE_FOR_QUESTION.get(request.question)
    if resolved_type is None:
        raise AiProposalError(
            f"question {request.question} has no proposal type; supply one explicitly"
        )

    evidence_payload = (
        list(evidence)
        if evidence is not None
        else [
            {"source_item_id": evidence_id, "relationship": "considered_by_provider"}
            for evidence_id in (response.evidence_ids or request.evidence_ids)
        ]
    )
    if not evidence_payload:
        raise AiProposalError(
            "an AI decision must cite at least one evidence record before it can be proposed"
        )

    return validate_proposal(
        {
            "agent_name": response.provider,
            "agent_version": agent_version,
            "subject_id": request.subject_id,
            "proposal_type": resolved_type,
            "proposal_value": {
                "question": str(request.question),
                "answer": response.answer,
                "object_id": request.object_id,
                "model": response.model,
                "rationale": response.rationale,
            },
            "confidence": float(response.confidence),
            "evidence": evidence_payload,
            "task_id": task_id,
            "source_ids": [],
            "notes": response.rationale,
            # Not configurable, on purpose.
            "review_status": "proposed",
        }
    )
