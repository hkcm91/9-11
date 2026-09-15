from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from archive.models import SourceItem


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


# Weighted toward fields needed to place evidence in the Explorer's core
# dimensions: what, when, where, who, provenance/rights.
WEIGHTS = {
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

SOURCE_VALUE = {
    "nist-wtc-organized-media": 1.00,
    "nist-wtc-disaster-repository": 0.85,
    "september-11-digital-archive": 0.80,
    "internet-archive-understanding-911": 0.85,
}


def _present(value) -> bool:
    return value not in (None, "", [], {}, ())


def prioritize_item(item: SourceItem) -> EnrichmentPriority:
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
    if item.metadata_raw.get("_nist_normalized"):
        reasons.append("NIST structured visual metadata available")
    if item.metadata_raw.get("_file_summary"):
        reasons.append("media-file metadata available for deeper analysis")

    source_value = SOURCE_VALUE.get(item.source_id, 0.65)
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


def prioritize_records(records: Iterable[SourceItem]) -> list[EnrichmentPriority]:
    priorities = [prioritize_item(item) for item in records]
    return sorted(priorities, key=lambda row: (-row.enrichment_priority, row.item_id))
