from pathlib import Path

from archive.corpus import load_jsonl
from archive.store import ArchiveStore
from historical_engine.collection_registry import get_collection
from historical_engine.graph_derivation import materialize_graph

FIXTURE = Path("src/evidence_collections/wikileaks/fixtures/real_sample.jsonl")


def test_real_wikileaks_fixture_materializes_typed_graph(tmp_path: Path) -> None:
    records = load_jsonl(FIXTURE)
    collection = get_collection("wikileaks")
    database = tmp_path / "wikileaks.sqlite"

    with ArchiveStore(database) as store:
        result = materialize_graph(records, collection, store)
        stats = store.stats()

        predicates = {
            row[0]
            for row in store.connection.execute(
                "SELECT DISTINCT predicate FROM relationships"
            ).fetchall()
        }
        event = store.connection.execute(
            "SELECT name, event_type, start_time FROM events LIMIT 1"
        ).fetchone()
        references = store.connection.execute(
            "SELECT COUNT(*) FROM relationships WHERE predicate = 'references_document'"
        ).fetchone()[0]

    assert result["records"] == 2
    assert result["entities"] >= 8
    assert result["events"] == 1
    assert result["relationships"] >= 7

    assert stats["source_records"] == 2
    assert stats["events"] == 1
    assert stats["relationships"] >= 7
    assert references == 2

    assert {
        "sent_from",
        "sent_to",
        "references_document",
        "describes",
        "located_in",
        "occurred_at",
    } <= predicates

    assert event["event_type"] == "sigact"
    assert event["start_time"].startswith("2004-07-11T17:29:00")


def test_real_sample_graph_remains_proposed(tmp_path: Path) -> None:
    records = load_jsonl(FIXTURE)
    collection = get_collection("wikileaks")

    with ArchiveStore(tmp_path / "wikileaks.sqlite") as store:
        materialize_graph(records, collection, store)

        entity_statuses = {
            row[0] for row in store.connection.execute("SELECT DISTINCT status FROM entities")
        }
        event_statuses = {
            row[0] for row in store.connection.execute("SELECT DISTINCT status FROM events")
        }
        relation_statuses = {
            row[0] for row in store.connection.execute("SELECT DISTINCT status FROM relationships")
        }
        assertion_levels = {
            row[0]
            for row in store.connection.execute(
                "SELECT DISTINCT assertion_level FROM relationships"
            )
        }

    assert entity_statuses == {"proposed"}
    assert event_statuses == {"proposed"}
    assert relation_statuses == {"proposed"}
    assert "established" not in assertion_levels
    assert "corroborated" not in assertion_levels
