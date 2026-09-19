from pathlib import Path

from archive.corpus import load_jsonl
from archive.store import ArchiveStore
from historical_engine.collection_registry import get_collection
from historical_engine.graph_derivation import materialize_graph
from historical_engine.graph_quality import analyze_graph_quality, render_markdown

FIXTURE = Path("src/evidence_collections/wikileaks/fixtures/real_sample.jsonl")


def test_quality_report_on_real_wikileaks_fixture(tmp_path: Path) -> None:
    database = tmp_path / "wikileaks.sqlite"
    records = load_jsonl(FIXTURE)
    collection = get_collection("wikileaks")

    with ArchiveStore(database) as store:
        materialize_graph(records, collection, store)

    report = analyze_graph_quality(database, high_degree_threshold=2)

    assert report["counts"]["source_records"] == 2
    assert report["counts"]["events"] == 1
    assert report["counts"]["relationships"] >= 7
    assert report["source_counts"] == {
        "wikileaks-plusd": 1,
        "wikileaks-war-diaries": 1,
    }
    assert report["placeholder_entities"] == []
    assert report["dangling_relationship_endpoints"] == []
    assert report["missing_event_start_times"] == []
    assert report["invalid_event_time_ranges"] == []
    assert all(row["severity"] != "high" for row in report["warnings"])
    assert report["high_degree_nodes"]


def test_quality_report_markdown_is_human_readable(tmp_path: Path) -> None:
    database = tmp_path / "wikileaks.sqlite"
    records = load_jsonl(FIXTURE)
    collection = get_collection("wikileaks")

    with ArchiveStore(database) as store:
        materialize_graph(records, collection, store)

    rendered = render_markdown(analyze_graph_quality(database))

    assert "# Evidence Graph Quality Report" in rendered
    assert "Relationship predicates" in rendered
    assert "Warnings" in rendered
