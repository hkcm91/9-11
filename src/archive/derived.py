from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from archive.adapters.nist_organized import temporal_claim_from_nist_row
from archive.heuristics import document_coverage_claim_from_title
from archive.models import SourceItem, TemporalClaim


def derive_temporal_claims(records: Iterable[SourceItem]) -> list[TemporalClaim]:
    """Run deterministic, evidence-preserving temporal derivations.

    These are claims, never replacements for SourceItem.date_raw. Only narrow
    transformations with explicit source evidence belong here; uncertain work
    stays in the agent proposal/review pipeline.
    """

    claims: list[TemporalClaim] = []
    for item in records:
        claim = document_coverage_claim_from_title(item)
        if claim is not None:
            claims.append(claim)

        if item.source_id == "nist-wtc-organized-media":
            nist_claim = temporal_claim_from_nist_row(item)
            if nist_claim is not None:
                claims.append(nist_claim)
    return claims


def serialize_temporal_claim(claim: TemporalClaim) -> dict[str, Any]:
    payload = asdict(claim)
    payload["time_kind"] = claim.time_kind.value
    payload["status"] = claim.status.value
    if claim.start_time is not None:
        payload["start_time"] = claim.start_time.isoformat()
    if claim.end_time is not None:
        payload["end_time"] = claim.end_time.isoformat()
    return payload
