"""Compatibility re-export.

The FDNY "Incident Action Plan" title parser is September 11 collection
knowledge and now lives in ``evidence_collections.september11.heuristics``.
"""

from __future__ import annotations

from evidence_collections.september11.heuristics import (
    NY_TZ,
    document_coverage_claim_from_title,
)

__all__ = ["NY_TZ", "document_coverage_claim_from_title"]
