from __future__ import annotations

import json
from typing import Any

from archive.query import ArchiveQuery


class WorkbenchQuery(ArchiveQuery):
    """Reviewer-oriented reads layered on the immutable Explorer query facade."""

    @staticmethod
    def _decode_proposal_row(row) -> dict[str, Any]:
        value = dict(row)
        raw = value.pop("proposal_json", None)
        if raw:
            proposal = json.loads(raw)
            # Current status is authoritative in the indexed column because
            # review events update it after the original proposal was written.
            proposal["review_status"] = value.get("review_status", proposal.get("review_status"))
            proposal["updated_at"] = value.get("updated_at")
            return proposal
        for key in ("proposal_value_json", "evidence_json", "source_ids_json"):
            raw_value = value.get(key)
            if raw_value:
                value[key.removesuffix("_json")] = json.loads(raw_value)
        return value

    def proposal_queue(
        self,
        *,
        statuses: set[str] | None = None,
        proposal_types: set[str] | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"p.review_status IN ({placeholders})")
            params.extend(sorted(statuses))
        if proposal_types:
            placeholders = ",".join("?" for _ in proposal_types)
            clauses.append(f"p.proposal_type IN ({placeholders})")
            params.extend(sorted(proposal_types))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT p.*, r.title_raw, r.creator_raw, r.source_url,
                   r.media_type_raw, r.collection_raw
            FROM agent_proposals AS p
            LEFT JOIN source_records AS r ON r.id = p.subject_id
            {where}
            ORDER BY p.confidence DESC, p.created_at ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [self._decode_proposal_row(row) for row in rows]

    def proposal_bundle(self, proposal_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM agent_proposals WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            return None
        proposal = self._decode_proposal_row(row)
        reviews = [
            dict(review)
            for review in self.connection.execute(
                """
                SELECT review_id, reviewer, previous_status, new_status, note, created_at
                FROM proposal_reviews
                WHERE proposal_id = ?
                ORDER BY created_at, review_id
                """,
                (proposal_id,),
            ).fetchall()
        ]
        record = self.get_record(str(row["subject_id"]))
        return {"proposal": proposal, "reviews": reviews, "record": record}

    def item_review_bundle(self, record_id: str) -> dict[str, Any] | None:
        bundle = self.item_bundle(record_id)
        if bundle is None:
            return None
        rows = self.connection.execute(
            "SELECT * FROM agent_proposals WHERE subject_id = ? ORDER BY created_at, proposal_id",
            (record_id,),
        ).fetchall()
        proposals: list[dict[str, Any]] = []
        for row in rows:
            proposal = self._decode_proposal_row(row)
            reviews = [
                dict(review)
                for review in self.connection.execute(
                    """
                    SELECT review_id, reviewer, previous_status, new_status, note, created_at
                    FROM proposal_reviews
                    WHERE proposal_id = ?
                    ORDER BY created_at, review_id
                    """,
                    (row["proposal_id"],),
                ).fetchall()
            ]
            proposals.append({"proposal": proposal, "reviews": reviews})
        bundle["agent_proposals"] = proposals
        return bundle
