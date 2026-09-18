from __future__ import annotations

import pytest

from historical_engine.collection_registry import get_collection
from historical_engine.routing import (
    ConfidenceRouter,
    RoutingDecision,
    RoutingPolicy,
    RoutingPolicyError,
    router_from_dict,
)


def test_thresholds_map_to_the_four_outcomes() -> None:
    router = ConfidenceRouter(
        default_policy=RoutingPolicy(accept_at=0.9, escalate_at=0.6, weak_at=0.3)
    )
    assert router.route(task_type="t", confidence=0.95).decision == RoutingDecision.ACCEPT_AS_PROPOSAL
    assert router.route(task_type="t", confidence=0.7).decision == RoutingDecision.ESCALATE
    assert router.route(task_type="t", confidence=0.4).decision == RoutingDecision.WEAK_CANDIDATE
    assert router.route(task_type="t", confidence=0.1).decision == RoutingDecision.WEAK_CANDIDATE


def test_discard_policy_drops_the_lowest_band() -> None:
    router = ConfidenceRouter(default_policy=RoutingPolicy(weak_at=0.3, discard_below_weak=True))
    assert router.route(task_type="t", confidence=0.1).decision == RoutingDecision.DISCARD


def test_sensitive_material_always_goes_to_a_human() -> None:
    router = ConfidenceRouter()
    outcome = router.route(task_type="t", confidence=1.0, sensitive=True)
    assert outcome.decision == RoutingDecision.HUMAN_REVIEW
    assert "sensitive_domain_policy" in outcome.reasons


def test_no_routing_outcome_ever_marks_anything_verified() -> None:
    router = ConfidenceRouter()
    for confidence in (0.0, 0.25, 0.5, 0.75, 1.0):
        for sensitive in (False, True):
            outcome = router.route(task_type="t", confidence=confidence, sensitive=sensitive)
            assert outcome.marks_verified is False


def test_thresholds_are_per_task_type() -> None:
    router = ConfidenceRouter(
        default_policy=RoutingPolicy(accept_at=0.9, escalate_at=0.6, weak_at=0.3),
        policies={"strict": RoutingPolicy(accept_at=0.99, escalate_at=0.9, weak_at=0.5)},
    )
    assert router.route(task_type="loose", confidence=0.95).decision == RoutingDecision.ACCEPT_AS_PROPOSAL
    assert router.route(task_type="strict", confidence=0.95).decision == RoutingDecision.ESCALATE


def test_thresholds_are_per_collection() -> None:
    september11 = get_collection("september11")
    demo = get_collection("demo_history")
    assert september11.routing_policy("resolve_location").accept_at != demo.routing_policy(
        "resolve_location"
    ).accept_at


def test_incoherent_policies_are_rejected() -> None:
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy(accept_at=0.5, escalate_at=0.7, weak_at=0.3)
    with pytest.raises(RoutingPolicyError):
        RoutingPolicy(accept_at=1.5)
    with pytest.raises(RoutingPolicyError):
        ConfidenceRouter().route(task_type="t", confidence=1.5)


def test_policies_load_from_configuration() -> None:
    router = router_from_dict(
        {
            "default": {"accept_at": 0.8, "escalate_at": 0.5, "weak_at": 0.2},
            "tasks": {"resolve_time": {"accept_at": 0.95, "escalate_at": 0.7, "weak_at": 0.4}},
        }
    )
    assert router.policy_for("resolve_time").accept_at == pytest.approx(0.95)
    assert router.policy_for("anything_else").accept_at == pytest.approx(0.8)
