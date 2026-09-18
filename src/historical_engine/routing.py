"""Confidence routing for AI-assisted decisions.

The engine never hardcodes a global threshold. A collection supplies a
:class:`RoutingPolicy` per task type; the router turns a provider's confidence
into one of four outcomes:

``accept_as_proposal``
    High enough to be worth recording — as a *proposal*, never as a fact.
``escalate``
    Ambiguous: send to a larger model or a human queue.
``human_review``
    Sensitive material, or policy says a person must decide.
``weak_candidate`` / ``discard``
    Below the floor; retained as a weak candidate or dropped per policy.

No outcome writes to a verified record. ``accept_as_proposal`` means the result
enters the existing proposal/review lifecycle exactly like any other agent
output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class RoutingDecision(StrEnum):
    ACCEPT_AS_PROPOSAL = "accept_as_proposal"
    ESCALATE = "escalate"
    HUMAN_REVIEW = "human_review"
    WEAK_CANDIDATE = "weak_candidate"
    DISCARD = "discard"


#: Outcomes that still require a human before anything is considered settled.
NEEDS_HUMAN: frozenset[str] = frozenset(
    {RoutingDecision.ACCEPT_AS_PROPOSAL, RoutingDecision.ESCALATE, RoutingDecision.HUMAN_REVIEW}
)


class RoutingPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Thresholds for one task type in one collection."""

    accept_at: float = 0.90
    escalate_at: float = 0.60
    weak_at: float = 0.30
    discard_below_weak: bool = False
    force_human_review: bool = False
    note: str | None = None

    def __post_init__(self) -> None:
        for name in ("accept_at", "escalate_at", "weak_at"):
            value = getattr(self, name)
            if not 0.0 <= float(value) <= 1.0:
                raise RoutingPolicyError(f"{name} must be between 0 and 1")
        if not self.accept_at >= self.escalate_at >= self.weak_at:
            raise RoutingPolicyError("thresholds must satisfy accept_at >= escalate_at >= weak_at")


@dataclass(frozen=True, slots=True)
class RoutingOutcome:
    decision: RoutingDecision
    confidence: float
    policy: RoutingPolicy
    task_type: str
    reasons: tuple[str, ...] = ()
    #: Always false. Routing can never mark anything verified; the field exists
    #: so callers and tests can assert the guarantee explicitly.
    marks_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": str(self.decision),
            "confidence": self.confidence,
            "task_type": self.task_type,
            "reasons": list(self.reasons),
            "marks_verified": self.marks_verified,
        }


@dataclass(slots=True)
class ConfidenceRouter:
    """Routes provider confidence to an outcome using per-task policies."""

    default_policy: RoutingPolicy = RoutingPolicy()
    policies: Mapping[str, RoutingPolicy] = field(default_factory=dict)

    def policy_for(self, task_type: str) -> RoutingPolicy:
        return self.policies.get(task_type, self.default_policy)

    def route(
        self,
        *,
        task_type: str,
        confidence: float,
        sensitive: bool = False,
    ) -> RoutingOutcome:
        policy = self.policy_for(task_type)
        try:
            value = float(confidence)
        except (TypeError, ValueError) as exc:
            raise RoutingPolicyError("confidence must be numeric") from exc
        if not 0.0 <= value <= 1.0:
            raise RoutingPolicyError("confidence must be between 0 and 1")

        reasons: list[str] = []
        if sensitive or policy.force_human_review:
            reasons.append(
                "sensitive_domain_policy" if sensitive else "collection_policy_forces_review"
            )
            return RoutingOutcome(
                decision=RoutingDecision.HUMAN_REVIEW,
                confidence=value,
                policy=policy,
                task_type=task_type,
                reasons=tuple(reasons),
            )

        if value >= policy.accept_at:
            decision = RoutingDecision.ACCEPT_AS_PROPOSAL
            reasons.append(f"confidence>={policy.accept_at}")
        elif value >= policy.escalate_at:
            decision = RoutingDecision.ESCALATE
            reasons.append(f"confidence>={policy.escalate_at}")
        elif value >= policy.weak_at:
            decision = RoutingDecision.WEAK_CANDIDATE
            reasons.append(f"confidence>={policy.weak_at}")
        else:
            decision = (
                RoutingDecision.DISCARD if policy.discard_below_weak else RoutingDecision.WEAK_CANDIDATE
            )
            reasons.append(f"confidence<{policy.weak_at}")
        return RoutingOutcome(
            decision=decision,
            confidence=value,
            policy=policy,
            task_type=task_type,
            reasons=tuple(reasons),
        )


def policy_from_dict(payload: Mapping[str, Any]) -> RoutingPolicy:
    return RoutingPolicy(
        accept_at=float(payload.get("accept_at", 0.90)),
        escalate_at=float(payload.get("escalate_at", 0.60)),
        weak_at=float(payload.get("weak_at", 0.30)),
        discard_below_weak=bool(payload.get("discard_below_weak", False)),
        force_human_review=bool(payload.get("force_human_review", False)),
        note=payload.get("note"),
    )


def router_from_dict(payload: Mapping[str, Any] | None) -> ConfidenceRouter:
    """Build a router from a collection's ``routing:`` configuration block."""

    if not payload:
        return ConfidenceRouter()
    default = payload.get("default")
    policies = payload.get("tasks") or {}
    if not isinstance(policies, Mapping):
        raise RoutingPolicyError("routing.tasks must be a mapping")
    return ConfidenceRouter(
        default_policy=policy_from_dict(default) if isinstance(default, Mapping) else RoutingPolicy(),
        policies={
            str(key): policy_from_dict(value)
            for key, value in policies.items()
            if isinstance(value, Mapping)
        },
    )
