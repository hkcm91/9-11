"""End-to-end run of the synthetic collection through the generic engine.

Nothing in here is demo-specific machinery: it calls the same corpus loader,
prioritiser, work queue, claim derivation, SQLite store and graph writers the
September 11 pipeline uses. That is the point — if this function needs a
special case, the engine is not yet generic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from archive.corpus import load_jsonl, reconcile_source_snapshots
from archive.models import SourceItem
from archive.store import ArchiveStore
from evidence_collections.demo_history.collection import (
    RECORDS_PATH,
    build_collection,
    demo_claim_relation,
    demo_entities,
    demo_event,
    demo_relationships,
)
from historical_engine.claims import serialize_claim
from historical_engine.quality import EnrichmentPriority, prioritize_item
from historical_engine.work_queue import EnrichmentTask, build_work_queue


def load_records(path: Path | str = RECORDS_PATH) -> list[SourceItem]:
    return reconcile_source_snapshots(load_jsonl(Path(path)))


def run_pipeline(database: Path | str, *, records_path: Path | str = RECORDS_PATH) -> dict[str, Any]:
    """Ingest, derive, queue and materialise the synthetic corpus."""

    collection = build_collection()
    records = load_records(records_path)

    priorities: list[EnrichmentPriority] = [
        prioritize_item(
            item,
            source_value=collection.source_value(item.source_id),
            extra_reasons=collection.hooks.priority_reasons,
        )
        for item in records
    ]
    tasks: list[EnrichmentTask] = build_work_queue(records, collection)

    temporal = [
        claim for item in records for claim in (collection.hooks.derive_temporal or (lambda _: []))(item)
    ]
    entities = [
        claim for item in records for claim in (collection.hooks.derive_entities or (lambda _: []))(item)
    ]

    ontology = collection.ontology
    with ArchiveStore(database) as store:
        store.put_collection(collection.record())
        store.put_source_items(records)

        temporal_ids: dict[str, str] = {}
        for claim in temporal:
            payload = serialize_claim(claim)
            temporal_ids[claim.subject_id] = store.claim_id_for("temporal", payload)
        _import_claims(store, "temporal", [serialize_claim(c) for c in temporal])
        _import_claims(store, "entity", [serialize_claim(c) for c in entities])

        for entity in demo_entities():
            store.put_entity(entity, allowed_entity_types=ontology.entity_types)
        store.put_event(demo_event(), allowed_event_types=ontology.event_types)
        for relationship in demo_relationships():
            store.put_relationship(relationship, allowed_predicates=ontology.predicates)

        # The contradictory pair: the report and the testimony disagree. Both
        # claims stay; the disagreement is recorded as its own edge.
        from evidence_collections.demo_history.collection import DOCUMENT_ID, TESTIMONY_ID

        store.put_claim_relation(
            demo_claim_relation(temporal_ids[DOCUMENT_ID], temporal_ids[TESTIMONY_ID])
        )
        stats = store.stats()

    return {
        "collection_id": collection.id,
        "records": len(records),
        "priorities": len(priorities),
        "tasks": len(tasks),
        "temporal_claims": len(temporal),
        "entity_claims": len(entities),
        "table_counts": stats,
    }


def _import_claims(store: ArchiveStore, kind: str, payloads: list[dict[str, Any]]) -> None:
    """Write serialized claims through the store's own claim path."""

    import json
    import tempfile

    if not payloads:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8", delete=False) as handle:
        for payload in payloads:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        temp_path = Path(handle.name)
    try:
        store.import_claim_jsonl(temp_path, kind)
    finally:
        temp_path.unlink(missing_ok=True)
