"""Historical Evidence Engine.

A reusable, provenance-first engine for historical archives. It handles source
registration, metadata-first ingestion, raw-source preservation, normalization,
duplicate detection, claims, an evidence graph, agent proposals, review, work
queues and query — without knowing which historical corpus it is serving.

Collection-specific behaviour arrives through configuration, ontologies,
adapters and hooks. See ``docs/ENGINE.md`` and ``docs/ENGINE_REFACTOR.md``.

The core rule the engine enforces everywhere:

    Never replace the source record with an AI guess. Raw observations are
    immutable; derived information is separately represented, carrying
    provenance, evidence, confidence, method, agent identity and review status.
"""

from historical_engine.collection import BaseCollection, Collection, CollectionHooks
from historical_engine.collection_registry import (
    UnknownCollectionError,
    available_collections,
    get_collection,
    iter_collections,
    register_collection,
    set_bootstrap,
)
from historical_engine.ontology import Ontology, SensitivePolicy, load_ontology
from historical_engine.records import SourceRecord
from historical_engine.routing import (
    ConfidenceRouter,
    RoutingDecision,
    RoutingOutcome,
    RoutingPolicy,
)

__all__ = [
    "BaseCollection",
    "Collection",
    "CollectionHooks",
    "ConfidenceRouter",
    "Ontology",
    "RoutingDecision",
    "RoutingOutcome",
    "RoutingPolicy",
    "SensitivePolicy",
    "SourceRecord",
    "UnknownCollectionError",
    "available_collections",
    "get_collection",
    "iter_collections",
    "load_ontology",
    "register_collection",
    "set_bootstrap",
]
