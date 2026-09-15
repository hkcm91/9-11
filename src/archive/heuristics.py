from __future__ import annotations

import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

from archive.models import EvidenceRef, SourceItem, TemporalClaim, TimeKind

NY_TZ = ZoneInfo("America/New_York")

_FDNY_PLAN_RE = re.compile(
    r"^\s*Incident\s+Action\s+Plan\s*:\s*"
    r"(?P<start>\d{1,2}/\d{1,2}/\d{2,4})"
    r"(?:\s*[-–—]\s*(?P<end>\d{1,2}/\d{1,2}/\d{2,4}))?\s*$",
    re.IGNORECASE,
)


def _parse_us_date(value: str) -> datetime:
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=NY_TZ)
        except ValueError:
            continue
    raise ValueError(value)


def document_coverage_claim_from_title(item: SourceItem) -> TemporalClaim | None:
    """Derive an explicit coverage interval from a narrowly recognized title.

    This is intentionally strict. It does not interpret generic dates in titles,
    and it never writes the result into SourceItem.date_raw. The title remains
    the evidence; the derived interval is a separate claim with a semantic kind.
    """

    title = (item.title_raw or "").strip()
    match = _FDNY_PLAN_RE.match(title)
    if not match:
        return None

    start_date = _parse_us_date(match.group("start"))
    end_text = match.group("end") or match.group("start")
    end_date = _parse_us_date(end_text)
    if end_date.date() < start_date.date():
        return None

    start = datetime.combine(start_date.date(), time.min, tzinfo=NY_TZ)
    end = datetime.combine(end_date.date(), time.max, tzinfo=NY_TZ)
    return TemporalClaim(
        subject_id=item.id,
        time_kind=TimeKind.DOCUMENT_COVERAGE,
        start_time=start,
        end_time=end,
        confidence=0.99,
        method="explicit_title_date_range",
        created_by_agent="deterministic-title-parser",
        evidence=[
            EvidenceRef(
                source_item_id=item.id,
                relationship="explicit_title_date_range",
                note=f"Coverage interval parsed directly from source title: {title}",
                weight=1.0,
            )
        ],
    )
