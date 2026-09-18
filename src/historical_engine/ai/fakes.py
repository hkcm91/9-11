"""Deterministic fake providers.

Tests and dry runs need providers that require no credentials, no network and
no randomness. These answer from a scripted table and fall back to ``unknown``
with zero confidence — the safest possible default.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Sequence

from historical_engine.ai.providers import AiProviderError
from historical_engine.ai.questions import (
    ANSWER_SPACE,
    DecisionQuestion,
    DecisionRequest,
    DecisionResponse,
)


@dataclass
class FakeDecisionProvider:
    """Answers from a scripted table keyed by (question, subject, object)."""

    name: str = "fake-decision-provider"
    model: str = "fake-decision-v1"
    answers: dict[tuple[str, str, str | None], tuple[str, float, str]] = field(
        default_factory=dict
    )
    #: Requests seen, so tests can assert the engine asked what it should have.
    calls: list[DecisionRequest] = field(default_factory=list)

    def script(
        self,
        question: DecisionQuestion | str,
        subject_id: str,
        answer: str,
        confidence: float,
        *,
        object_id: str | None = None,
        rationale: str = "scripted fake answer",
    ) -> None:
        key = str(question)
        allowed = ANSWER_SPACE.get(DecisionQuestion(key))
        if allowed is not None and answer not in allowed:
            raise AiProviderError(f"answer '{answer}' is not valid for {key}")
        self.answers[(key, subject_id, object_id)] = (answer, confidence, rationale)

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.calls.append(request)
        key = (str(request.question), request.subject_id, request.object_id)
        answer, confidence, rationale = self.answers.get(
            key, ("unknown", 0.0, "no scripted answer; defaulting to unknown")
        )
        return DecisionResponse(
            question=request.question,
            answer=answer,
            confidence=confidence,
            rationale=rationale,
            provider=self.name,
            model=self.model,
            evidence_ids=list(request.evidence_ids),
        )


@dataclass
class FakeGenerativeProvider:
    name: str = "fake-generative-provider"
    model: str = "fake-generative-v1"
    prompts: list[str] = field(default_factory=list)

    def generate(self, prompt: str, *, max_tokens: int | None = None, **kwargs: Any) -> str:
        self.prompts.append(prompt)
        return f"[fake:{self.model}] {prompt.strip()[:120]}"


@dataclass
class FakeEmbeddingProvider:
    """Hash-based embeddings: stable across runs, no model, no network."""

    name: str = "fake-embedding-provider"
    model: str = "fake-embedding-v1"
    dimensions: int = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append(
                [digest[index % len(digest)] / 255.0 for index in range(self.dimensions)]
            )
        return vectors


@dataclass
class FakeVisionProvider:
    name: str = "fake-vision-provider"
    model: str = "fake-vision-v1"

    def describe_image(self, image_ref: str, *, prompt: str | None = None) -> str:
        return f"[fake description of {image_ref}]"


@dataclass
class FakeTranscriptionProvider:
    name: str = "fake-transcription-provider"
    model: str = "fake-transcription-v1"

    def transcribe(self, media_ref: str, *, language: str | None = None) -> dict[str, Any]:
        return {
            "media_ref": media_ref,
            "language": language or "und",
            "segments": [{"start": 0.0, "end": 1.0, "text": f"[fake transcript of {media_ref}]"}],
        }
