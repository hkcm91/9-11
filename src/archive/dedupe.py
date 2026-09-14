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


def compare(left: SourceItem, right: SourceItem) -> DuplicateCandidate:
    reasons: list[str] = []
    title = _ratio(left.title_raw, right.title_raw)
    creator = _ratio(left.creator_raw, right.creator_raw)
    description = _ratio(left.description_raw, right.description_raw)

    if title >= 0.95:
        reasons.append("near-identical title")
    if creator >= 0.95:
        reasons.append("same/near-identical creator")
    if description >= 0.92:
        reasons.append("near-identical description")
    if left.date_raw and right.date_raw and normalize_text(left.date_raw) == normalize_text(right.date_raw):
        reasons.append("same raw date")

    # Deliberately conservative: metadata similarity proposes candidates only.
    score = 0.55 * title + 0.2 * creator + 0.25 * description
    return DuplicateCandidate(left.id, right.id, round(score, 4), reasons)


def find_candidates(
    records: Iterable[SourceItem],
    *,
    threshold: float = 0.86,
) -> list[DuplicateCandidate]:
    rows = list(records)
    candidates: list[DuplicateCandidate] = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            candidate = compare(left, right)
            if candidate.score >= threshold and candidate.reasons:
                candidates.append(candidate)
    return sorted(candidates, key=lambda item: item.score, reverse=True)
