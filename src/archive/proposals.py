"""Compatibility re-export.

Proposal validation is generic engine infrastructure and now lives in
``historical_engine.proposals``. This module keeps the original import path
working for adapters, agents, tests and downstream tooling.
"""

from __future__ import annotations

from historical_engine.proposals import (
    ALLOWED_PROPOSAL_TYPES,
    CONSEQUENTIAL_PROPOSAL_TYPES,
    ProposalEnvelope,
    ProposalValidationError,
    load_proposal_jsonl,
    validate_proposal,
)

__all__ = [
    "ALLOWED_PROPOSAL_TYPES",
    "CONSEQUENTIAL_PROPOSAL_TYPES",
    "ProposalEnvelope",
    "ProposalValidationError",
    "load_proposal_jsonl",
    "validate_proposal",
]
