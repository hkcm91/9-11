import json

import pytest

from archive.derived import derive_temporal_claims, serialize_temporal_claim
from archive.models import SourceItem
from archive.store import ArchiveStore
from evidence_collections.september11.media_timing import audit, timing_requests
from historical_engine.ai.questions import DecisionResponse


def seed(tmp_path):
    records = [SourceItem(
        id=f"photo:{i}", source_id="archdisk-911-photo-map", source_item_id=str(i),
        source_url="https://archdisk.com/photomap", media_type_raw="photo",
        metadata_raw={"folder_path": "8:46-9:03AM"},
    ) for i in range(5)]
    records.append(SourceItem(
        id="broadcast:1", source_id="internet-archive-understanding-911", source_item_id="1",
        source_url="https://archive.org/details/example", media_type_raw="video",
        metadata_raw={"start_time": "2001-09-11 12:46:00", "stop_time": "2001-09-11 13:16:00"},
    ))
    database = tmp_path / "archive.sqlite"
    claims = tmp_path / "claims.jsonl"
    claims.write_text("".join(json.dumps(serialize_temporal_claim(c)) + "\n"
                              for c in derive_temporal_claims(records)), encoding="utf-8")
    with ArchiveStore(database) as store:
        store.put_source_items(records)
        store.import_claim_jsonl(claims, "temporal")
    return database


def test_bounded_stratified_sample_keeps_broadcast_distinct(tmp_path):
    with ArchiveStore(seed(tmp_path)) as store:
        requests = timing_requests(store, 2)
        assert {r.context["claim"]["time_kind"] for r in requests} == {"capture_time", "recording_time"}
        assert all(r.object_id and r.evidence_ids == [r.subject_id] for r in requests)
        assert "start_time" in requests[1].context["source_metadata"]
        for limit in (0, 501):
            with pytest.raises(ValueError):
                timing_requests(store, limit)


def test_even_high_confidence_support_cannot_verify_or_change_time(tmp_path):
    class Provider:
        def decide(self, request):
            return DecisionResponse(question=request.question, answer="supports", confidence=0.99,
                                    rationale="Metadata supports the stated interval only.",
                                    provider="test", model="test", evidence_ids=request.evidence_ids)
    database = seed(tmp_path)
    with ArchiveStore(database) as store:
        before = [tuple(r) for r in store.connection.execute("SELECT * FROM temporal_claims")]
    summary = audit(database, tmp_path / "reports", limit=2, provider=Provider())
    assert summary["decisions"] == summary["proposals"] == 2
    with ArchiveStore(database) as store:
        assert before == [tuple(r) for r in store.connection.execute("SELECT * FROM temporal_claims")]
        assert {r[0] for r in store.connection.execute("SELECT review_status FROM agent_proposals")} == {"proposed"}
