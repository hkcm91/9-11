from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_PROPOSAL_TYPES = {
    # Original Phase-0 vocabulary.
    "temporal_claim",
    "spatial_claim",
    "entity_claim",
    "metadata_enrichment",
    "duplicate_link",
    # Evidence-graph vocabulary. Additive: nothing was removed or relaxed.
    "event_link",
    "relationship_link",
    "entity_resolution",
    "claim_relation",
    "source_classification",
}

#: Proposal types whose consequences are severe enough that evidence
#: requirements must never be loosened for them.
CONSEQUENTIAL_PROPOSAL_TYPES = frozenset(
    {
        "temporal_claim",
        "spatial_claim",
        "entity_claim",
        "event_link",
        "relationship_link",
        "entity_resolution",
        "claim_relation",
    }
)


class ProposalValidationError(ValueError):
    pass


@dataclass(slots=True)
class ProposalEnvelope:
    proposal_id: str
    agent_name: str
    agent_version: str
    subject_id: str
    proposal_type: str
    proposal_value: dict[str, Any]
    confidence: float
    evidence: list[dict[str, Any]]
    task_id: str | None = None
    source_ids: list[str] = field(default_factory=list)
    notes: str | None = None
    review_status: str = "proposed"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["created_at"] = self.created_at.isoformat()
        return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProposalValidationError(f"{key} is required")
    return value.strip()


def _validate_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ProposalValidationError("at least one evidence reference is required")
    evidence: list[dict[str, Any]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise ProposalValidationError(f"evidence[{index}] must be an object")
        source_item_id = entry.get("source_item_id")
        if not isinstance(source_item_id, str) or not source_item_id.strip():
            raise ProposalValidationError(f"evidence[{index}].source_item_id is required")
        relationship = entry.get("relationship", "supports")
        if not isinstance(relationship, str) or not relationship.strip():
            raise ProposalValidationError(f"evidence[{index}].relationship must be text")
        normalized = dict(entry)
        normalized["source_item_id"] = source_item_id.strip()
        normalized["relationship"] = relationship.strip()
        weight = normalized.get("weight")
        if weight is not None:
            try:
                weight = float(weight)
            except (TypeError, ValueError) as exc:
                raise ProposalValidationError(f"evidence[{index}].weight must be numeric") from exc
            if not 0.0 <= weight <= 1.0:
                raise ProposalValidationError(f"evidence[{index}].weight must be between 0 and 1")
            normalized["weight"] = weight
        evidence.append(normalized)
    return evidence


def validate_proposal(payload: dict[str, Any]) -> ProposalEnvelope:
    """Validate an agent output before it can enter the research database.

    Agents cannot mark their own conclusions reviewed or verified. Every claim
    proposal must cite at least one evidence record and carry explicit
    confidence. Human/reviewer actions are stored separately.
    """

    if not isinstance(payload, dict):
        raise ProposalValidationError("proposal must be an object")

    agent_name = _required_text(payload, "agent_name")
    agent_version = _required_text(payload, "agent_version")
    subject_id = _required_text(payload, "subject_id")
    proposal_type = _required_text(payload, "proposal_type")
    if proposal_type not in ALLOWED_PROPOSAL_TYPES:
        raise ProposalValidationError(f"unsupported proposal_type: {proposal_type}")

    proposal_value = payload.get("proposal_value")
    if not isinstance(proposal_value, dict) or not proposal_value:
        raise ProposalValidationError("proposal_value must be a non-empty object")

    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise ProposalValidationError("confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ProposalValidationError("confidence must be between 0 and 1")

    review_status = str(payload.get("review_status") or "proposed").strip().lower()
    if review_status != "proposed":
        raise ProposalValidationError("agents may only submit proposals with review_status='proposed'")

    evidence = _validate_evidence(payload.get("evidence"))
    source_ids_value = payload.get("source_ids") or []
    if not isinstance(source_ids_value, list):
        raise ProposalValidationError("source_ids must be a list")
    source_ids = [str(value).strip() for value in source_ids_value if str(value).strip()]

    task_id = payload.get("task_id")
    if task_id is not None and (not isinstance(task_id, str) or not task_id.strip()):
        raise ProposalValidationError("task_id must be non-empty text when provided")
    task_id = task_id.strip() if isinstance(task_id, str) else None

    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ProposalValidationError("notes must be text when provided")

    created_at_value = payload.get("created_at")
    if isinstance(created_at_value, str) and created_at_value.strip():
        try:
            created_at = datetime.fromisoformat(created_at_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProposalValidationError("created_at must be ISO-8601") from exc
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    identity = {
        "agent_name": agent_name,
        "agent_version": agent_version,
        "task_id": task_id,
        "subject_id": subject_id,
        "proposal_type": proposal_type,
        "proposal_value": proposal_value,
        "confidence": confidence,
        "evidence": evidence,
        "source_ids": source_ids,
    }
    generated_id = "proposal:" + hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()[:24]
    supplied_id = payload.get("proposal_id")
    proposal_id = supplied_id.strip() if isinstance(supplied_id, str) and supplied_id.strip() else generated_id

    return ProposalEnvelope(
        proposal_id=proposal_id,
        agent_name=agent_name,
        agent_version=agent_version,
        subject_id=subject_id,
        proposal_type=proposal_type,
        proposal_value=dict(proposal_value),
        confidence=confidence,
        evidence=evidence,
        task_id=task_id,
        source_ids=source_ids,
        notes=notes.strip() if isinstance(notes, str) and notes.strip() else None,
        review_status="proposed",
        created_at=created_at,
    )


def load_proposal_jsonl(path: Path) -> list[ProposalEnvelope]:
    proposals: list[ProposalEnvelope] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProposalValidationError(f"invalid JSONL at {path}:{line_number}") from exc
            try:
                proposals.append(validate_proposal(payload))
            except ProposalValidationError as exc:
                raise ProposalValidationError(f"{path}:{line_number}: {exc}") from exc
    return proposals
