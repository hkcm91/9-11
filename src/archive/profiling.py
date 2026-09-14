from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

from archive.models import SourceItem


FIELDS = (
    "title_raw",
    "description_raw",
    "creator_raw",
    "date_raw",
    "location_raw",
    "rights_raw",
)


@dataclass(slots=True)
class CorpusProfile:
    total_records: int
    source_counts: dict[str, int]
    populated_counts: dict[str, int]
    populated_percent: dict[str, float]
    raw_metadata_keys: dict[str, int]

    def to_dict(self) -> dict:
        return asdict(self)


def profile_records(records: Iterable[SourceItem]) -> CorpusProfile:
    rows = list(records)
    total = len(rows)
    source_counts = Counter(item.source_id for item in rows)
    populated = Counter()
    raw_keys = Counter()

    for item in rows:
        for field in FIELDS:
            value = getattr(item, field)
            if value not in (None, "", [], {}):
                populated[field] += 1
        for key in item.metadata_raw:
            raw_keys[str(key)] += 1

    percentages = {
        field: round((populated[field] / total) * 100, 2) if total else 0.0
        for field in FIELDS
    }

    return CorpusProfile(
        total_records=total,
        source_counts=dict(source_counts.most_common()),
        populated_counts={field: populated[field] for field in FIELDS},
        populated_percent=percentages,
        raw_metadata_keys=dict(raw_keys.most_common()),
    )
