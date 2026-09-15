# Agent Contracts

Agents should exchange structured records, not prose-only conclusions.

Every proposal produced by an agent must include:

- `agent_name`
- `agent_version`
- `subject_id`
- `proposal_type`
- `proposal_value`
- `confidence`
- `evidence[]`
- `source_ids[]`
- `created_at`
- `notes`

Agents may propose; they may not silently mark historical claims as verified.

## Discovery agents

### Source Discovery
Find candidate archives, datasets, websites, collections, channels, and mirrors.

Output: source registry entries only.

### Government / FOIA
Specialize in NIST, FEMA, FAA/ATC, government reports, releases, exhibits, and public agency collections.

### Internet Archive
Find digitized tapes, recordings, archived websites, dead-project mirrors, broadcasts, and historical datasets.

### Museum / Institutional
Index museum, library, university, historical-society, and institutional collections.

### Public Video
Catalog public video sources and uploader metadata without assuming uploader titles are correct.

### Photography
Catalog photographer collections, sequences, captions, known map positions, and adjacent frames.

### Oral History / Testimony
Index interviews/transcripts and extract candidate people, locations, organizations, times, and events with citations back to the source passage.

## Enrichment agents

### Normalization
Map raw source metadata into shared fields while preserving raw values.

### Deduplication
Suggest canonical-media groupings using exact hashes, perceptual similarity, fingerprints, duration, sequence context, and attribution.

### Sequence Reconstruction
Group frames/clips belonging to the same continuous source and establish order.

### Temporal Synchronization
Propose timestamps/ranges with explicit uncertainty and evidence.

### Geolocation
Propose coordinates, accuracy radius, camera heading, and heading uncertainty.

### Entity Resolution
Resolve aliases for people, units, buildings, organizations, vehicles, boats, streets, and places.

### Event Linking
Connect records into named historical episodes/events.

## Trust agents

### Provenance
Ensure every important derived field can be traced to source evidence.

### Contradiction Detection
Actively search for conflicting times, locations, identities, attribution, and event interpretations.

### Verification / QA
Route high-value or conflicting proposals to human review and run consistency checks.

### Archivist
Maintain revision history. A corrected claim is superseded, not erased.

## Recommended workflow

`discover -> ingest raw -> normalize -> dedupe -> reconstruct sequence -> propose time/place/entities/events -> provenance check -> contradiction check -> human review -> verified projection`

## Guardrails

- Do not scrape around authentication, paywalls, robots restrictions, or technical access controls.
- Public visibility does not imply permission to redistribute media.
- Store rights/access information separately from historical metadata.
- Do not use face recognition as sole evidence of identity.
- Do not manufacture precision: keep ranges and uncertainty when the evidence is approximate.
- Sensitive imagery should be flagged during ingestion and hidden by default in public-facing experiences.
