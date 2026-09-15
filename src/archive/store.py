from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import timezone
from pathlib import Path
from typing import Any, Iterable

from archive.corpus import load_jsonl
from archive.models import SourceItem

SCHEMA_VERSION = 2


class ArchiveStore:
    """Small provenance-first SQLite store for Phase 0/1 research outputs.

    Raw source payloads and normalization outputs are both version-significant:
    the same upstream JSON/XML may normalize differently after an adapter fix.
    `source_records` is a convenience read model pointing at the richest
    normalized observation seen for a stable item; observations stay preserved.
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
            """
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.connection.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

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
        material = cls._json({"kind": kind, "payload": payload})
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

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

    def stats(self) -> dict[str, int]:
        tables = (
            "source_records", "source_observations", "temporal_claims",
            "spatial_claims", "entity_claims",
        )
        return {
            table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
