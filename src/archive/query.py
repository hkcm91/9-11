from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class NearbyResult:
    subject_id: str
    latitude: float
    longitude: float
    distance_m: float
    location_kind: str
    confidence: float
    heading_deg: float | None
    record: dict[str, Any]


class ArchiveQuery:
    """Read-only query facade for Explorer/Workbench surfaces.

    This deliberately queries claims rather than treating normalized source
    metadata as historical truth. The same record can therefore carry multiple
    proposed/reviewed claims without losing provenance or uncertainty.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ArchiveQuery":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _decode_record(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        raw = value.pop("metadata_json", None)
        if raw:
            value["metadata_raw"] = json.loads(raw)
        return value

    @staticmethod
    def _claim_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        for row in rows:
            value = dict(row)
            raw = value.pop("claim_json", None)
            value.pop("evidence_json", None)
            if raw:
                original = json.loads(raw)
                # Retain typed/indexed columns while restoring evidence and any
                # fields that are intentionally not promoted into SQL columns.
                original.update({k: v for k, v in value.items() if v is not None})
                value = original
            claims.append(value)
        return claims

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM source_records WHERE id = ?", (record_id,)
        ).fetchone()
        return self._decode_record(row)

    def item_bundle(self, record_id: str) -> dict[str, Any] | None:
        record = self.get_record(record_id)
        if record is None:
            return None
        temporal = self._claim_rows(
            self.connection.execute(
                "SELECT * FROM temporal_claims WHERE subject_id = ? ORDER BY confidence DESC",
                (record_id,),
            ).fetchall()
        )
        spatial = self._claim_rows(
            self.connection.execute(
                "SELECT * FROM spatial_claims WHERE subject_id = ? ORDER BY confidence DESC",
                (record_id,),
            ).fetchall()
        )
        entities = self._claim_rows(
            self.connection.execute(
                "SELECT * FROM entity_claims WHERE subject_id = ? ORDER BY confidence DESC",
                (record_id,),
            ).fetchall()
        )
        observations = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT observation_id, ingested_at, raw_digest
                FROM source_observations
                WHERE record_id = ?
                ORDER BY ingested_at
                """,
                (record_id,),
            ).fetchall()
        ]
        return {
            "record": record,
            "temporal_claims": temporal,
            "spatial_claims": spatial,
            "entity_claims": entities,
            "observations": observations,
        }

    def timeline(
        self,
        start: datetime,
        end: datetime,
        *,
        kinds: set[str] | None = None,
        min_confidence: float = 0.0,
        statuses: set[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return claims intersecting an absolute time window.

        Open-ended claims are handled explicitly: a missing start means
        "sometime before end_time" and a missing end means "sometime after
        start_time". Callers can filter semantic kinds such as capture_time or
        recording_time so document coverage never masquerades as camera time.
        """

        if end < start:
            raise ValueError("end must be on or after start")
        if limit < 1:
            return []

        clauses = [
            "confidence >= ?",
            "(start_time IS NULL OR start_time <= ?)",
            "(end_time IS NULL OR end_time >= ?)",
        ]
        params: list[Any] = [min_confidence, end.isoformat(), start.isoformat()]
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            clauses.append(f"time_kind IN ({placeholders})")
            params.extend(sorted(kinds))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(sorted(statuses))

        params.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT t.*, r.title_raw, r.creator_raw, r.source_url,
                   r.media_type_raw, r.collection_raw
            FROM temporal_claims AS t
            LEFT JOIN source_records AS r ON r.id = t.subject_id
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(t.start_time, t.end_time), t.confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return self._claim_rows(rows)

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6_371_008.8
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def nearby(
        self,
        latitude: float,
        longitude: float,
        radius_m: float,
        *,
        kinds: set[str] | None = None,
        min_confidence: float = 0.0,
        statuses: set[str] | None = None,
        limit: int = 200,
    ) -> list[NearbyResult]:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("invalid latitude/longitude")
        if radius_m <= 0 or limit < 1:
            return []

        # Cheap bounding box keeps the SQLite query small; exact distance is
        # calculated with haversine below. This avoids a spatial extension for
        # Phase 0 while remaining adequate for Lower Manhattan-scale queries.
        lat_delta = radius_m / 111_320.0
        cos_lat = max(0.01, math.cos(math.radians(latitude)))
        lon_delta = radius_m / (111_320.0 * cos_lat)
        clauses = [
            "s.confidence >= ?",
            "s.latitude BETWEEN ? AND ?",
            "s.longitude BETWEEN ? AND ?",
        ]
        params: list[Any] = [
            min_confidence,
            latitude - lat_delta,
            latitude + lat_delta,
            longitude - lon_delta,
            longitude + lon_delta,
        ]
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            clauses.append(f"s.location_kind IN ({placeholders})")
            params.extend(sorted(kinds))
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"s.status IN ({placeholders})")
            params.extend(sorted(statuses))

        rows = self.connection.execute(
            f"""
            SELECT s.*, r.title_raw, r.creator_raw, r.source_url,
                   r.media_type_raw, r.collection_raw, r.metadata_json
            FROM spatial_claims AS s
            LEFT JOIN source_records AS r ON r.id = s.subject_id
            WHERE {' AND '.join(clauses)}
            """,
            params,
        ).fetchall()

        results: list[NearbyResult] = []
        for row in rows:
            distance = self._haversine_m(latitude, longitude, row["latitude"], row["longitude"])
            if distance > radius_m:
                continue
            record = {
                "id": row["subject_id"],
                "title_raw": row["title_raw"],
                "creator_raw": row["creator_raw"],
                "source_url": row["source_url"],
                "media_type_raw": row["media_type_raw"],
                "collection_raw": row["collection_raw"],
                "metadata_raw": json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            }
            results.append(
                NearbyResult(
                    subject_id=row["subject_id"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    distance_m=round(distance, 2),
                    location_kind=row["location_kind"],
                    confidence=float(row["confidence"]),
                    heading_deg=row["heading_deg"],
                    record=record,
                )
            )
        results.sort(key=lambda result: (result.distance_m, -result.confidence))
        return results[:limit]
