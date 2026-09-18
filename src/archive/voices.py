"""Compatibility re-export.

Voices of 9.11 filename parsing is September 11 collection knowledge and now
lives in ``evidence_collections.september11.voices``.
"""

from __future__ import annotations

from evidence_collections.september11.voices import (
    VoicesIntervieweeLabel,
    parse_voices_interviewee_label,
    strip_media_extensions,
)

__all__ = [
    "VoicesIntervieweeLabel",
    "parse_voices_interviewee_label",
    "strip_media_extensions",
]
