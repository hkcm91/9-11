from __future__ import annotations

import json

from archive.corpus import load_jsonl


def test_load_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "sample.jsonl"
    payload = {
        "id": "source:1",
        "source_id": "source",
        "source_item_id": "1",
        "source_url": "https://example.test/1",
        "title_raw": "Example",
        "metadata_raw": {"collection": "demo"},
        "ingested_at": "2026-09-14T23:00:00+00:00",
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    records = load_jsonl(path)
    assert len(records) == 1
    assert records[0].id == "source:1"
    assert records[0].metadata_raw["collection"] == "demo"
