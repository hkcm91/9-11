from __future__ import annotations

import re
from dataclasses import dataclass

_MEDIA_EXTENSION_RE = re.compile(r"\.(?:mov|mp4|m4v|avi|wmv|mpg|mpeg)$", re.IGNORECASE)
_PREFIX_RE = re.compile(r"^V\d+\s+(?P<name>.+)$", re.IGNORECASE)
_TRAILING_MARKER_RE = re.compile(r"^(?P<name>.+?)\s+W$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class VoicesIntervieweeLabel:
    name_raw: str
    normalized_name: str | None
    confidence: float
    method: str


def strip_media_extensions(value: str) -> str:
    """Strip one or more known media extensions without touching name text."""
    text = value.strip()
    while True:
        updated = _MEDIA_EXTENSION_RE.sub("", text).strip()
        if updated == text:
            return text
        text = updated


def parse_voices_interviewee_label(title: str | None) -> VoicesIntervieweeLabel | None:
    """Interpret a Voices of 9.11 filename as an interviewee source label.

    The collection itself establishes that these records are participant video
    testimonies, so the filename can seed an interviewee reference. We only
    normalize conventions that are strongly evidenced by the corpus:

    * `V#### Name` prefixes are archive sequence identifiers.
    * a separate final token ` W` is a repeated collection marker.

    Ambiguous attached suffixes such as `HuangW` or `Farb2` are deliberately
    preserved verbatim and get lower confidence rather than being guessed away.
    """
    if not isinstance(title, str):
        return None
    base = " ".join(strip_media_extensions(title).split())
    if not base:
        return None

    prefixed = _PREFIX_RE.match(base)
    if prefixed:
        name = " ".join(prefixed.group("name").split())
        if not name:
            return None
        return VoicesIntervieweeLabel(
            name_raw=name,
            normalized_name=name,
            confidence=0.95,
            method="voices_911_vcode_filename_convention",
        )

    marked = _TRAILING_MARKER_RE.match(base)
    if marked:
        name = " ".join(marked.group("name").split())
        if not name:
            return None
        return VoicesIntervieweeLabel(
            name_raw=name,
            normalized_name=name,
            confidence=0.88,
            method="voices_911_trailing_w_filename_convention",
        )

    # Preserve, but do not normalize, the remaining source label. This captures
    # the historical archive's own participant label without pretending that
    # attached letters/numbers are spelling mistakes.
    return VoicesIntervieweeLabel(
        name_raw=base,
        normalized_name=None,
        confidence=0.70,
        method="voices_911_raw_filename_label",
    )
