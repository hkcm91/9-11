from __future__ import annotations

from collections import Counter
from typing import Iterable

from historical_engine.collection import Collection
from historical_engine.models.graph import Entity, Event, Relationship
from historical_engine.records import SourceRecord


def materialize_graph(records: Iterable[SourceRecord], collection: Collection, store) -> dict[str, int]:
    """Run a collection's deterministic graph hook and persist typed graph objects.

    Raw source records are written first and remain separate from all derived graph
    objects. Machine-derived graph rows remain proposed and provenance-backed.
    """

    if collection.hooks.derive_graph is None:
        raise ValueError(f"collection '{collection.id}' does not define a graph derivation hook")

    counts: Counter[str] = Counter()
    store.put_collection(collection.record())

    for record in records:
        store.put_source_item(record)
        for obj in collection.hooks.derive_graph(record):
            if isinstance(obj, Entity):
                store.put_entity(
                    obj,
                    actor_kind="machine",
                    allowed_entity_types=collection.ontology.entity_types,
                )
                counts["entities"] += 1
            elif isinstance(obj, Event):
                store.put_event(
                    obj,
                    actor_kind="machine",
                    allowed_event_types=collection.ontology.event_types,
                )
                counts["events"] += 1
            elif isinstance(obj, Relationship):
                store.put_relationship(
                    obj,
                    actor_kind="machine",
                    allowed_predicates=collection.ontology.predicates,
                    allowed_entity_types=None,
                )
                counts["relationships"] += 1
            else:
                raise TypeError(f"unsupported graph object: {type(obj).__name__}")

    return {
        "records": counts["records"],
        "entities": counts["entities"],
        "events": counts["events"],
        "relationships": counts["relationships"],
    }
