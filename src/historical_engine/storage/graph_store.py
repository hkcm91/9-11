"""Additive evidence-graph schema.

Everything here is ``CREATE TABLE IF NOT EXISTS``. No existing table is
dropped, renamed or rewritten, and no existing row is touched: an older
database opened by newer code simply gains empty tables. That is the whole
migration strategy, and it is deliberate — a destructive migration of an
evidence archive is not a thing worth being clever about.

Writes go through validation first, so a machine actor cannot insert a verified
entity, an ``established`` relationship, or an unevidenced edge.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

from historical_engine.models.graph import (
    ClaimRelation,
    CollectionRecord,
    Entity,
    EntityAlias,
    Event,
    EvidenceItem,
    Relationship,
    Revision,
)
from historical_engine.models.validation import (
    validate_claim_relation,
    validate_entity,
    validate_event,
    validate_relationship,
)
from historical_engine.storage.ids import canonical_json, digest_id

GRAPH_SCHEMA_VERSION = 1

GRAPH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS collections (
    collection_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    ontology_version TEXT NOT NULL,
    config_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    provenance_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_kind TEXT NOT NULL,
    language TEXT,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    provenance_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    UNIQUE(entity_id, alias, alias_kind)
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT,
    start_time TEXT,
    end_time TEXT,
    time_precision TEXT,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    provenance_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    assertion_level TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    attributes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_relations (
    claim_relation_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    subject_claim_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    object_claim_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    provenance_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    UNIQUE(subject_claim_id, relation, object_claim_id)
);

CREATE TABLE IF NOT EXISTS revisions (
    revision_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    supersedes_revision_id TEXT,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_collection ON entities(collection_id);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_aliases_entity ON entity_aliases(entity_id);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON entity_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_events_collection ON events(collection_id);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_relationships_subject ON relationships(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_relationships_object ON relationships(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_relationships_predicate ON relationships(predicate);
CREATE INDEX IF NOT EXISTS idx_claim_relations_subject ON claim_relations(subject_claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_relations_object ON claim_relations(object_claim_id);
CREATE INDEX IF NOT EXISTS idx_revisions_target ON revisions(target_kind, target_id);
"""

GRAPH_TABLES: tuple[str, ...] = (
    "collections",
    "entities",
    "entity_aliases",
    "events",
    "relationships",
    "claim_relations",
    "revisions",
)


def apply_graph_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(GRAPH_SCHEMA_SQL)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _evidence_json(evidence: Iterable[EvidenceItem]) -> str:
    return canonical_json([item.to_ref() for item in evidence])


def _provenance_json(provenance: Any) -> str:
    if provenance is None:
        return canonical_json(None)
    payload = asdict(provenance)
    payload["created_at"] = _iso(provenance.created_at)
    return canonical_json(payload)


def put_collection(connection: sqlite3.Connection, record: CollectionRecord) -> str:
    connection.execute(
        """
        INSERT INTO collections(
            collection_id, name, description, ontology_version,
            config_version, created_at, metadata_json
        ) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(collection_id) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            ontology_version=excluded.ontology_version,
            config_version=excluded.config_version,
            metadata_json=excluded.metadata_json
        """,
        (
            record.id,
            record.name,
            record.description,
            record.ontology_version,
            record.config_version,
            _iso(record.created_at),
            canonical_json(record.metadata),
        ),
    )
    return record.id


def put_entity(
    connection: sqlite3.Connection,
    entity: Entity,
    *,
    actor_kind: str = "machine",
    allowed_entity_types: Iterable[str] | None = None,
) -> str:
    validate_entity(entity, actor_kind=actor_kind, allowed_entity_types=allowed_entity_types)
    connection.execute(
        """
        INSERT INTO entities(
            entity_id, collection_id, entity_type, canonical_name, description,
            status, confidence, provenance_json, evidence_json, attributes_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_id) DO UPDATE SET
            canonical_name=excluded.canonical_name,
            description=excluded.description,
            status=excluded.status,
            confidence=excluded.confidence,
            provenance_json=excluded.provenance_json,
            evidence_json=excluded.evidence_json,
            attributes_json=excluded.attributes_json
        """,
        (
            entity.id,
            entity.collection_id,
            entity.entity_type,
            entity.canonical_name,
            entity.description,
            str(entity.status),
            entity.confidence,
            _provenance_json(entity.provenance),
            _evidence_json(entity.evidence),
            canonical_json(entity.attributes),
        ),
    )
    return entity.id


def put_entity_alias(connection: sqlite3.Connection, alias: EntityAlias) -> str:
    alias_id = digest_id("alias", (alias.entity_id, alias.alias, alias.alias_kind))
    connection.execute(
        """
        INSERT INTO entity_aliases(
            alias_id, entity_id, alias, alias_kind, language,
            status, confidence, provenance_json, evidence_json
        ) VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entity_id, alias, alias_kind) DO UPDATE SET
            language=excluded.language,
            status=excluded.status,
            confidence=excluded.confidence,
            provenance_json=excluded.provenance_json,
            evidence_json=excluded.evidence_json
        """,
        (
            alias_id,
            alias.entity_id,
            alias.alias,
            alias.alias_kind,
            alias.language,
            str(alias.status),
            alias.confidence,
            _provenance_json(alias.provenance),
            _evidence_json(alias.evidence),
        ),
    )
    return alias_id


def put_event(
    connection: sqlite3.Connection,
    event: Event,
    *,
    actor_kind: str = "machine",
    allowed_event_types: Iterable[str] | None = None,
) -> str:
    validate_event(event, actor_kind=actor_kind, allowed_event_types=allowed_event_types)
    connection.execute(
        """
        INSERT INTO events(
            event_id, collection_id, name, event_type, description,
            start_time, end_time, time_precision, status, confidence,
            provenance_json, evidence_json, attributes_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(event_id) DO UPDATE SET
            name=excluded.name,
            event_type=excluded.event_type,
            description=excluded.description,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            time_precision=excluded.time_precision,
            status=excluded.status,
            confidence=excluded.confidence,
            provenance_json=excluded.provenance_json,
            evidence_json=excluded.evidence_json,
            attributes_json=excluded.attributes_json
        """,
        (
            event.id,
            event.collection_id,
            event.name,
            event.event_type,
            event.description,
            _iso(event.start_time),
            _iso(event.end_time),
            event.time_precision,
            str(event.status),
            event.confidence,
            _provenance_json(event.provenance),
            _evidence_json(event.evidence),
            canonical_json(event.attributes),
        ),
    )
    return event.id


def put_relationship(
    connection: sqlite3.Connection,
    relationship: Relationship,
    *,
    actor_kind: str = "machine",
    allowed_predicates: Iterable[str] | None = None,
    allowed_entity_types: Iterable[str] | None = None,
) -> str:
    validate_relationship(
        relationship,
        actor_kind=actor_kind,
        allowed_predicates=allowed_predicates,
        allowed_entity_types=allowed_entity_types,
    )
    connection.execute(
        """
        INSERT INTO relationships(
            relationship_id, collection_id, subject_type, subject_id, predicate,
            object_type, object_id, assertion_level, start_time, end_time,
            confidence, status, provenance_json, evidence_json, attributes_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(relationship_id) DO UPDATE SET
            assertion_level=excluded.assertion_level,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            confidence=excluded.confidence,
            status=excluded.status,
            provenance_json=excluded.provenance_json,
            evidence_json=excluded.evidence_json,
            attributes_json=excluded.attributes_json
        """,
        (
            relationship.id,
            relationship.collection_id,
            relationship.subject_type,
            relationship.subject_id,
            relationship.predicate,
            relationship.object_type,
            relationship.object_id,
            str(relationship.assertion_level),
            _iso(relationship.start_time),
            _iso(relationship.end_time),
            relationship.confidence,
            str(relationship.status),
            _provenance_json(relationship.provenance),
            _evidence_json(relationship.evidence),
            canonical_json(relationship.attributes),
        ),
    )
    return relationship.id


def put_claim_relation(
    connection: sqlite3.Connection,
    relation: ClaimRelation,
    *,
    actor_kind: str = "machine",
) -> str:
    validate_claim_relation(relation, actor_kind=actor_kind)
    connection.execute(
        """
        INSERT INTO claim_relations(
            claim_relation_id, collection_id, subject_claim_id, relation,
            object_claim_id, confidence, status, note,
            provenance_json, evidence_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(subject_claim_id, relation, object_claim_id) DO UPDATE SET
            confidence=excluded.confidence,
            status=excluded.status,
            note=excluded.note,
            provenance_json=excluded.provenance_json,
            evidence_json=excluded.evidence_json
        """,
        (
            relation.id,
            relation.collection_id,
            relation.subject_claim_id,
            str(relation.relation),
            relation.object_claim_id,
            relation.confidence,
            str(relation.status),
            relation.note,
            _provenance_json(relation.provenance),
            _evidence_json(relation.evidence),
        ),
    )
    return relation.id


def put_revision(connection: sqlite3.Connection, revision: Revision) -> str:
    connection.execute(
        """
        INSERT INTO revisions(
            revision_id, collection_id, target_kind, target_id,
            supersedes_revision_id, reason, actor, actor_kind,
            payload_json, created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(revision_id) DO NOTHING
        """,
        (
            revision.id,
            revision.collection_id,
            revision.target_kind,
            revision.target_id,
            revision.supersedes_revision_id,
            revision.reason,
            revision.actor,
            revision.actor_kind,
            canonical_json(revision.payload),
            _iso(revision.created_at),
        ),
    )
    return revision.id
