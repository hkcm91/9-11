"""Canonical serialization and deterministic identifiers.

Claim and relation identifiers are content hashes so that re-running a
deterministic derivation produces the same row rather than a duplicate. The
exact JSON encoding matters: changing it would renumber every existing claim,
so it is defined once here and reused everywhere.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def claim_id(kind: str, payload: dict[str, Any]) -> str:
    material = canonical_json({"kind": kind, "payload": payload})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def digest_id(prefix: str, material: Any, *, length: int = 24) -> str:
    return f"{prefix}:" + hashlib.sha256(
        canonical_json(material).encode("utf-8")
    ).hexdigest()[:length]
