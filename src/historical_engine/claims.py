"""Claim serialization.

Claims are dataclasses whose fields are enums, datetimes, scalars and nested
evidence references. Turning one into JSON is shape-driven, not
collection-driven, so it belongs to the engine.

The output is identical to the per-claim serializers this replaced: enum
members become their string values and datetimes become ISO-8601, everything
else is left exactly as the claim recorded it.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def _convert(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _convert(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_convert(item) for item in value]
    return value


def serialize_claim(claim: Any) -> dict[str, Any]:
    """Serialize a claim dataclass to a JSON-ready dict."""

    if not is_dataclass(claim):
        raise TypeError(f"expected a claim dataclass, got {type(claim).__name__}")
    return _convert(asdict(claim))
