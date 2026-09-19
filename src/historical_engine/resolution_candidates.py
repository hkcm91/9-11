from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from historical_engine.ai.questions import DecisionQuestion, DecisionRequest

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(value: str | None) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value or "")}


def _normalized(value: str | None) -> str:
    return "".join(sorted(_tokens(value)))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _evidence_ids(raw_json: str | None) -> list[str]:
    if not raw_json:
        return []
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    values: list[str] = []
    for item in payload:
        if isinstance(item, dict):
            source_item_id = item.get("source_item_id")
            if isinstance(source_item_id, str) and source_item_id.strip():
                values.append(source_item_id.strip())
    return sorted(set(values))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _event_place_signatures(connection: sqlite3.Connection) -> dict[str, dict[str, set[str]]]:
    """Return event -> {region,mgrs,other} place labels from graph relationships."""

    rows = connection.execute(
        """
        SELECT r.subject_id AS event_id, r.predicate, e.canonical_name, e.attributes_json
        FROM relationships r
        JOIN entities e ON e.entity_id = r.object_id
        WHERE r.subject_type = 'event'
          AND r.object_type = 'place'
          AND r.predicate IN ('located_in', 'occurred_at')
        """
    ).fetchall()

    result: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        try:
            attrs = json.loads(row["attributes_json"] or "{}")
        except json.JSONDecodeError:
            attrs = {}
        kind = str((attrs or {}).get("place_kind") or "other")
        if kind not in {"region", "mgrs"}:
            kind = "other"
        label = str(row["canonical_name"] or "").strip().casefold()
        if not label:
            continue
        result.setdefault(row["event_id"], {"region": set(), "mgrs": set(), "other": set()})[kind].add(label)
    return result


def _generic_event_name(value: str | None) -> bool:
    tokens = _tokens(value)
    if not tokens:
        return True
    generic = {
        "other", "surv", "cache", "found", "cleared", "explosive", "hazard",
        "ied", "explosion", "rpt", "direct", "fire", "attack", "incident",
    }
    informative = {token for token in tokens if token not in generic and not token.isdigit()}
    return len(informative) <= 1


def entity_resolution_candidates(
    connection: sqlite3.Connection,
    *,
    collection_id: str,
    minimum_similarity: float = 0.72,
    max_pairs: int = 500,
) -> list[DecisionRequest]:
    """Generate candidate same-entity questions without merging anything."""

    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT entity_id, entity_type, canonical_name, evidence_json, attributes_json
        FROM entities
        WHERE collection_id = ?
        ORDER BY entity_type, canonical_name, entity_id
        """,
        (collection_id,),
    ).fetchall()

    candidates: list[tuple[float, DecisionRequest]] = []
    by_type: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_type.setdefault(row["entity_type"], []).append(row)

    for entity_type, typed_rows in by_type.items():
        for left, right in combinations(typed_rows, 2):
            left_tokens = _tokens(left["canonical_name"])
            right_tokens = _tokens(right["canonical_name"])
            score = _jaccard(left_tokens, right_tokens)

            left_compact = re.sub(r"[^a-z0-9]", "", (left["canonical_name"] or "").casefold())
            right_compact = re.sub(r"[^a-z0-9]", "", (right["canonical_name"] or "").casefold())
            exact_compact = bool(left_compact and left_compact == right_compact)
            if exact_compact:
                score = 1.0

            # Acronym-like containment is useful for organisations but remains a
            # candidate only, never an automatic merge.
            if entity_type in {"organization", "government_agency", "diplomatic_mission", "military_unit"}:
                shorter, longer = sorted(
                    ((left_compact, right_compact), (right_compact, left_compact)),
                    key=lambda pair: len(pair[0]),
                )[0]
                if shorter and len(shorter) >= 3 and shorter in longer:
                    score = max(score, 0.78)

            if score < minimum_similarity:
                continue

            evidence = sorted(
                set(_evidence_ids(left["evidence_json"])) | set(_evidence_ids(right["evidence_json"]))
            )
            request = DecisionRequest(
                question=DecisionQuestion.SAME_ENTITY,
                subject_id=left["entity_id"],
                object_id=right["entity_id"],
                task_type="entity_resolution",
                collection_id=collection_id,
                evidence_ids=evidence,
                context={
                    "candidate_score": round(score, 4),
                    "entity_type": entity_type,
                    "subject_name": left["canonical_name"],
                    "object_name": right["canonical_name"],
                    "heuristic": "normalized_name_similarity",
                },
            )
            candidates.append((score, request))

    candidates.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].context.get("entity_type", ""),
            pair[1].subject_id,
            pair[1].object_id or "",
        )
    )
    return [request for _, request in candidates[:max_pairs]]


def event_resolution_candidates(
    connection: sqlite3.Connection,
    *,
    collection_id: str,
    max_time_delta_hours: float = 12.0,
    minimum_name_similarity: float = 0.25,
    max_pairs: int = 500,
) -> list[DecisionRequest]:
    """Generate candidate same-event questions from time/type/name/structured attrs."""

    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT event_id, name, event_type, start_time, evidence_json, attributes_json
        FROM events
        WHERE collection_id = ?
        ORDER BY event_type, start_time, event_id
        """,
        (collection_id,),
    ).fetchall()

    place_signatures = _event_place_signatures(connection)

    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            attrs = json.loads(row["attributes_json"] or "{}")
        except json.JSONDecodeError:
            attrs = {}
        parsed.append(
            {
                "row": row,
                "time": _parse_iso(row["start_time"]),
                "attrs": attrs if isinstance(attrs, dict) else {},
            }
        )

    candidates: list[tuple[float, DecisionRequest]] = []
    for left, right in combinations(parsed, 2):
        lrow, rrow = left["row"], right["row"]
        if lrow["event_type"] != rrow["event_type"]:
            continue

        ltime, rtime = left["time"], right["time"]
        if ltime is None or rtime is None:
            continue

        delta_hours = abs((ltime - rtime).total_seconds()) / 3600.0
        if delta_hours > max_time_delta_hours:
            continue

        name_similarity = _jaccard(_tokens(lrow["name"]), _tokens(rrow["name"]))
        lattrs, rattrs = left["attrs"], right["attrs"]
        shared_category = (
            lattrs.get("category")
            and rattrs.get("category")
            and str(lattrs.get("category")).casefold() == str(rattrs.get("category")).casefold()
        )
        shared_type = (
            lattrs.get("type")
            and rattrs.get("type")
            and str(lattrs.get("type")).casefold() == str(rattrs.get("type")).casefold()
        )

        lplaces = place_signatures.get(lrow["event_id"], {"region": set(), "mgrs": set(), "other": set()})
        rplaces = place_signatures.get(rrow["event_id"], {"region": set(), "mgrs": set(), "other": set()})
        shared_mgrs = bool(lplaces["mgrs"] & rplaces["mgrs"])
        conflicting_mgrs = bool(lplaces["mgrs"] and rplaces["mgrs"] and not shared_mgrs)
        shared_region = bool(lplaces["region"] & rplaces["region"])

        time_score = max(0.0, 1.0 - delta_hours / max_time_delta_hours)
        score = (
            0.45 * name_similarity
            + 0.20 * time_score
            + (0.12 if shared_category else 0.0)
            + (0.08 if shared_type else 0.0)
            + (0.12 if shared_mgrs else 0.0)
            + (0.03 if shared_region else 0.0)
        )
        if conflicting_mgrs:
            score -= 0.25
        if _generic_event_name(lrow["name"]) and _generic_event_name(rrow["name"]) and not shared_mgrs:
            score -= 0.15
        score = max(0.0, min(1.0, score))

        if name_similarity < minimum_name_similarity and not (shared_category and shared_type):
            continue
        if score < 0.50:
            continue

        evidence = sorted(
            set(_evidence_ids(lrow["evidence_json"])) | set(_evidence_ids(rrow["evidence_json"]))
        )
        request = DecisionRequest(
            question=DecisionQuestion.SAME_EVENT,
            subject_id=lrow["event_id"],
            object_id=rrow["event_id"],
            task_type="event_link",
            collection_id=collection_id,
            evidence_ids=evidence,
            context={
                "candidate_score": round(score, 4),
                "event_type": lrow["event_type"],
                "subject_name": lrow["name"],
                "object_name": rrow["name"],
                "time_delta_hours": round(delta_hours, 3),
                "shared_category": bool(shared_category),
                "shared_type": bool(shared_type),
                "shared_mgrs": shared_mgrs,
                "conflicting_mgrs": conflicting_mgrs,
                "shared_region": shared_region,
                "subject_mgrs": sorted(lplaces["mgrs"]),
                "object_mgrs": sorted(rplaces["mgrs"]),
                "heuristic": "time_type_name_location_similarity_v2",
            },
        )
        candidates.append((score, request))

    candidates.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].subject_id,
            pair[1].object_id or "",
        )
    )
    return [request for _, request in candidates[:max_pairs]]


def build_resolution_candidates(
    database: Path | str,
    *,
    collection_id: str,
    max_entity_pairs: int = 500,
    max_event_pairs: int = 500,
) -> list[DecisionRequest]:
    connection = sqlite3.connect(Path(database))
    try:
        candidates = [
            *entity_resolution_candidates(
                connection,
                collection_id=collection_id,
                max_pairs=max_entity_pairs,
            ),
            *event_resolution_candidates(
                connection,
                collection_id=collection_id,
                max_pairs=max_event_pairs,
            ),
        ]
        return candidates
    finally:
        connection.close()


def request_to_dict(request: DecisionRequest) -> dict[str, Any]:
    return {
        "question": str(request.question),
        "subject_id": request.subject_id,
        "object_id": request.object_id,
        "task_type": request.task_type,
        "collection_id": request.collection_id,
        "evidence_ids": list(request.evidence_ids),
        "context": dict(request.context),
    }


def write_candidates(
    database: Path | str,
    output: Path | str,
    *,
    collection_id: str,
    max_entity_pairs: int = 500,
    max_event_pairs: int = 500,
) -> dict[str, int]:
    candidates = build_resolution_candidates(
        database,
        collection_id=collection_id,
        max_entity_pairs=max_entity_pairs,
        max_event_pairs=max_event_pairs,
    )
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for request in candidates:
            handle.write(json.dumps(request_to_dict(request), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    entity_count = sum(request.question == DecisionQuestion.SAME_ENTITY for request in candidates)
    event_count = sum(request.question == DecisionQuestion.SAME_EVENT for request in candidates)
    return {
        "total": len(candidates),
        "same_entity": entity_count,
        "same_event": event_count,
    }
