"""September 11 collection rules.

Everything here is knowledge about *this* corpus: which custodial source ids
exist, which of their internal collection ids mean "oral history" rather than
"document", and which title conventions carry a parseable date range.

The ordering of ``role_rules`` reproduces the original ``work_queue._record_role``
``if`` chain exactly, including the points where a generic media test sits
*between* two collection-specific tests. See ``docs/ENGINE_REFACTOR.md``.
"""

from __future__ import annotations

from historical_engine.records import SourceRecord, collection_text, metadata_int, title_text
from historical_engine.roles import (
    AUDIO_MEDIA_RULE,
    DOCUMENT_MEDIA_RULE,
    ORAL_HISTORY_RULE,
    PHOTO_MEDIA_RULE,
    REPOSITORY_MEDIA_RULE,
    ROLE_AUDIO,
    ROLE_DOCUMENT,
    ROLE_PHOTO,
    ROLE_REPOSITORY,
    ROLE_TESTIMONY,
    VIDEO_MEDIA_RULE,
    RoleRule,
    constant_rule,
)

# --- source identifiers ------------------------------------------------------

SOURCE_INTERNET_ARCHIVE = "internet-archive-understanding-911"
SOURCE_ARCHDISK_PHOTO_MAP = "archdisk-911-photo-map"
SOURCE_NIST_REPOSITORY = "nist-wtc-disaster-repository"
SOURCE_NIST_ORGANIZED = "nist-wtc-organized-media"

# The registry declares `september11-digital-archive` while the Phase-0
# pipeline code keyed on `september-11-digital-archive`. Both spellings are
# live in real corpora and in tests, so both are recognised rather than
# silently unified, which would change existing queue output. See
# docs/ENGINE_REFACTOR.md.
SOURCE_911DA_REGISTRY = "september11-digital-archive"
SOURCE_911DA_PIPELINE = "september-11-digital-archive"
SOURCE_911DA_IDS = frozenset({SOURCE_911DA_REGISTRY, SOURCE_911DA_PIPELINE})

#: September 11 Digital Archive internal collection ids whose meaning is known.
DIGITAL_ARCHIVE_COLLECTION_ROLES: dict[int, str] = {
    11: ROLE_DOCUMENT,
    267: ROLE_TESTIMONY,
    266: ROLE_AUDIO,
}

#: The Voices of 9.11 oral-history collection inside the Digital Archive.
VOICES_COLLECTION_ID = 267

#: How much each custodial source is worth to spend research effort on.
SOURCE_VALUE: dict[str, float] = {
    SOURCE_NIST_ORGANIZED: 1.00,
    SOURCE_NIST_REPOSITORY: 0.85,
    SOURCE_911DA_PIPELINE: 0.80,
    SOURCE_911DA_REGISTRY: 0.80,
    SOURCE_INTERNET_ARCHIVE: 0.85,
}


# --- collection-specific role rules -----------------------------------------


def _source_role(record: SourceRecord) -> str | None:
    if record.source_id == SOURCE_INTERNET_ARCHIVE:
        return "broadcast"
    if record.source_id == SOURCE_ARCHDISK_PHOTO_MAP:
        return ROLE_PHOTO
    if record.source_id in SOURCE_911DA_IDS:
        collection_id = metadata_int(record, "collection_id")
        if collection_id is not None:
            return DIGITAL_ARCHIVE_COLLECTION_ROLES.get(collection_id)
    return None


SOURCE_ROLE_RULE = RoleRule(name="september11_source_role", matcher=_source_role)

NIST_REPOSITORY_RULE = constant_rule(
    "september11_nist_repository_source",
    lambda record: record.source_id == SOURCE_NIST_REPOSITORY,
    ROLE_REPOSITORY,
)

INCIDENT_ACTION_PLAN_RULE = constant_rule(
    "september11_incident_action_plan",
    lambda record: "incident action plan" in title_text(record),
    ROLE_DOCUMENT,
)

VOICES_COLLECTION_RULE = constant_rule(
    "september11_voices_collection",
    lambda record: "voices of 9.11" in collection_text(record),
    ROLE_TESTIMONY,
)

SONIC_MEMORIAL_RULE = constant_rule(
    "september11_sonic_memorial",
    lambda record: "sonic memorial" in collection_text(record),
    ROLE_AUDIO,
)


def role_rules() -> list[RoleRule]:
    """Ordered classification chain, identical in effect to the Phase-0 chain."""

    return [
        SOURCE_ROLE_RULE,
        NIST_REPOSITORY_RULE,
        REPOSITORY_MEDIA_RULE,
        INCIDENT_ACTION_PLAN_RULE,
        DOCUMENT_MEDIA_RULE,
        VOICES_COLLECTION_RULE,
        ORAL_HISTORY_RULE,
        SONIC_MEMORIAL_RULE,
        AUDIO_MEDIA_RULE,
        PHOTO_MEDIA_RULE,
        VIDEO_MEDIA_RULE,
    ]


def priority_reasons(record: SourceRecord) -> list[str]:
    """Extra researcher-facing reasons specific to this corpus' metadata."""

    reasons: list[str] = []
    if record.metadata_raw.get("_nist_normalized"):
        reasons.append("NIST structured visual metadata available")
    if record.metadata_raw.get("_file_summary"):
        reasons.append("media-file metadata available for deeper analysis")
    return reasons
