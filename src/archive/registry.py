"""Compatibility re-export.

The source registry is generic engine infrastructure and now lives in
``historical_engine.sources``. The original import path is preserved.
"""

from __future__ import annotations

from historical_engine.sources import (
    SourceRegistryEntry,
    enabled_sources,
    load_source_registry,
)

__all__ = ["SourceRegistryEntry", "enabled_sources", "load_source_registry"]
