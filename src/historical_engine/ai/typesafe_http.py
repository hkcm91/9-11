from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from historical_engine.ai.providers import AiProviderError
from historical_engine.ai.questions import ANSWER_SPACE, DecisionQuestion, DecisionRequest
from historical_engine.ai.typesafe_config import TypeSafeConfig, typesafe_config_from_env

HttpOpener = Callable[..., Any]

_QUESTION_INSTRUCTIONS: dict[DecisionQuestion, str] = {
    DecisionQuestion.SAME_ENTITY: (
        "Do the subject and object refer to the same real-world entity? "
        "Use only the supplied state and return unknown when the evidence is insufficient."
    ),
    DecisionQuestion.SAME_EVENT: (
        "Do the subject and object refer to the same historical event or incident? "
        "Use only the supplied state and return unknown when the evidence is insufficient."
    ),
    DecisionQuestion.SUPPORTS_CLAIM: (
        "Does the supplied evidence support the claim represented by the object? "
        "Distinguish actual support from mere topical relevance."
    ),
    DecisionQuestion.CONTRADICTS_CLAIM: (
        "Does the supplied evidence contradict the claim represented by the object? "
        "Return unknown when the relationship cannot be determined."
    ),
    DecisionQuestion.RELEVANT_TO_THREAD: (
        "Is the supplied material relevant to the research thread represented by the object?"
    ),
    DecisionQuestion.FIRSTHAND_OR_SECONDHAND: (
        "Is the source material firsthand or secondhand with respect to the described event?"
    ),
    DecisionQuestion.DUPLICATE_OR_DERIVATIVE: (
        "Is the subject a duplicate of, derived from, unrelated to, or indeterminate with respect to the object?"
    ),
    DecisionQuestion.ROUTE_TO_HUMAN_REVIEW: (
        "Should this item be routed to human review based on the supplied state?"
    ),
}

_ANSWER_DESCRIPTIONS: dict[str, str] = {
    "same": "The two identifiers refer to the same underlying entity or event.",
    "different": "They refer to different underlying entities or events.",
    "unknown": "The supplied state is insufficient to determine the answer reliably.",
    "supports": "The supplied material provides evidence that supports the claim.",
    "does_not_support": "The supplied material does not provide support for the claim.",
    "contradicts": "The supplied material conflicts with or contradicts the claim.",
    "does_not_contradict": "The supplied material does not contradict the claim.",
    "relevant": "The material is relevant to the specified research thread.",
    "not_relevant": "The material is not relevant to the specified research thread.",
    "firsthand": "The source directly witnessed, recorded, or participated in the described event.",
    "secondhand": "The source reports information learned from another source.",
    "duplicate": "The subject is effectively a duplicate of the object.",
    "derivative": "The subject derives materially from the object but is not an exact duplicate.",
    "unrelated": "The subject and object are unrelated for this decision.",
    "route": "This item should be sent to human review.",
    "do_not_route": "This item does not require human review based on the supplied state.",
}


def _state_for_request(request: DecisionRequest) -> str:
    payload = {
        "question": str(request.question),
        "subject_id": request.subject_id,
        "object_id": request.object_id,
        "evidence_ids": list(request.evidence_ids),
        "context": dict(request.context),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _choice_criteria(question: DecisionQuestion) -> dict[str, str]:
    return {
        answer: _ANSWER_DESCRIPTIONS.get(answer, answer.replace("_", " "))
        for answer in sorted(ANSWER_SPACE[question])
    }


@dataclass
class TypeSafeHttpTransport:
    """Documented HTTP transport for TypeSafe System One / Jev.

    API contract:
      POST https://api.typesafe.ai/v1/systemone
      Authorization: Bearer <API_KEY>
      {"state": ..., "model": "jev-latest", "questions": {...}}

    The endpoint, model and auth header/prefix remain overrideable through
    TypeSafeConfig so a future API version does not require rewriting callers.
    """

    config: TypeSafeConfig
    opener: HttpOpener = urlopen
    timeout_s: float = 30.0

    @classmethod
    def from_env(
        cls,
        *,
        dotenv_path: str = ".env",
        opener: HttpOpener = urlopen,
        timeout_s: float = 30.0,
    ) -> "TypeSafeHttpTransport":
        return cls(
            config=typesafe_config_from_env(dotenv_path=dotenv_path),
            opener=opener,
            timeout_s=timeout_s,
        )

    def _headers(self) -> dict[str, str]:
        if not self.config.has_api_key:
            raise AiProviderError("TYPESAFE_API_KEY is not configured")
        header = (self.config.auth_header or "Authorization").strip()
        prefix = (self.config.auth_prefix or "Bearer").strip()
        value = self.config.api_key.strip()
        if prefix:
            value = f"{prefix} {value}"
        return {
            header: value,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def ask(self, request: DecisionRequest) -> dict[str, Any]:
        if not self.config.has_api_url:
            raise AiProviderError("TYPESAFE_API_URL is not configured")

        question_name = "decision"
        body = {
            "state": _state_for_request(request),
            "model": self.config.model,
            "questions": {
                question_name: {
                    "type": "choice",
                    "instructions": _QUESTION_INSTRUCTIONS[request.question],
                    "criteria": _choice_criteria(request.question),
                }
            },
        }
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        http_request = Request(
            self.config.api_url,
            data=encoded,
            headers=self._headers(),
            method="POST",
        )

        try:
            with self.opener(http_request, timeout=self.timeout_s) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:500]
            except Exception:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise AiProviderError(f"TypeSafe API HTTP {exc.code}{suffix}") from exc
        except URLError as exc:
            raise AiProviderError(f"TypeSafe API connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise AiProviderError("TypeSafe API request timed out") from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise AiProviderError("TypeSafe API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AiProviderError("TypeSafe API response must be an object")

        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise AiProviderError("TypeSafe API response is missing answers")
        answer_payload = answers.get(question_name)
        if not isinstance(answer_payload, dict):
            raise AiProviderError("TypeSafe API response is missing the decision answer")

        choice = answer_payload.get("choice")
        confidence = answer_payload.get("confidence")
        probabilities = answer_payload.get("probabilities") or {}
        if not isinstance(choice, str) or not choice:
            raise AiProviderError("TypeSafe Choice response is missing choice")
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError) as exc:
            raise AiProviderError("TypeSafe Choice response is missing numeric confidence") from exc

        rationale = (
            f"TypeSafe Choice selected '{choice}' with confidence {confidence_value:.3f}; "
            f"probabilities={json.dumps(probabilities, sort_keys=True)}"
        )

        return {
            "answer": choice,
            "confidence": confidence_value,
            "rationale": rationale,
            "model": str(payload.get("model") or self.config.model),
            "evidence_ids": list(request.evidence_ids),
            "probabilities": probabilities,
            "usage": payload.get("usage"),
            "raw": payload,
        }
