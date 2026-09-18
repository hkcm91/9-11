"""Synthetic demonstration collection — architectural validation only."""

from evidence_collections.demo_history.collection import (
    COLLECTION_ID,
    ONTOLOGY_PATH,
    RECORDS_PATH,
    SOURCES_PATH,
    DemoHistoryCollection,
    build_collection,
    demo_claim_relation,
    demo_entities,
    demo_event,
    demo_relationships,
)

__all__ = [
    "COLLECTION_ID",
    "DemoHistoryCollection",
    "ONTOLOGY_PATH",
    "RECORDS_PATH",
    "SOURCES_PATH",
    "build_collection",
    "demo_claim_relation",
    "demo_entities",
    "demo_event",
    "demo_relationships",
]
