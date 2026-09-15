from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from archive.models import SourceItem
from archive.proposals import validate_proposal
from archive.store import ArchiveStore
from archive.workbench import WorkbenchQuery


def build_db(tmp_path: Path) -> tuple[Path, str]:
    db = tmp_path / "archive.sqlite"
    item = SourceItem(
        id="photo:1",
        source_id="photos",
        source_item_id="1",
        source_url="https://example.test/photo/1",
        title_raw="Photograph",
        media_type_raw="photo",
        metadata_raw={},
        ingested_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    proposal = validate_proposal({
        "agent_name": "geolocation-agent",
        "agent_version": "1.0",
        "task_id": "task:resolve_location:abc",
        "subject_id": item.id,
        "proposal_type": "spatial_claim",
        "proposal_value": {
            "location_kind": "capture_location",
            "latitude": 40.71,
            "longitude": -74.01,
        },
        "confidence": 0.82,
        "evidence": [{"source_item_id": item.id, "relationship": "supports"}],
    })
    with ArchiveStore(db) as store:
        store.put_source_item(item)
        store.put_proposal(proposal)
        store.review_proposal(
            proposal.proposal_id,
            reviewer="researcher",
            new_status="reviewed",
            note="Checked source geometry.",
        )
    return db, proposal.proposal_id


def test_proposal_queue_filters_by_review_status(tmp_path: Path) -> None:
    db, proposal_id = build_db(tmp_path)
    with WorkbenchQuery(db) as query:
        reviewed = query.proposal_queue(statuses={"reviewed"})
        proposed = query.proposal_queue(statuses={"proposed"})

    assert len(reviewed) == 1
    assert reviewed[0]["proposal_id"] == proposal_id
    assert reviewed[0]["review_status"] == "reviewed"
    assert proposed == []


def test_proposal_bundle_includes_review_history_and_record(tmp_path: Path) -> None:
    db, proposal_id = build_db(tmp_path)
    with WorkbenchQuery(db) as query:
        bundle = query.proposal_bundle(proposal_id)

    assert bundle is not None
    assert bundle["proposal"]["proposal_id"] == proposal_id
    assert bundle["record"]["id"] == "photo:1"
    assert len(bundle["reviews"]) == 1
    assert bundle["reviews"][0]["new_status"] == "reviewed"


def test_item_review_bundle_combines_evidence_and_proposals(tmp_path: Path) -> None:
    db, proposal_id = build_db(tmp_path)
    with WorkbenchQuery(db) as query:
        bundle = query.item_review_bundle("photo:1")

    assert bundle is not None
    assert bundle["record"]["id"] == "photo:1"
    assert len(bundle["observations"]) == 1
    assert bundle["agent_proposals"][0]["proposal"]["proposal_id"] == proposal_id
    assert bundle["agent_proposals"][0]["reviews"][0]["reviewer"] == "researcher"
