"""Generic source registry.

A source registry is a YAML document describing the custodial sources a
collection draws on. Nothing here is collection-specific: the same loader
serves the September 11 registry, the demo registry and any future one.

Two document shapes are supported:

* ``sources:`` — a list of source entries.
* ``sources_from:`` — a list of other registry files to compose, resolved
  relative to the including document. This lets a legacy path keep working
  while the canonical file lives inside its collection.

Both keys may appear together; composed entries are loaded first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = frozenset(
    {
        "id",
        "name",
        "type",
        "homepage_url",
        "access_method",
        "public_access",
        "rights_status",
        "metadata_quality",
        "ingest_mode",
        "media_types",
        "priority",
    }
)

_KNOWN_FIELDS = REQUIRED_FIELDS | {
    "enabled",
    "estimated_item_count",
    "notes",
    "rights_notes",
}


@dataclass(slots=True)
class SourceRegistryEntry:
    id: str
    name: str
    type: str
    homepage_url: str
    access_method: str
    public_access: bool | str
    rights_status: str
    metadata_quality: str
    ingest_mode: str
    media_types: list[str]
    priority: str
    enabled: bool = True
    estimated_item_count: int | None = None
    notes: str | None = None
    rights_notes: str | None = None
    extra: dict[str, Any] | None = None


def _entry_from_dict(raw: Any, index: int, seen: set[str]) -> SourceRegistryEntry:
    if not isinstance(raw, dict):
        raise ValueError(f"source registry entry {index} must be a mapping")
    missing = sorted(REQUIRED_FIELDS - raw.keys())
    if missing:
        raise ValueError(f"source registry entry {index} missing: {', '.join(missing)}")

    source_id = str(raw["id"]).strip()
    if not source_id:
        raise ValueError(f"source registry entry {index} has an empty id")
    if source_id in seen:
        raise ValueError(f"duplicate source id: {source_id}")
    seen.add(source_id)

    media_types = raw["media_types"]
    if not isinstance(media_types, list) or not media_types:
        raise ValueError(f"source {source_id} must declare at least one media type")

    extra = {key: value for key, value in raw.items() if key not in _KNOWN_FIELDS}
    return SourceRegistryEntry(
        id=source_id,
        name=str(raw["name"]),
        type=str(raw["type"]),
        homepage_url=str(raw["homepage_url"]),
        access_method=str(raw["access_method"]),
        public_access=raw["public_access"],
        rights_status=str(raw["rights_status"]),
        metadata_quality=str(raw["metadata_quality"]),
        ingest_mode=str(raw["ingest_mode"]),
        media_types=[str(value) for value in media_types],
        priority=str(raw["priority"]),
        enabled=bool(raw.get("enabled", True)),
        estimated_item_count=raw.get("estimated_item_count"),
        notes=raw.get("notes"),
        rights_notes=raw.get("rights_notes"),
        extra=extra or None,
    )


def _load_into(
    path: Path,
    entries: list[SourceRegistryEntry],
    seen: set[str],
    visited: set[Path],
) -> None:
    resolved = path.resolve()
    if resolved in visited:
        raise ValueError(f"circular source registry include: {resolved}")
    visited.add(resolved)

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"source registry {resolved} must be a mapping")

    includes = payload.get("sources_from") or []
    if not isinstance(includes, list):
        raise ValueError("'sources_from' must be a list of registry paths")
    for include in includes:
        _load_into(resolved.parent / str(include), entries, seen, visited)

    raw_sources = payload.get("sources")
    if raw_sources is None and includes:
        return
    if not isinstance(raw_sources, list):
        raise ValueError("source registry must contain a top-level 'sources' list")
    for index, raw in enumerate(raw_sources):
        entries.append(_entry_from_dict(raw, index, seen))


def load_source_registry(path: str | Path) -> list[SourceRegistryEntry]:
    entries: list[SourceRegistryEntry] = []
    _load_into(Path(path), entries, set(), set())
    return entries


def enabled_sources(path: str | Path) -> list[SourceRegistryEntry]:
    return [entry for entry in load_source_registry(path) if entry.enabled]
