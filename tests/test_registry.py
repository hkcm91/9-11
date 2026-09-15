from __future__ import annotations

from pathlib import Path

import pytest

from archive.registry import enabled_sources, load_source_registry


def test_phase0_registry_loads() -> None:
    sources = load_source_registry(Path("config/sources.phase0.yaml"))
    assert len(sources) >= 10
    ids = {source.id for source in sources}
    assert "september11-digital-archive" in ids
    assert "internet-archive-understanding-911" in ids
    assert "nist-wtc-disaster-repository" in ids


def test_phase0_registry_has_no_duplicate_ids() -> None:
    sources = load_source_registry(Path("config/sources.phase0.yaml"))
    ids = [source.id for source in sources]
    assert len(ids) == len(set(ids))


def test_enabled_sources_filters_disabled(tmp_path: Path) -> None:
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        """
sources:
  - id: enabled
    name: Enabled
    type: archive
    homepage_url: https://example.com
    access_method: web
    public_access: true
    rights_status: review_required
    metadata_quality: medium
    ingest_mode: metadata_first
    media_types: [photo]
    priority: high
    enabled: true
  - id: disabled
    name: Disabled
    type: archive
    homepage_url: https://example.org
    access_method: web
    public_access: true
    rights_status: review_required
    metadata_quality: medium
    ingest_mode: metadata_first
    media_types: [video]
    priority: low
    enabled: false
""".strip(),
        encoding="utf-8",
    )
    assert [source.id for source in enabled_sources(registry)] == ["enabled"]


def test_registry_rejects_duplicate_ids(tmp_path: Path) -> None:
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        """
sources:
  - &source
    id: duplicate
    name: One
    type: archive
    homepage_url: https://example.com
    access_method: web
    public_access: true
    rights_status: review_required
    metadata_quality: medium
    ingest_mode: metadata_first
    media_types: [photo]
    priority: high
  - <<: *source
    name: Two
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate source id"):
        load_source_registry(registry)
