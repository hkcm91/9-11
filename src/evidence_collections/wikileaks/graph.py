from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from archive.models import SourceItem
from historical_engine.models.graph import (
    AssertionLevel,
    Entity,
    Event,
    EvidenceItem,
    Provenance,
    Relationship,
    ReviewState,
)
from historical_engine.storage.ids import digest_id

COLLECTION_ID = "wikileaks"

_PLACEHOLDERS = {
    "",
    "not provided",
    "not provided.",
    "unknown",
    "none selected",
    "n/a",
    "na",
    "none",
}


def _meaningful(value: object) -> str | None:
    text = str(value or "").strip()
    return None if text.casefold() in _PLACEHOLDERS else text


def _evidence(item: SourceItem, note: str | None = None) -> list[EvidenceItem]:
    return [EvidenceItem(source_item_id=item.id, relationship="supports", note=note)]


def _provenance(method: str) -> Provenance:
    return Provenance(method=method, created_by_agent="deterministic:wikileaks-graph", agent_version="1")


def _entity_id(entity_type: str, name: str) -> str:
    return digest_id("entity", (COLLECTION_ID, entity_type, name.strip().casefold()))


def _document_entity(item: SourceItem, *, reference: str | None = None) -> Entity:
    name = reference or item.source_item_id
    return Entity(
        id=_entity_id("document", name),
        collection_id=COLLECTION_ID,
        entity_type="document",
        canonical_name=name,
        description=item.title_raw,
        status=ReviewState.PROPOSED,
        confidence=1.0,
        provenance=_provenance("wikileaks:source-record-document"),
        evidence=_evidence(item),
        attributes={
            "source_record_id": item.id,
            "source_url": item.source_url,
            "source_id": item.source_id,
        },
    )


def _organization(item: SourceItem, name: str, *, kind: str = "organization") -> Entity:
    return Entity(
        id=_entity_id(kind, name),
        collection_id=COLLECTION_ID,
        entity_type=kind,
        canonical_name=name,
        status=ReviewState.PROPOSED,
        confidence=1.0,
        provenance=_provenance("wikileaks:structured-header-entity"),
        evidence=_evidence(item),
    )


def _place(item: SourceItem, name: str, *, place_kind: str) -> Entity:
    return Entity(
        id=_entity_id("place", f"{place_kind}:{name}"),
        collection_id=COLLECTION_ID,
        entity_type="place",
        canonical_name=name,
        status=ReviewState.PROPOSED,
        confidence=1.0,
        provenance=_provenance("wikileaks:structured-location-label"),
        evidence=_evidence(item),
        attributes={"place_kind": place_kind},
    )


def _relationship(
    item: SourceItem,
    *,
    subject_type: str,
    subject_id: str,
    predicate: str,
    object_type: str,
    object_id: str,
    assertion_level: AssertionLevel = AssertionLevel.REPORTED,
    confidence: float = 1.0,
    attributes: dict | None = None,
) -> Relationship:
    return Relationship(
        id=digest_id(
            "relationship",
            (COLLECTION_ID, subject_type, subject_id, predicate, object_type, object_id),
        ),
        collection_id=COLLECTION_ID,
        subject_type=subject_type,
        subject_id=subject_id,
        predicate=predicate,
        object_type=object_type,
        object_id=object_id,
        assertion_level=assertion_level,
        confidence=confidence,
        status=ReviewState.PROPOSED,
        provenance=_provenance("wikileaks:deterministic-structured-relationship"),
        evidence=_evidence(item),
        attributes=attributes or {},
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y%m%dT%H%M%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def derive_plusd_graph(item: SourceItem) -> Iterable[Entity | Relationship]:
    doc = _document_entity(item)
    yield doc

    origin = _meaningful(item.creator_raw)
    if origin:
        origin_kind = "diplomatic_mission" if "embassy" in origin.casefold() else "organization"
        origin_entity = _organization(item, origin, kind=origin_kind)
        yield origin_entity
        yield _relationship(
            item,
            subject_type="document",
            subject_id=doc.id,
            predicate="sent_from",
            object_type=origin_kind,
            object_id=origin_entity.id,
        )

    destinations = item.metadata_raw.get("destinations") or []
    if isinstance(destinations, str):
        destinations = [destinations]
    for destination in destinations:
        name = _meaningful(destination)
        if not name:
            continue
        kind = "diplomatic_mission" if "embassy" in name.casefold() else "organization"
        entity = _organization(item, name, kind=kind)
        yield entity
        yield _relationship(
            item,
            subject_type="document",
            subject_id=doc.id,
            predicate="sent_to",
            object_type=kind,
            object_id=entity.id,
        )

    references = item.metadata_raw.get("references_to") or []
    if isinstance(references, str):
        references = [references]
    for reference in references:
        ref = _meaningful(reference)
        if not ref:
            continue
        target = Entity(
            id=_entity_id("document", ref),
            collection_id=COLLECTION_ID,
            entity_type="document",
            canonical_name=ref,
            status=ReviewState.PROPOSED,
            confidence=1.0,
            provenance=_provenance("wikileaks:cable-reference-target"),
            evidence=_evidence(item, "Referenced by this cable's REF metadata."),
            attributes={"formal_reference": ref},
        )
        yield target
        yield _relationship(
            item,
            subject_type="document",
            subject_id=doc.id,
            predicate="references_document",
            object_type="document",
            object_id=target.id,
            assertion_level=AssertionLevel.MENTIONED,
        )


def derive_war_diary_graph(item: SourceItem) -> Iterable[Entity | Event | Relationship]:
    doc = _document_entity(item)
    yield doc

    event = Event(
        id=digest_id("event", (COLLECTION_ID, item.id)),
        collection_id=COLLECTION_ID,
        name=item.title_raw or item.source_item_id,
        event_type="sigact",
        description=item.description_raw,
        start_time=_parse_datetime(item.date_raw),
        time_precision="source_timestamp" if item.date_raw else None,
        status=ReviewState.PROPOSED,
        confidence=1.0,
        provenance=_provenance("wikileaks:war-diary-event-record"),
        evidence=_evidence(item),
        attributes={
            "source_record_id": item.id,
            "category": item.metadata_raw.get("category"),
            "type": item.metadata_raw.get("type"),
            "classification": item.metadata_raw.get("classification"),
            "casualties": item.metadata_raw.get("casualties"),
        },
    )
    yield event
    yield _relationship(
        item,
        subject_type="document",
        subject_id=doc.id,
        predicate="describes",
        object_type="event",
        object_id=event.id,
    )

    reporting_unit = _meaningful(item.metadata_raw.get("reporting_unit") or item.creator_raw)
    if reporting_unit:
        unit = _organization(item, reporting_unit, kind="military_unit")
        yield unit
        yield _relationship(
            item,
            subject_type="document",
            subject_id=doc.id,
            predicate="reported_by",
            object_type="military_unit",
            object_id=unit.id,
        )

    region = _meaningful(item.metadata_raw.get("region"))
    if region:
        place = _place(item, region, place_kind="region")
        yield place
        yield _relationship(
            item,
            subject_type="event",
            subject_id=event.id,
            predicate="located_in",
            object_type="place",
            object_id=place.id,
        )

    mgrs = _meaningful(item.metadata_raw.get("mgrs"))
    if mgrs:
        grid = _place(item, mgrs, place_kind="mgrs")
        yield grid
        yield _relationship(
            item,
            subject_type="event",
            subject_id=event.id,
            predicate="occurred_at",
            object_type="place",
            object_id=grid.id,
            attributes={"location_precision": "source_mgrs_not_converted"},
        )


def derive_graph(item: SourceItem) -> Iterable[Entity | Event | Relationship]:
    if item.source_id == "wikileaks-plusd":
        yield from derive_plusd_graph(item)
    elif item.source_id == "wikileaks-war-diaries":
        yield from derive_war_diary_graph(item)
