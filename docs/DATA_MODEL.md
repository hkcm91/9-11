# Initial Data Model

This is deliberately implementation-neutral. It can later map to PostgreSQL/PostGIS tables, JSON documents, or a graph layer.

## Source

Represents a repository, collection, website, institution, channel, or dataset.

Fields:

- `id`
- `name`
- `type`
- `homepage_url`
- `access_method`
- `rights_status`
- `rights_notes`
- `priority`
- `estimated_item_count`
- `last_crawled_at`
- `raw_metadata`

## SourceItem

Immutable record of what a source says about one item.

Fields:

- `id`
- `source_id`
- `source_item_id`
- `source_url`
- `title_raw`
- `description_raw`
- `creator_raw`
- `date_raw`
- `location_raw`
- `media_type_raw`
- `rights_raw`
- `metadata_raw`
- `ingested_at`

## Media

Canonical media entity that may have many source copies.

Fields:

- `id`
- `media_type` (`photo`, `video`, `audio`, `document`, `other`)
- `canonical_title`
- `creator_entity_id`
- `duration_ms`
- `master_candidate_source_item_id`
- `sensitive_content_level`
- `review_status`

## MediaCopy

Connects a canonical media item to a source copy or derivative.

Fields:

- `media_id`
- `source_item_id`
- `relationship` (`master_candidate`, `direct_copy`, `crop`, `excerpt`, `recompression`, `edit`, `unknown`)
- `match_method`
- `match_confidence`

## TemporalClaim

A proposed or verified time/time range for any entity.

Fields:

- `id`
- `subject_type`
- `subject_id`
- `start_time`
- `end_time`
- `uncertainty_before_ms`
- `uncertainty_after_ms`
- `confidence`
- `status`
- `method`
- `created_by_agent`
- `reviewed_by`
- `reviewed_at`

## SpatialClaim

A proposed or verified location / camera position.

Fields:

- `id`
- `subject_type`
- `subject_id`
- `latitude`
- `longitude`
- `accuracy_radius_m`
- `heading_deg`
- `heading_uncertainty_deg`
- `elevation_m`
- `floor_label`
- `confidence`
- `status`
- `method`
- `created_by_agent`
- `reviewed_by`
- `reviewed_at`

## Evidence

Supports or contradicts a claim.

Fields:

- `id`
- `claim_type`
- `claim_id`
- `evidence_type`
- `source_item_id`
- `excerpt_or_note`
- `relationship` (`supports`, `contradicts`, `context`)
- `weight`

## Entity

Generic resolved entity.

Types can include:

- `person`
- `organization`
- `responder_unit`
- `building`
- `street`
- `intersection`
- `boat`
- `hospital`
- `vehicle`
- `place`

Fields:

- `id`
- `entity_type`
- `canonical_name`
- `description`
- `review_status`

## EntityAlias

Fields:

- `entity_id`
- `alias`
- `source_item_id`
- `confidence`

## Event

Historical event or episode.

Fields:

- `id`
- `name`
- `description`
- `start_time`
- `end_time`
- `event_type`
- `review_status`

## Relationship

Connects media, entities, events, testimony, and locations.

Fields:

- `id`
- `subject_type`
- `subject_id`
- `predicate`
- `object_type`
- `object_id`
- `start_time`
- `end_time`
- `confidence`
- `status`
- `claim_id`

Examples:

- media `depicts` event
- media `created_by` person
- person `present_at` place
- testimony `describes` event
- unit `located_at` place

## Transcript

Fields:

- `id`
- `media_id`
- `language`
- `text`
- `segments_json`
- `transcription_method`
- `confidence`
- `review_status`

## Revision

Never erase a historical inference change.

Fields:

- `id`
- `record_type`
- `record_id`
- `previous_value_json`
- `new_value_json`
- `reason`
- `actor`
- `created_at`

## Suggested status vocabulary

- `raw`
- `proposed`
- `reviewed`
- `verified`
- `disputed`
- `rejected`

## Confidence

Store confidence numerically (`0.0`–`1.0`) but present plain-language labels in the UI. Suggested initial mapping:

- `0.95–1.00`: exact / exceptionally strong
- `0.80–0.949`: high
- `0.60–0.799`: moderate
- `0.00–0.599`: low / inferred

Confidence does not replace evidence. A claim without inspectable evidence should never become verified solely because a model reports a high score.

---

## Implementation status after the engine refactor

This document describes the target model. What is implemented, and where:

| Concept | Implemented as | Module |
| --- | --- | --- |
| Source, SourceItem | `SourceItem`, `source_records`, `source_observations` | `archive.models`, `archive.store` |
| TemporalClaim, SpatialClaim, EntityReferenceClaim | dataclasses + SQLite tables | `archive.models`, `archive.store` |
| AgentProposal, review history | `ProposalEnvelope`, `agent_proposals`, `proposal_reviews` | `historical_engine.proposals`, `archive.store` |
| Collection | `CollectionRecord` + `collections` table | `historical_engine.models.graph` |
| Entity, EntityAlias | `Entity`, `EntityAlias` + `entities`, `entity_aliases` | `historical_engine.models.graph` |
| Event | `Event` + `events` | `historical_engine.models.graph` |
| Relationship | `Relationship` + `relationships`, with an `assertion_level` | `historical_engine.models.graph` |
| Evidence | `EvidenceItem`, round-trips the embedded `EvidenceRef` shape | `historical_engine.models.graph` |
| Claim-to-claim reasoning | `ClaimRelation` + `claim_relations` | `historical_engine.models.graph` |
| Revision / supersession | `Revision` + `revisions` | `historical_engine.models.graph` |
| Transcript | not yet implemented | — |

The graph tables were added by an **additive** migration (schema 3 → 4):
`CREATE TABLE IF NOT EXISTS` only. No existing table was dropped, renamed or
rewritten, and no existing row was touched.

### Entity types

The engine's generic vocabulary is `person`, `organization`, `place`,
`building`, `unit`, `vehicle`, `vessel`, `aircraft`, `document`, `other`. A
collection ontology extends it — the September 11 ontology adds
`responder_unit`, `broadcast_outlet` and `flight` — rather than the engine
hardcoding responder-specific concepts.

### Assertion levels

A relationship must declare how strongly the record supports it:
`mentioned`, `associated`, `alleged`, `witnessed`, `reported`, `corroborated`,
`contradicted`, `established`. `corroborated` and `established` can only be set
by a human actor. See `docs/ENGINE.md`.
