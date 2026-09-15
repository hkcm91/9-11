from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


def load_source_registry(path: str | Path) -> list[SourceRegistryEntry]:
    registry_path = Path(path)
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    raw_sources = payload.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("source registry must contain a top-level 'sources' list")

    entries: list[SourceRegistryEntry] = []
    seen: set[str] = set()
    required = {
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

    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ValueError(f"source registry entry {index} must be a mapping")
        missing = sorted(required - raw.keys())
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

        known = {
            "id", "name", "type", "homepage_url", "access_method", "public_access",
            "rights_status", "metadata_quality", "ingest_mode", "media_types", "priority",
            "enabled", "estimated_item_count", "notes", "rights_notes",
        }
        extra = {key: value for key, value in raw.items() if key not in known}
        entries.append(
            SourceRegistryEntry(
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
        )
    return entries


def enabled_sources(path: str | Path) -> list[SourceRegistryEntry]:
    return [entry for entry in load_source_registry(path) if entry.enabled]
