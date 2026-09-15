# Project Plan

## Goal

Build a trustworthy, explorable historical interface for September 11, 2001 that combines public photos, video, audio, oral histories, events, people, units, buildings, and locations into a synchronized map + timeline.

The difficult part is not the map. The difficult part is improving fragmented archival data without obscuring uncertainty or provenance.

## Core principles

1. Preserve the raw source record unchanged.
2. Treat every AI conclusion as a proposal, not a fact.
3. Attach evidence and confidence to derived claims.
4. Keep a full revision history for disputed or improved metadata.
5. Separate discovery, archival metadata, derived metadata, and verified metadata.
6. Prefer linking to media when rights are uncertain rather than mirroring it.
7. Build incrementally; the archive does not need to be complete before it is useful.
8. Make sensitive-content controls first-class in the public experience.

## Product surfaces

### Archive Workbench

Research and review interface used to:

- register sources and collections
- ingest metadata
- detect duplicates and derivative copies
- reconstruct photo/video sequences
- transcribe audio/video
- geolocate media
- estimate timestamps and uncertainty ranges
- resolve people, units, buildings, and organizations
- link records to events
- record provenance and contradictions
- approve or reject machine suggestions
- preserve revision history

### Public Explorer

Read-only public interface centered on:

- Lower Manhattan map
- synchronized timeline scrubber
- photo/video/audio markers
- camera direction and field-of-view when known
- people and responder/unit story threads
- oral-history excerpts
- nearby media at the selected time
- provenance/confidence display
- sensitive-content filters

## Phase 0 — Source inventory

Before large-scale downloading, build a registry of public sources.

Target categories:

- NIST / FEMA / federal FOIA releases
- National September 11 Memorial & Museum public resources
- Library of Congress / September 11 Digital Archive
- Internet Archive collections and mirrors
- public oral-history collections
- mapped photographer projects
- public researcher datasets
- public video platforms and preservation channels
- local news/public institutional archives
- historical web projects recovered via Internet Archive

Deliverable: `sources` registry with access method, rights notes, estimated size, media types, and priority.

## Phase 1 — Metadata-first ingestion

Ingest metadata before bulk media copying.

For every source item preserve:

- original source identifier
- source URL
- original title/description
- creator/uploader attribution
- original timestamps and date fields
- collection name
- media type
- access status
- rights/reuse status
- checksums where available
- ingestion timestamp

No machine-normalized value replaces the raw value.

## Phase 2 — Normalization + deduplication

Normalize records into one common schema.

Create canonical media entities while retaining all known copies.

Matching methods may include:

- exact cryptographic hash
- perceptual image hash
- video fingerprint
- audio fingerprint
- filename and duration similarity
- frame similarity
- sequence adjacency
- source attribution

Output should distinguish:

- original/master candidate
- direct copy
- crop
- edit/excerpt
- recompression
- documentary reuse
- uncertain relationship

## Phase 3 — Time + place reconstruction

### Time

Represent time as an interval plus confidence, not only a timestamp.

Evidence may include:

- embedded metadata
- continuous recording sequence
- known impact/collapse times
- radio/audio synchronization
- clocks visible in frame
- television/radio audio captured in background
- photographer/videographer testimony
- neighboring verified frames
- environmental/event-state comparison

### Location

Store:

- coordinates
- accuracy radius
- camera heading
- heading uncertainty
- elevation/floor when known
- evidence list

AI may propose locations using visible landmarks, façades, street signs, skyline geometry, and neighboring records. Human review is required before `verified` status.

## Phase 4 — Entity + event graph

Resolve and connect:

- people
- FDNY/NYPD/EMS/PAPD units
- buildings
- streets/intersections
- boats
- hospitals
- organizations
- command posts
- named historical events

Example relationships:

- media `depicts` event
- media `captured_at` place
- media `created_by` person
- person `present_at` event
- testimony `describes` event
- radio call `mentions` unit
- unit `located_at` place during time interval

## Phase 5 — Verification system

Every derived claim should have:

- status: proposed / reviewed / verified / disputed / rejected
- confidence score
- evidence references
- model/tool that generated the proposal
- reviewer identity
- review timestamp
- revision history

Contradictions are stored, not erased.

## Phase 6 — Explorer MVP

Start with a deliberately limited, high-quality corpus (roughly 500–1,000 well-documented records).

MVP features:

- map of Lower Manhattan
- morning timeline scrubber
- photo/video/audio markers
- major events
- camera heading where known
- nearby media drawer
- record details + provenance
- confidence legend
- search and layer filters
- sensitive-content toggle
- a handful of curated story threads

## Phase 7 — Research Workbench UI

Build queues such as:

- locate this camera
- estimate this time
- identify this unit
- verify duplicate match
- resolve conflicting attribution
- review AI transcript/entity extraction

The system should rank tasks by expected information gain so researchers solve records that unlock the most downstream data first.

## Phase 8 — Advanced reconstruction

Optional later capabilities:

- moving camera tracks
- responder/unit movement tracks
- 2001 building geometry
- camera frustums / field-of-view
- synchronized multi-camera playback
- lightweight 3D reconstruction
- graph queries across people/events/media

## Agent architecture

Recommended agents:

1. Source Discovery
2. Government / FOIA
3. Internet Archive
4. Museum / Institutional
5. Public Video
6. Photography
7. Oral History / Testimony
8. Normalization
9. Deduplication
10. Sequence Reconstruction
11. Temporal Synchronization
12. Geolocation
13. Entity Resolution
14. Event Linking
15. Provenance
16. Contradiction Detection
17. Verification / QA
18. Archivist / Revision History

See `agents/README.md` for contracts.

## First milestone

Do not begin by scraping everything.

The first milestone is a reproducible inventory + a small end-to-end corpus:

1. register 10–20 high-value public sources
2. ingest 500–1,000 metadata records
3. normalize them
4. identify duplicates
5. attach time/location confidence
6. manually verify a representative sample
7. expose them through a tiny API
8. render them on a prototype map/timeline

That milestone tells us how much AI can automate and where human historical research is still essential.
