from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from archive.corpus import load_jsonl
from archive.models import SourceItem
from archive.proposals import ProposalEnvelope, load_proposal_jsonl
from historical_engine.models.graph import (
    ClaimRelation,
    CollectionRecord,
    Entity,
    EntityAlias,
    Event,
    Relationship,
    Revision,
)
from historical_engine.storage import graph_store
from historical_engine.storage.ids import canonical_json, claim_id as _canonical_claim_id

# 4 adds the evidence-graph tables. The migration is purely additive:
# `CREATE TABLE IF NOT EXISTS` only, no existing table or row is altered, so a
# database written by schema 3 is read and extended without conversion.
SCHEMA_VERSION = 4
_ALLOWED_REVIEW_STATUSES = {"reviewed", "verified", "rejected", "disputed"}


class ArchiveStore:
    """Small provenance-first SQLite store for Phase 0/1 research outputs.

    Raw source payloads, normalization outputs, machine proposals, and reviewer
    actions are all preserved separately. `source_records` is only a convenient
    read model; it never erases the observations from which it was derived.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.initialize()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ArchiveStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_records (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_item_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                title_raw TEXT,
                description_raw TEXT,
                creator_raw TEXT,
                date_raw TEXT,
                archive_added_raw TEXT,
                location_raw TEXT,
                rights_raw TEXT,
                collection_raw TEXT,
                media_type_raw TEXT,
                metadata_json TEXT NOT NULL,
                richness INTEGER NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                UNIQUE(source_id, source_item_id)
            );

            CREATE TABLE IF NOT EXISTS source_observations (
                observation_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL REFERENCES source_records(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL,
                source_item_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                raw_digest TEXT NOT NULL,
                normalized_digest TEXT NOT NULL,
                normalized_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                UNIQUE(record_id, raw_digest, normalized_digest)
            );

            CREATE TABLE IF NOT EXISTS temporal_claims (
                claim_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                time_kind TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                uncertainty_before_ms INTEGER,
                uncertainty_after_ms INTEGER,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                method TEXT,
                created_by_agent TEXT,
                evidence_json TEXT NOT NULL,
                claim_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS spatial_claims (
                claim_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                location_kind TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                accuracy_radius_m REAL,
                heading_deg REAL,
                heading_uncertainty_deg REAL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                method TEXT,
                created_by_agent TEXT,
                evidence_json TEXT NOT NULL,
                claim_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entity_claims (
                claim_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                entity_kind TEXT NOT NULL,
                relation TEXT NOT NULL,
                name_raw TEXT NOT NULL,
                normalized_name TEXT,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                method TEXT,
                created_by_agent TEXT,
                evidence_json TEXT NOT NULL,
                claim_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_proposals (
                proposal_id TEXT PRIMARY KEY,
                task_id TEXT,
                agent_name TEXT NOT NULL,
                agent_version TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                proposal_type TEXT NOT NULL,
                proposal_value_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                source_ids_json TEXT NOT NULL,
                notes TEXT,
                review_status TEXT NOT NULL DEFAULT 'proposed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                proposal_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proposal_reviews (
                review_id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL REFERENCES agent_proposals(proposal_id) ON DELETE CASCADE,
                reviewer TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_source_records_source ON source_records(source_id);
            CREATE INDEX IF NOT EXISTS idx_source_records_date ON source_records(date_raw);
            CREATE INDEX IF NOT EXISTS idx_source_records_creator ON source_records(creator_raw);
            CREATE INDEX IF NOT EXISTS idx_observations_record ON source_observations(record_id);
            CREATE INDEX IF NOT EXISTS idx_temporal_subject ON temporal_claims(subject_id);
            CREATE INDEX IF NOT EXISTS idx_temporal_time ON temporal_claims(start_time, end_time);
            CREATE INDEX IF NOT EXISTS idx_spatial_subject ON spatial_claims(subject_id);
            CREATE INDEX IF NOT EXISTS idx_spatial_latlon ON spatial_claims(latitude, longitude);
            CREATE INDEX IF NOT EXISTS idx_entity_subject ON entity_claims(subject_id);
            CREATE INDEX IF NOT EXISTS idx_entity_name ON entity_claims(normalized_name);
            CREATE INDEX IF NOT EXISTS idx_proposals_subject ON agent_proposals(subject_id);
            CREATE INDEX IF NOT EXISTS idx_proposals_task ON agent_proposals(task_id);
            CREATE INDEX IF NOT EXISTS idx_proposals_status ON agent_proposals(review_status);
            CREATE INDEX IF NOT EXISTS idx_reviews_proposal ON proposal_reviews(proposal_id);
            """
        )
        graph_store.apply_graph_schema(self.connection)
        self.connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.connection.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_json(value)

    @classmethod
    def _richness(cls, item: SourceItem) -> int:
        fields = (
            item.title_raw,
            item.description_raw,
            item.creator_raw,
            item.date_raw,
            item.archive_added_raw,
            item.location_raw,
            item.rights_raw,
            item.collection_raw,
            item.media_type_raw,
        )
        populated = sum(value not in (None, "") for value in fields)
        return populated * 10_000 + len(cls._json(item.metadata_raw))

    @classmethod
    def _normalized_payload(cls, item: SourceItem) -> dict[str, Any]:
        payload = asdict(item)
        payload["ingested_at"] = item.ingested_at.isoformat()
        return payload

    def put_source_item(self, item: SourceItem) -> None:
        now = item.ingested_at
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        seen_at = now.isoformat()
        metadata_json = self._json(item.metadata_raw)
        normalized = self._normalized_payload(item)
        normalized_json = self._json(normalized)
        raw_digest = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()
        normalized_digest = hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()
        observation_id = hashlib.sha256(
            f"{item.id}|{raw_digest}|{normalized_digest}".encode("utf-8")
        ).hexdigest()
        richness = self._richness(item)

        existing = self.connection.execute(
            "SELECT richness, first_seen FROM source_records WHERE id = ?", (item.id,)
        ).fetchone()
        if existing is None:
            first_seen = seen_at
            replace_read_model = True
        else:
            first_seen = existing["first_seen"]
            replace_read_model = richness >= int(existing["richness"])

        if existing is None or replace_read_model:
            self.connection.execute(
                """
                INSERT INTO source_records(
                    id, source_id, source_item_id, source_url, title_raw,
                    description_raw, creator_raw, date_raw, archive_added_raw,
                    location_raw, rights_raw, collection_raw, media_type_raw,
                    metadata_json, richness, first_seen, last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    source_url=excluded.source_url,
                    title_raw=excluded.title_raw,
                    description_raw=excluded.description_raw,
                    creator_raw=excluded.creator_raw,
                    date_raw=excluded.date_raw,
                    archive_added_raw=excluded.archive_added_raw,
                    location_raw=excluded.location_raw,
                    rights_raw=excluded.rights_raw,
                    collection_raw=excluded.collection_raw,
                    media_type_raw=excluded.media_type_raw,
                    metadata_json=excluded.metadata_json,
                    richness=excluded.richness,
                    last_seen=excluded.last_seen
                """,
                (
                    item.id, item.source_id, item.source_item_id, item.source_url,
                    item.title_raw, item.description_raw, item.creator_raw,
                    item.date_raw, item.archive_added_raw, item.location_raw,
                    item.rights_raw, item.collection_raw, item.media_type_raw,
                    metadata_json, richness, first_seen, seen_at,
                ),
            )
        else:
            self.connection.execute(
                "UPDATE source_records SET last_seen = ? WHERE id = ?", (seen_at, item.id)
            )

        self.connection.execute(
            """
            INSERT OR IGNORE INTO source_observations(
                observation_id, record_id, source_id, source_item_id,
                ingested_at, raw_digest, normalized_digest, normalized_json, metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                observation_id, item.id, item.source_id, item.source_item_id,
                seen_at, raw_digest, normalized_digest, normalized_json, metadata_json,
            ),
        )

    def put_source_items(self, items: Iterable[SourceItem]) -> int:
        count = 0
        with self.connection:
            for item in items:
                self.put_source_item(item)
                count += 1
        return count

    def import_source_jsonl(self, paths: Iterable[Path]) -> int:
        count = 0
        with self.connection:
            for path in paths:
                for item in load_jsonl(path):
                    self.put_source_item(item)
                    count += 1
        return count

    @classmethod
    def _claim_id(cls, kind: str, payload: dict[str, Any]) -> str:
        return _canonical_claim_id(kind, payload)

    def import_claim_jsonl(self, path: Path, kind: str) -> int:
        if kind not in {"temporal", "spatial", "entity"}:
            raise ValueError("kind must be temporal, spatial, or entity")
        count = 0
        with path.open("r", encoding="utf-8") as handle, self.connection:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid claim JSONL at {path}:{line_number}") from exc
                if not isinstance(payload, dict):
                    raise ValueError(f"expected claim object at {path}:{line_number}")
                claim_id = self._claim_id(kind, payload)
                evidence_json = self._json(payload.get("evidence") or [])
                claim_json = self._json(payload)

                if kind == "temporal":
                    self.connection.execute(
                        """
                        INSERT OR REPLACE INTO temporal_claims(
                            claim_id, subject_id, time_kind, start_time, end_time,
                            uncertainty_before_ms, uncertainty_after_ms, confidence,
                            status, method, created_by_agent, evidence_json, claim_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            claim_id, payload["subject_id"], payload["time_kind"],
                            payload.get("start_time"), payload.get("end_time"),
                            payload.get("uncertainty_before_ms"), payload.get("uncertainty_after_ms"),
                            float(payload.get("confidence") or 0.0), payload.get("status") or "proposed",
                            payload.get("method"), payload.get("created_by_agent"), evidence_json, claim_json,
                        ),
                    )
                elif kind == "spatial":
                    self.connection.execute(
                        """
                        INSERT OR REPLACE INTO spatial_claims(
                            claim_id, subject_id, location_kind, latitude, longitude,
                            accuracy_radius_m, heading_deg, heading_uncertainty_deg,
                            confidence, status, method, created_by_agent, evidence_json, claim_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            claim_id, payload["subject_id"], payload["location_kind"],
                            float(payload["latitude"]), float(payload["longitude"]),
                            payload.get("accuracy_radius_m"), payload.get("heading_deg"),
                            payload.get("heading_uncertainty_deg"), float(payload.get("confidence") or 0.0),
                            payload.get("status") or "proposed", payload.get("method"),
                            payload.get("created_by_agent"), evidence_json, claim_json,
                        ),
                    )
                else:
                    self.connection.execute(
                        """
                        INSERT OR REPLACE INTO entity_claims(
                            claim_id, subject_id, entity_kind, relation, name_raw,
                            normalized_name, confidence, status, method,
                            created_by_agent, evidence_json, claim_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            claim_id, payload["subject_id"], payload["entity_kind"], payload["role"],
                            payload["name_raw"], payload.get("normalized_name"),
                            float(payload.get("confidence") or 0.0), payload.get("status") or "proposed",
                            payload.get("method"), payload.get("created_by_agent"), evidence_json, claim_json,
                        ),
                    )
                count += 1
        return count

    def put_proposal(self, proposal: ProposalEnvelope) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = proposal.to_dict()
        self.connection.execute(
            """
            INSERT INTO agent_proposals(
                proposal_id, task_id, agent_name, agent_version, subject_id,
                proposal_type, proposal_value_json, confidence, evidence_json,
                source_ids_json, notes, review_status, created_at, updated_at,
                proposal_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(proposal_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                proposal_json=excluded.proposal_json
            """,
            (
                proposal.proposal_id, proposal.task_id, proposal.agent_name,
                proposal.agent_version, proposal.subject_id, proposal.proposal_type,
                self._json(proposal.proposal_value), proposal.confidence,
                self._json(proposal.evidence), self._json(proposal.source_ids),
                proposal.notes, proposal.review_status, proposal.created_at.isoformat(),
                now, self._json(payload),
            ),
        )

    def import_proposal_jsonl(self, path: Path) -> int:
        proposals = load_proposal_jsonl(path)
        with self.connection:
            for proposal in proposals:
                self.put_proposal(proposal)
        return len(proposals)

    def review_proposal(
        self,
        proposal_id: str,
        *,
        reviewer: str,
        new_status: str,
        note: str | None = None,
    ) -> str:
        reviewer = reviewer.strip()
        new_status = new_status.strip().lower()
        if not reviewer:
            raise ValueError("reviewer is required")
        if new_status not in _ALLOWED_REVIEW_STATUSES:
            raise ValueError(f"unsupported review status: {new_status}")

        row = self.connection.execute(
            "SELECT review_status FROM agent_proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        previous = str(row["review_status"])
        if new_status == "verified" and previous != "reviewed":
            raise ValueError("a proposal must be reviewed before it can be verified")
        if previous in {"rejected", "verified"}:
            raise ValueError(f"proposal is already terminal: {previous}")

        created_at = datetime.now(timezone.utc).isoformat()
        review_material = self._json(
            {
                "proposal_id": proposal_id,
                "reviewer": reviewer,
                "previous_status": previous,
                "new_status": new_status,
                "note": note,
                "created_at": created_at,
            }
        )
        review_id = "review:" + hashlib.sha256(review_material.encode("utf-8")).hexdigest()[:24]
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO proposal_reviews(
                    review_id, proposal_id, reviewer, previous_status,
                    new_status, note, created_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (review_id, proposal_id, reviewer, previous, new_status, note, created_at),
            )
            self.connection.execute(
                "UPDATE agent_proposals SET review_status = ?, updated_at = ? WHERE proposal_id = ?",
                (new_status, created_at, proposal_id),
            )
        return review_id

    # -- evidence graph ------------------------------------------------------
    #
    # Additive. These never touch `source_records` or `source_observations`;
    # a derived entity, event, relationship or claim-to-claim edge is stored
    # alongside the raw observation, never in place of it. Every writer
    # validates first, so a machine actor cannot insert a verified row.

    def put_collection(self, record: CollectionRecord) -> str:
        with self.connection:
            return graph_store.put_collection(self.connection, record)

    def put_entity(self, entity: Entity, *, actor_kind: str = "machine",
                   allowed_entity_types: Iterable[str] | None = None) -> str:
        with self.connection:
            return graph_store.put_entity(
                self.connection, entity, actor_kind=actor_kind,
                allowed_entity_types=allowed_entity_types,
            )

    def put_entity_alias(self, alias: EntityAlias) -> str:
        with self.connection:
            return graph_store.put_entity_alias(self.connection, alias)

    def put_event(self, event: Event, *, actor_kind: str = "machine",
                  allowed_event_types: Iterable[str] | None = None) -> str:
        with self.connection:
            return graph_store.put_event(
                self.connection, event, actor_kind=actor_kind,
                allowed_event_types=allowed_event_types,
            )

    def put_relationship(self, relationship: Relationship, *, actor_kind: str = "machine",
                         allowed_predicates: Iterable[str] | None = None,
                         allowed_entity_types: Iterable[str] | None = None) -> str:
        with self.connection:
            return graph_store.put_relationship(
                self.connection, relationship, actor_kind=actor_kind,
                allowed_predicates=allowed_predicates,
                allowed_entity_types=allowed_entity_types,
            )

    def put_claim_relation(self, relation: ClaimRelation, *, actor_kind: str = "machine") -> str:
        with self.connection:
            return graph_store.put_claim_relation(
                self.connection, relation, actor_kind=actor_kind
            )

    def put_revision(self, revision: Revision) -> str:
        with self.connection:
            return graph_store.put_revision(self.connection, revision)

    def claim_id_for(self, kind: str, payload: dict[str, Any]) -> str:
        """The id `import_claim_jsonl` would assign to this claim payload."""

        return self._claim_id(kind, payload)

    def stats(self) -> dict[str, int]:
        tables = (
            "source_records", "source_observations", "temporal_claims",
            "spatial_claims", "entity_claims", "agent_proposals",
            "proposal_reviews", *graph_store.GRAPH_TABLES,
        )
        return {
            table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
