"""Attachment-level, evidence-bounded minute ordering with optional Jev review."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from archive.store import ArchiveStore
from evidence_collections.september11.collection import build_collection
from historical_engine.ai.batch import decision_to_dict
from historical_engine.ai.jev import JevDecisionProvider
from historical_engine.ai.pipeline import run_decision
from historical_engine.ai.questions import DecisionQuestion, DecisionRequest

CATALOG = Path(__file__).parent / "anchors" / "nist-pilot.json"
NY = ZoneInfo("America/New_York")


def minute_candidates(start, end, before_ms=0, after_ms=0):
    """Closed bounds, including uncertainty; open bounds must remain unplaced."""
    if not start or not end:
        return []
    if (before_ms or 0) < 0 or (after_ms or 0) < 0:
        raise ValueError("uncertainty cannot be negative")
    a, b = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (start, end))
    if a.tzinfo is None or b.tzinfo is None:
        raise ValueError("ordering requires timezone-aware bounds")
    a = (a - timedelta(milliseconds=before_ms or 0)).astimezone(NY)
    b = (b + timedelta(milliseconds=after_ms or 0)).astimezone(NY)
    if b < a or (b-a).total_seconds() > 86400:
        return []
    cursor = a.replace(second=0, microsecond=0)
    minutes = []
    while cursor <= b:
        minutes.append(cursor.isoformat())
        cursor += timedelta(minutes=1)
    return minutes


def review_requests(catalog):
    anchors = {x["id"]: x for x in catalog["anchors"]}
    observations = {x["asset_id"]: x for x in catalog["observations"]}
    common = (
        "Assess a proposed ordering using ONLY the supplied evidence. You have textual "
        "observations from a separate visual inspection, not image pixels. Do not claim to "
        "see the images. Observations and matches are unverified. Unknown is valid. "
        "Do not infer camera cadence, absolute time or identical capture from a shared "
        "photographer, similar smoke, filename alone or generic event label. "
        "A source-reported minute is not a verified minute. Do not add five seconds "
        "to an already adjusted published NIST time. Never invent metadata."
    )
    for match in catalog["matches"]:
        anchor = anchors[match["anchor_id"]]
        yield DecisionRequest(
            question=DecisionQuestion.SUPPORTS_CLAIM,
            subject_id=match["asset_id"], object_id=anchor["id"],
            collection_id="september11", task_type="resolve_time",
            evidence_ids=[match["asset_id"], anchor["id"]],
            context={"claim": {"type": "reported_minute_match", "minute": anchor["reported_time"][:16]},
                     "anchor": anchor, "observation": observations[match["asset_id"]],
                     "match": match, "rules": common},
        )
    for sequence in catalog["sequences"]:
        for left, right in zip(sequence["asset_ids"], sequence["asset_ids"][1:]):
            yield DecisionRequest(
                question=DecisionQuestion.SUPPORTS_CLAIM, subject_id=left, object_id=right,
                collection_id="september11", task_type="resolve_time",
                evidence_ids=[left, right],
                context={"claim": {"type": "before", "left": left, "right": right},
                         "observations": [observations[left], observations[right]],
                         "sequence_basis": sequence["basis"], "rules": common},
            )


def build_ordering(store, catalog):
    anchors = {a["id"]: a for a in catalog["anchors"]}
    matches = {m["asset_id"]: m for m in catalog["matches"]}
    observed = {o["asset_id"]: o for o in catalog["observations"]}
    claims, recordings = {}, {}
    for row in store.connection.execute("SELECT subject_id, claim_json FROM temporal_claims WHERE time_kind='capture_time'"):
        claims.setdefault(row[0], []).append(json.loads(row[1]))
    for row in store.connection.execute("SELECT subject_id, claim_json FROM temporal_claims WHERE time_kind='recording_time'"):
        recordings.setdefault(row[0], []).append(json.loads(row[1]))
    assets = []
    for row in store.connection.execute("SELECT * FROM source_records ORDER BY id"):
        metadata = json.loads(row["metadata_json"])
        attachments = metadata.get("media_attachments") or []
        if not attachments and row["media_type_raw"] not in {"photo", "video", "movies"}:
            continue
        candidates = attachments or [{"id": None, "url": row["source_url"]}]
        for attachment in candidates:
            asset_id = row["id"] + f':attachment:{attachment["id"]}' if attachment["id"] is not None else row["id"]
            item = {"asset_id": asset_id, "parent_id": row["id"], "url": attachment["url"],
                    "title": row["title_raw"], "creator": row["creator_raw"],
                    "status": "unplaced", "candidate_minutes": [], "review_status": "proposed",
                    "capture_claims": claims.get(row["id"], []),
                    "recording_claims": recordings.get(row["id"], []),
                    "observation": observed.get(asset_id)}
            if asset_id in matches:
                anchor = anchors[matches[asset_id]["anchor_id"]]
                item.update(status="anchor_match_proposed", anchor_id=anchor["id"],
                            reported_minute=anchor["reported_time"][:16],
                            uncertainty_seconds=anchor["uncertainty_seconds"],
                            candidate_minutes=[datetime.fromisoformat(anchor["reported_time"]).replace(second=0).isoformat()])
            elif item["capture_claims"]:
                # Multiple claims are alternatives; a union never pretends conflicts
                # agree. Multi-attachment record times are not per-image timestamps.
                minutes = set()
                for claim in item["capture_claims"]:
                    minutes.update(minute_candidates(claim.get("start_time"), claim.get("end_time"),
                                                    claim.get("uncertainty_before_ms"), claim.get("uncertainty_after_ms")))
                item["candidate_minutes"] = sorted(minutes)
                if len(candidates) > 1:
                    item["status"] = "group_timing_only"
                elif len(minutes) == 1:
                    item["status"] = "source_reported_minute"
                elif minutes:
                    item["status"] = "range_only"
                else:
                    item["status"] = "open_bound_only"
            elif item["recording_claims"]:
                item["status"] = "broadcast_interval_only"
            assets.append(item)
    return assets


def run(database, output, *, catalog_path=CATALOG, provider=None):
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    decisions = []
    with ArchiveStore(database) as store:
        assets = build_ordering(store, catalog)
        available = {a["asset_id"] for a in assets}
        if any(o["asset_id"] not in available for o in catalog["observations"]):
            raise ValueError("anchor pilot requires the expanded corpus containing all observed attachments")
        # Separate research tables; never mutate capture claims or source records.
        store.connection.executescript("""
            CREATE TABLE IF NOT EXISTS reference_image_anchors (
                anchor_id TEXT PRIMARY KEY, anchor_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS media_minute_candidates (
                asset_id TEXT PRIMARY KEY, candidate_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS anchor_ordering_decisions (
                decision_key TEXT PRIMARY KEY, decision_json TEXT NOT NULL);
        """)
        for anchor in catalog["anchors"]:
            store.connection.execute("INSERT OR REPLACE INTO reference_image_anchors VALUES (?,?)", (anchor["id"], json.dumps(anchor)))
        if provider is not None:
            with (output / "jev-anchor-decisions.jsonl").open("w", encoding="utf-8") as handle:
                for request in review_requests(catalog):
                    decision = run_decision(provider, request, collection=build_collection(), agent_version="anchor-ordering-v1")
                    payload = decision_to_dict(decision); decisions.append(payload)
                    handle.write(json.dumps(payload) + "\n"); handle.flush()
                    key = request.subject_id + "|" + request.object_id
                    store.connection.execute("INSERT OR REPLACE INTO anchor_ordering_decisions VALUES (?,?)", (key, json.dumps(payload)))
                    if decision.proposal:
                        store.put_proposal(decision.proposal)
                    store.connection.commit()
        for asset in assets:
            related = [d for d in decisions if d["subject_id"] == asset["asset_id"]]
            asset["jev_reviews"] = [{k: d[k] for k in ("object_id", "answer", "confidence", "routing")} for d in related]
            # A negative/unknown model review never becomes a minute placement.
            match_reviews = [d for d in related if d["context"]["claim"]["type"] == "reported_minute_match"]
            if match_reviews and match_reviews[0]["answer"] != "supports":
                asset["status"] = "anchor_match_needs_review"
            store.connection.execute("INSERT OR REPLACE INTO media_minute_candidates VALUES (?,?)", (asset["asset_id"], json.dumps(asset)))
        store.connection.commit()
        (output / "minute-ordering.json").write_text(json.dumps({
            "timezone": "America/New_York", "scope": "Candidate ordering, never a verified total order",
            "anchors": catalog["anchors"], "sequences": catalog["sequences"], "assets": assets,
        }, indent=2) + "\n", encoding="utf-8")
        (output / "nist-anchor-catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
        summary = {"assets": len(assets), "anchors": len(catalog["anchors"]),
                   "visually_inspected_assets": len(catalog["observations"]),
                   "proposed_anchor_matches": len(catalog["matches"]),
                   "status_counts": dict(Counter(a["status"] for a in assets)),
                   "jev_decisions": len(decisions),
                   "jev_answers": dict(Counter(d["answer"] for d in decisions)),
                   "jev_routing": dict(Counter(d["routing"]["decision"] for d in decisions)),
                   "verified_by_this_run": 0}
        (output / "anchor-ordering-summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jev", action="store_true")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("database must already exist")
    print(json.dumps(run(args.database, args.output, provider=JevDecisionProvider.from_env() if args.jev else None), indent=2))


if __name__ == "__main__":
    main()
