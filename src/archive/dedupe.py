from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from archive.models import SourceItem


_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold().strip()
    value = _PUNCT.sub(" ", value)
    return _WS.sub(" ", value).strip()


@dataclass(slots=True)
class DuplicateCandidate:
    left_id: str
    right_id: str
    score: float
    reasons: list[str]


def _ratio(left: str | None, right: str | None) -> float:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _same_text(left: str | None, right: str | None) -> bool:
    a = normalize_text(left)
    b = normalize_text(right)
    return bool(a and b and a == b)


def compare(left: SourceItem, right: SourceItem) -> DuplicateCandidate:
    """Score a possible duplicate without merging anything.

    The important distinction here is between repeated *series metadata* and the
    same historical object. Broadcast archives commonly contain many distinct
    half-hour blocks with nearly identical title/description/creator metadata,
    so text similarity alone must never be treated as strong duplicate proof.
    """

    reasons: list[str] = []
    title = _ratio(left.title_raw, right.title_raw)
    creator = _ratio(left.creator_raw, right.creator_raw)
    description = _ratio(left.description_raw, right.description_raw)
    same_date = _same_text(left.date_raw, right.date_raw)

    if title >= 0.97:
        reasons.append("near-identical title")
    if creator >= 0.97:
        reasons.append("same/near-identical creator")
    if description >= 0.96:
        reasons.append("near-identical description")
    if same_date:
        reasons.append("same raw date")

    # Date agreement is useful corroboration, but never enough by itself.
    score = 0.50 * title + 0.20 * creator + 0.20 * description + (0.10 if same_date else 0.0)
    return DuplicateCandidate(left.id, right.id, round(score, 4), reasons)


def _qualifies_cross_source(candidate: DuplicateCandidate) -> bool:
    reasons = set(candidate.reasons)
    strong_text = "near-identical title" in reasons or "near-identical description" in reasons
    corroboration = "same/near-identical creator" in reasons or "same raw date" in reasons
    # Require at least two independent-ish signals. This intentionally prefers
    # false negatives over flooding reviewers with generic-series matches.
    return strong_text and corroboration


def _qualifies_same_source(candidate: DuplicateCandidate) -> bool:
    reasons = set(candidate.reasons)
    # Same-source duplicates are unusual after stable-ID reconciliation. To
    # surface one, require near-identical title + description and corroboration.
    return (
        "near-identical title" in reasons
        and "near-identical description" in reasons
        and ("same/near-identical creator" in reasons or "same raw date" in reasons)
        and candidate.score >= 0.97
    )


def find_candidates(
    records: Iterable[SourceItem],
    *,
    threshold: float = 0.86,
    include_same_source: bool = False,
) -> list[DuplicateCandidate]:
    """Return conservative duplicate candidates.

    By default, compare records *across custodial sources only*. Multiple
    snapshots of the same stable source ID should already have been reconciled
    by the corpus loader; separate records within one archive are presumed
    distinct unless a caller explicitly requests the stricter same-source pass.
    """

    rows = list(records)
    candidates: list[DuplicateCandidate] = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            if left.id == right.id:
                continue

            same_source = left.source_id == right.source_id
            if same_source and not include_same_source:
                continue

            candidate = compare(left, right)
            if candidate.score < threshold or not candidate.reasons:
                continue

            qualifies = _qualifies_same_source(candidate) if same_source else _qualifies_cross_source(candidate)
            if qualifies:
                candidates.append(candidate)

    return sorted(candidates, key=lambda item: item.score, reverse=True)
