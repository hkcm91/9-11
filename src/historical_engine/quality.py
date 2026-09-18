"""Generic enrichment prioritisation.

Field weights are a property of the engine (what it takes to place evidence on
a timeline and a map). How much a *particular custodial source* is worth is a
property of the collection, so it arrives through ``source_value``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from historical_engine.records import SourceRecord

# Weighted toward the dimensions every historical collection needs:
# what, when, where, who, provenance/rights.
WEIGHTS: dict[str, float] = {
    "title_raw": 0.08,
    "description_raw": 0.07,
    "creator_raw": 0.14,
    "date_raw": 0.20,
    "location_raw": 0.20,
    "rights_raw": 0.10,
    "collection_raw": 0.08,
    "media_type_raw": 0.08,
    "source_url": 0.05,
}

DEFAULT_SOURCE_VALUE = 0.65


@dataclass(slots=True)
class EnrichmentPriority:
    item_id: str
    source_id: str
    completeness_score: float
    enrichment_priority: float
    missing_fields: list[str]
    present_fields: list[str]
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _present(value) -> bool:
    return value not in (None, "", [], {}, ())


def prioritize_item(
    item: SourceRecord,
    *,
    source_value: float = DEFAULT_SOURCE_VALUE,
    extra_reasons: Callable[[SourceRecord], Iterable[str]] | None = None,
) -> EnrichmentPriority:
    present: list[str] = []
    missing: list[str] = []
    completeness = 0.0
    for field_name, weight in WEIGHTS.items():
        if _present(getattr(item, field_name)):
            completeness += weight
            present.append(field_name)
        else:
            missing.append(field_name)

    reasons: list[str] = []
    if "date_raw" in missing:
        reasons.append("missing historical time/date")
    if "location_raw" in missing:
        reasons.append("missing map location")
    if "creator_raw" in missing:
        reasons.append("missing creator/source identity")
    if "rights_raw" in missing:
        reasons.append("reuse/rights status unresolved")
    if extra_reasons is not None:
        reasons.extend(extra_reasons(item))

    # Priority is intentionally not simply inverse completeness. Records with
    # some useful structure are often cheaper to solve than almost-empty ones.
    information_gain = 1.0 - completeness
    solvability_bonus = min(0.15, len(present) * 0.015)
    priority = min(1.0, source_value * (information_gain + solvability_bonus))

    return EnrichmentPriority(
        item_id=item.id,
        source_id=item.source_id,
        completeness_score=round(completeness, 4),
        enrichment_priority=round(priority, 4),
        missing_fields=missing,
        present_fields=present,
        reasons=reasons,
    )
