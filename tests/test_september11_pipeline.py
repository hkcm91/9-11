"""The September 11 pipeline must behave exactly as it did before the refactor.

This walks the full sequence — records in, profile, dedupe, priorities, claims,
work queue, rights queue, SQLite store, proposal review, query — through the
public ``archive.*`` API, with no collection argument anywhere. That is how
every existing workflow calls it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from archive.corpus import reconcile_source_snapshots
from archive.dedupe import find_candidates
from archive.derived import (
    derive_entity_claims,
    derive_spatial_claims,
    derive_temporal_claims,
    serialize_entity_claim,
    serialize_spatial_claim,
    serialize_temporal_claim,
)
from archive.models import SourceItem
from archive.profiling import profile_records
from archive.proposals import validate_proposal
from archive.quality import prioritize_records
from archive.query import ArchiveQuery
from archive.registry import enabled_sources, load_source_registry
from archive.store import ArchiveStore
from archive.work_queue import build_rights_queue, build_work_queue

LEGACY_REGISTRY = Path("config/sources.phase0.yaml")
COLLECTION_REGISTRY = Path("src/evidence_collections/september11/sources.yaml")


def _records() -> list[SourceItem]:
    ingested = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        SourceItem(
            id="ia:1",
            source_id="internet-archive-understanding-911",
            source_item_id="1",
            source_url="https://example.test/ia/1",
            title_raw="Broadcast segment",
            metadata_raw={
                "start_time": "2001-09-11 12:46:00",
                "stop_time": "2001-09-11 13:16:00",
                "contributor": "A Broadcaster",
            },
            ingested_at=ingested,
        ),
        SourceItem(
            id="archdisk:1",
            source_id="archdisk-911-photo-map",
            source_item_id="1",
            source_url="https://example.test/archdisk/1",
            title_raw="Street photograph",
            creator_raw="A Photographer",
            metadata_raw={
                "time_taken_raw": "09:15",
                "resolved_latitude": 40.7115,
                "resolved_longitude": -74.0130,
                "mapped_address": "Church St facing north",
            },
            ingested_at=ingested,
        ),
        SourceItem(
            id="911da:1",
            source_id="september-11-digital-archive",
            source_item_id="1",
            source_url="https://example.test/911da/1",
            title_raw="Smith, Jane.mp3",
            metadata_raw={"collection_id": 267},
            ingested_at=ingested,
        ),
        SourceItem(
            id="fdny:1",
            source_id="september-11-digital-archive",
            source_item_id="2",
            source_url="https://example.test/911da/2",
            title_raw="Incident Action Plan: 9/14/01 - 9/15/01",
            media_type_raw="document",
            ingested_at=ingested,
        ),
    ]


# --- registry ----------------------------------------------------------------


def test_the_legacy_registry_path_still_resolves() -> None:
    assert len(load_source_registry(LEGACY_REGISTRY)) >= 10
    assert len(enabled_sources(LEGACY_REGISTRY)) >= 10


def test_the_shim_and_the_collection_registry_agree() -> None:
    legacy = [entry.id for entry in load_source_registry(LEGACY_REGISTRY)]
    canonical = [entry.id for entry in load_source_registry(COLLECTION_REGISTRY)]
    assert legacy == canonical


def test_a_circular_include_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("sources_from: [b.yaml]\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("sources_from: [a.yaml]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="circular"):
        load_source_registry(tmp_path / "a.yaml")


# --- deterministic derivations ----------------------------------------------


def test_deterministic_claims_are_unchanged() -> None:
    records = _records()

    temporal = derive_temporal_claims(records)
    kinds = {(claim.subject_id, claim.time_kind.value) for claim in temporal}
    assert ("ia:1", "recording_time") in kinds
    assert ("archdisk:1", "capture_time") in kinds
    assert ("fdny:1", "document_coverage") in kinds
    assert all(claim.status.value == "proposed" for claim in temporal)
    assert all(claim.evidence for claim in temporal)

    spatial = derive_spatial_claims(records)
    assert [claim.subject_id for claim in spatial] == ["archdisk:1"]
    assert spatial[0].heading_deg == pytest.approx(0.0)

    entities = derive_entity_claims(records)
    by_subject = {claim.subject_id: claim for claim in entities}
    assert by_subject["ia:1"].role.value == "broadcaster"
    assert by_subject["archdisk:1"].role.value == "photographer"
    assert by_subject["911da:1"].role.value == "interviewee"


# --- queues ------------------------------------------------------------------


def test_work_queue_roles_and_suppressions_are_unchanged() -> None:
    tasks = build_work_queue(_records())
    by_item: dict[str, set[str]] = {}
    roles: dict[str, str] = {}
    for task in tasks:
        by_item.setdefault(task.item_id, set()).add(task.task_type)
        roles[task.item_id] = task.record_role

    assert roles == {
        "ia:1": "broadcast",
        "archdisk:1": "photo",
        "911da:1": "testimony",
        "fdny:1": "document",
    }
    # A broadcast item never gets a camera-location task.
    assert "resolve_location" not in by_item["ia:1"]
    # A parsed Incident Action Plan needs neither a time nor a location task.
    assert "resolve_time" not in by_item.get("fdny:1", set())
    assert "resolve_location" not in by_item.get("fdny:1", set())
    # Rights stay out of the research queue.
    assert all("resolve_rights" not in types for types in by_item.values())


def test_rights_queue_is_produced_separately() -> None:
    rights = build_rights_queue(_records())
    assert rights
    assert {task.task_type for task in rights} == {"resolve_rights"}


def test_priorities_still_reflect_per_source_value() -> None:
    priorities = {row.item_id: row for row in prioritize_records(_records())}
    assert priorities["ia:1"].enrichment_priority > 0
    assert "missing map location" in priorities["911da:1"].reasons


def test_profile_and_dedupe_still_run() -> None:
    records = reconcile_source_snapshots(_records())
    assert profile_records(records).to_dict()["total_records"] == 4
    assert isinstance(find_candidates(records), list)


# --- store and query ---------------------------------------------------------


def test_the_full_pipeline_materializes_sqlite(tmp_path: Path) -> None:
    records = _records()
    paths = {}
    for name, claims, serializer in (
        ("temporal", derive_temporal_claims(records), serialize_temporal_claim),
        ("spatial", derive_spatial_claims(records), serialize_spatial_claim),
        ("entity", derive_entity_claims(records), serialize_entity_claim),
    ):
        path = tmp_path / f"{name}.jsonl"
        path.write_text(
            "".join(json.dumps(serializer(claim), ensure_ascii=False) + "\n" for claim in claims),
            encoding="utf-8",
        )
        paths[name] = path

    database = tmp_path / "archive.sqlite"
    with ArchiveStore(database) as store:
        store.put_source_items(records)
        for kind, path in paths.items():
            store.import_claim_jsonl(path, kind)
        proposal = validate_proposal(
            {
                "agent_name": "agent",
                "agent_version": "1",
                "subject_id": "archdisk:1",
                "proposal_type": "spatial_claim",
                "proposal_value": {"latitude": 40.71, "longitude": -74.01},
                "confidence": 0.7,
                "evidence": [{"source_item_id": "archdisk:1"}],
            }
        )
        store.put_proposal(proposal)
        store.review_proposal(proposal.proposal_id, reviewer="researcher", new_status="reviewed")
        stats = store.stats()

    assert stats["source_records"] == 4
    assert stats["source_observations"] == 4
    assert stats["temporal_claims"] == 3
    assert stats["spatial_claims"] == 1
    assert stats["entity_claims"] == 3
    assert stats["proposal_reviews"] == 1

    with ArchiveQuery(database) as query:
        nearby = query.nearby(40.7115, -74.0130, radius_m=500)
    assert [result.subject_id for result in nearby] == ["archdisk:1"]
