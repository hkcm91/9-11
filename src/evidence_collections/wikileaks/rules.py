"""Collection-specific rules for WikiLeaks releases."""

from __future__ import annotations

from historical_engine.records import SourceRecord, media_text
from historical_engine.roles import RoleRule, generic_role_rules

ROLE_EVENT_RECORD = "event_record"

SOURCE_PLUSD = "wikileaks-plusd"
SOURCE_WAR_DIARIES = "wikileaks-war-diaries"

SOURCE_VALUE = {
    SOURCE_PLUSD: 0.90,
    SOURCE_WAR_DIARIES: 0.90,
}


def _event_record(record: SourceRecord) -> str | None:
    if media_text(record) == "event_record" or record.metadata_raw.get("document_family") == "sigact":
        return ROLE_EVENT_RECORD
    return None


EVENT_RECORD_RULE = RoleRule(name="wikileaks_event_record", matcher=_event_record)


def role_rules() -> list[RoleRule]:
    # Event records must be recognized before generic document/media rules.
    return [EVENT_RECORD_RULE, *generic_role_rules()]


def priority_reasons(record: SourceRecord) -> list[str]:
    reasons: list[str] = []
    if record.metadata_raw.get("formal_reference"):
        reasons.append("formal diplomatic cable reference preserved")
    if record.metadata_raw.get("mgrs"):
        reasons.append("structured MGRS grid reference available for location resolution")
    if record.metadata_raw.get("classification"):
        reasons.append("source classification metadata preserved")
    return reasons
