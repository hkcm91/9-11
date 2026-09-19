import json

import pytest

from archive.models import SourceItem
from archive.store import ArchiveStore
from evidence_collections.september11.anchor_ordering import minute_candidates, build_ordering, review_requests, run
from historical_engine.ai.questions import DecisionResponse


def test_minute_boundary_uncertainty_never_collapses_to_one_minute():
    assert len(minute_candidates("2001-09-11T08:59:59-04:00", "2001-09-11T08:59:59-04:00", 3000, 3000)) == 2
    assert minute_candidates(None, "2001-09-11T09:03:00-04:00") == []
    assert minute_candidates("2001-09-11T13:03:00+00:00", "2001-09-11T13:03:59+00:00") == ["2001-09-11T09:03:00-04:00"]
    with pytest.raises(ValueError):
        minute_candidates("2001-09-11T09:03:00", "2001-09-11T09:03:01")


def seed(tmp_path):
    db = tmp_path / "archive.sqlite"
    catalog = {"anchors": [{"id": "anchor", "reported_time": "2001-09-11T09:03:08-04:00", "uncertainty_seconds": None}],
               "matches": [{"asset_id": "photos:1:attachment:2", "anchor_id": "anchor"}],
               "observations": [{"asset_id": f"photos:1:attachment:{i}", "observation": "Test observation"} for i in (1,2)],
               "sequences": [{"asset_ids": ["photos:1:attachment:1", "photos:1:attachment:2"], "basis": "Test sequence"}]}
    with ArchiveStore(db) as store:
        store.put_source_items([SourceItem(
            id="photos:1", source_id="photos", source_item_id="1", source_url="https://example.test/source",
            media_type_raw="photo", metadata_raw={"media_attachments": [{"id": i, "url": f"https://example.test/{i}.jpg"} for i in (1,2)]},
        ), SourceItem(id="video:1", source_id="video", source_item_id="1", source_url="https://example.test/tv", media_type_raw="movies")])
        for subject,kind in [("photos:1","capture_time"),("video:1","recording_time")]:
            p=tmp_path / "claim.jsonl"
            p.write_text(json.dumps({"subject_id": subject, "time_kind": kind, "start_time": "2001-09-11T09:03:00-04:00", "end_time": "2001-09-11T09:03:59-04:00", "confidence": .7,"status":"proposed"})+"\n")
            store.import_claim_jsonl(p,"temporal")
    path=tmp_path / "catalog.json";path.write_text(json.dumps(catalog))
    return db,catalog,path


def test_attachment_scope_and_broadcast_separation(tmp_path):
    db,catalog,_ = seed(tmp_path)
    with ArchiveStore(db) as store:
        assets=build_ordering(store,catalog)
    assert [a["status"] for a in assets] == ["group_timing_only","anchor_match_proposed","broadcast_interval_only"]
    assert assets[0].get("anchor_id") is None
    assert assets[1]["uncertainty_seconds"] is None
    assert assets[2]["candidate_minutes"] == []


def test_requests_have_observations_and_anchor_evidence_not_claimed_vision(tmp_path):
    _,catalog,_=seed(tmp_path)
    requests=list(review_requests(catalog))
    assert len(requests)==2
    assert requests[0].evidence_ids==["photos:1:attachment:2","anchor"]
    assert "not image pixels" in requests[0].context["rules"]
    assert requests[1].context["claim"]["type"]=="before"


def test_unknown_match_and_high_confidence_order_do_not_change_capture_claims(tmp_path):
    class Provider:
        def decide(self, request):
            return DecisionResponse(question=request.question, answer="unknown" if request.object_id=="anchor" else "supports",
                                    confidence=.99, rationale="Test decision", provider="fake", model="test", evidence_ids=request.evidence_ids)
    db,_,path=seed(tmp_path)
    with ArchiveStore(db) as store:
        before=[tuple(r) for r in store.connection.execute("SELECT * FROM temporal_claims")]
    summary=run(db,tmp_path/"out",catalog_path=path,provider=Provider())
    assert summary["status_counts"]["anchor_match_needs_review"]==1
    with ArchiveStore(db) as store:
        assert before==[tuple(r) for r in store.connection.execute("SELECT * FROM temporal_claims")]
        assert {r[0] for r in store.connection.execute("SELECT review_status FROM agent_proposals")}=={"proposed"}
