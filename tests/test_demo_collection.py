"""The demo collection proves the engine runs a second, unrelated corpus."""

from __future__ import annotations

import json
from pathlib import Path

from archive.cli import main
from archive.store import ArchiveStore
from evidence_collections.demo_history.collection import DOCUMENT_ID, TESTIMONY_ID
from evidence_collections.demo_history.pipeline import load_records, run_pipeline


def test_fixtures_cover_the_required_shapes() -> None:
    records = load_records()
    assert len(records) == 3
    roles = {record.id: record.media_type_raw for record in records}
    assert roles == {
        DOCUMENT_ID: "document",
        TESTIMONY_ID: "oral_history",
        "demo:photo:mill-facade": "photograph",
    }


def test_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    summary = run_pipeline(tmp_path / "demo.sqlite")

    assert summary["collection_id"] == "demo_history"
    assert summary["records"] == 3
    assert summary["tasks"] > 0
    counts = summary["table_counts"]
    assert counts["source_records"] == 3
    assert counts["source_observations"] == 3
    assert counts["temporal_claims"] == 2
    assert counts["entity_claims"] == 1
    assert counts["entities"] == 2
    assert counts["events"] == 1
    assert counts["relationships"] == 2
    assert counts["claim_relations"] == 1
    assert counts["collections"] == 1


def test_the_contradiction_is_recorded_not_resolved(tmp_path: Path) -> None:
    """Two sources disagree about when the fire started. Both survive."""

    database = tmp_path / "demo.sqlite"
    run_pipeline(database)
    with ArchiveStore(database) as store:
        claims = store.connection.execute(
            "SELECT subject_id, start_time FROM temporal_claims ORDER BY subject_id"
        ).fetchall()
        relation = store.connection.execute(
            "SELECT relation, subject_claim_id, object_claim_id, status FROM claim_relations"
        ).fetchone()
        claim_ids = {
            row["subject_id"]: row["claim_id"]
            for row in store.connection.execute(
                "SELECT claim_id, subject_id FROM temporal_claims"
            ).fetchall()
        }

    # Neither claim was averaged away or deleted.
    assert len(claims) == 2
    assert len({row["start_time"] for row in claims}) == 2

    assert relation["relation"] == "contradicts"
    assert relation["status"] == "proposed"
    assert relation["subject_claim_id"] == claim_ids[TESTIMONY_ID]
    assert relation["object_claim_id"] == claim_ids[DOCUMENT_ID]


def test_demo_pipeline_is_reachable_from_the_cli(tmp_path: Path, capsys) -> None:
    exit_code = main(["run-demo-pipeline", "--database", str(tmp_path / "cli.sqlite")])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["collection_id"] == "demo_history"


def test_running_twice_does_not_duplicate_rows(tmp_path: Path) -> None:
    database = tmp_path / "demo.sqlite"
    first = run_pipeline(database)
    second = run_pipeline(database)
    assert first["table_counts"] == second["table_counts"]
