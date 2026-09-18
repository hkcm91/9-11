"""Record-role classification as an explicit ordered rule list.

A *record role* answers "what kind of historical record is this, for workflow
purposes?" — photograph, video, audio, broadcast, testimony, document,
repository entry. It is a workflow classification, not a claim about history,
so it carries no confidence and is never written back onto the source record.

Classification is modelled as an ordered list of named rules rather than a
hardcoded ``if`` chain so that a collection can interleave its own rules with
the generic ones at exactly the position it needs. See
``docs/ENGINE_REFACTOR.md`` for why ordering matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from historical_engine.records import (
    SourceRecord,
    collection_text,
    media_text,
)

# Generic workflow roles understood by the engine. A collection ontology may
# declare additional roles; the engine treats an unknown role as opaque.
ROLE_REPOSITORY = "repository"
ROLE_DOCUMENT = "document"
ROLE_TESTIMONY = "testimony"
ROLE_AUDIO = "audio"
ROLE_BROADCAST = "broadcast"
ROLE_PHOTO = "photo"
ROLE_VIDEO = "video"
ROLE_UNKNOWN = "unknown"

GENERIC_ROLES: frozenset[str] = frozenset(
    {
        ROLE_REPOSITORY,
        ROLE_DOCUMENT,
        ROLE_TESTIMONY,
        ROLE_AUDIO,
        ROLE_BROADCAST,
        ROLE_PHOTO,
        ROLE_VIDEO,
        ROLE_UNKNOWN,
    }
)


@dataclass(frozen=True, slots=True)
class RoleRule:
    """A single named classification step.

    ``matcher`` returns the role this rule assigns, or ``None`` to defer to the
    next rule. Rules are pure functions of the record.
    """

    name: str
    matcher: Callable[[SourceRecord], str | None]

    def __call__(self, record: SourceRecord) -> str | None:
        return self.matcher(record)


def classify(record: SourceRecord, rules: Sequence[RoleRule]) -> str:
    for rule in rules:
        role = rule(record)
        if role is not None:
            return role
    return ROLE_UNKNOWN


def constant_rule(name: str, predicate: Callable[[SourceRecord], bool], role: str) -> RoleRule:
    """Build a rule that assigns ``role`` whenever ``predicate`` holds."""

    return RoleRule(name=name, matcher=lambda record: role if predicate(record) else None)


def _media_contains(record: SourceRecord, tokens: Iterable[str]) -> bool:
    media = media_text(record)
    return any(token in media for token in tokens)


# --- generic rules -----------------------------------------------------------

REPOSITORY_MEDIA_RULE = constant_rule(
    "repository_media",
    lambda record: media_text(record) == "repository_entry",
    ROLE_REPOSITORY,
)

DOCUMENT_MEDIA_RULE = constant_rule(
    "document_media",
    lambda record: _media_contains(record, ("document", "text", "pdf")),
    ROLE_DOCUMENT,
)

ORAL_HISTORY_RULE = constant_rule(
    "oral_history",
    lambda record: "oral history" in collection_text(record)
    or "oral_history" in media_text(record),
    ROLE_TESTIMONY,
)

AUDIO_MEDIA_RULE = constant_rule(
    "audio_media",
    lambda record: _media_contains(record, ("audio", "sound")),
    ROLE_AUDIO,
)

PHOTO_MEDIA_RULE = constant_rule(
    "photo_media",
    lambda record: _media_contains(record, ("photo", "image")),
    ROLE_PHOTO,
)

VIDEO_MEDIA_RULE = constant_rule(
    "video_media",
    lambda record: _media_contains(record, ("video", "movie", "film")),
    ROLE_VIDEO,
)


def generic_role_rules() -> list[RoleRule]:
    """The engine's default ordering, used by collections that add nothing."""

    return [
        REPOSITORY_MEDIA_RULE,
        DOCUMENT_MEDIA_RULE,
        ORAL_HISTORY_RULE,
        AUDIO_MEDIA_RULE,
        PHOTO_MEDIA_RULE,
        VIDEO_MEDIA_RULE,
    ]
