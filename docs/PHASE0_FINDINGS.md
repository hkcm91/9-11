# Phase 0 live findings

This file records observations from public source discovery so adapter work can be tied to concrete collections rather than assumptions.

## September 11 Digital Archive

Observed public browse total: **70,359 items**.

The browse UI exposes machine-readable output formats including JSON, CSV, RDF, Omeka XML, Atom, and RSS. This confirms that metadata-first ingestion is the correct first approach.

Useful collection anchors observed during the first pass:

| Collection | Omeka collection id | Observed item count | Immediate value |
|---|---:|---:|---|
| September 11 Digital Archive Stories | 23 | 7,169 | eyewitness / personal narrative corpus |
| Smithsonian `Bearing Witness to History` visitor stories | 31 | 20,626 | large public-response corpus; useful for separating later memory from event-day evidence |
| FDNY Incident Action Plans | 11 | 39 | authoritative recovery / command documentation |
| Sonic Memorial Project | 266 | 826 | audio, voicemail, soundscape and eyewitness material |
| Voices of 9.11 | 267 | 517 | named video oral histories |
| 15th Anniversary Collection | 296 | 36 | later-contributed memories and artifacts |
| Smithsonian 10th Anniversary visitor responses | 297 | 989 | later-memory collection |

### Implication for ingestion

Do **not** treat all 70k records as equivalent evidence. Collection membership must remain a first-class field so event-day primary media, later oral histories, anniversary recollections, institutional records, and recovery documents can be filtered and weighted differently.

For the first research corpus, prioritize collections that improve reconstruction:

1. event-day photo/video/audio where available;
2. named oral histories with explicit locations/times;
3. FDNY / official operational records;
4. continuous audio/video sources that can become synchronization anchors.

Large retrospective story collections are still valuable, but they should not dominate the first reconstruction sample simply because they are numerous.

### Live-format correction

The archive's browse JSON is useful for enumeration but does not expose the complete descriptive record assumed by the first adapter draft. The adapter therefore uses browse JSON for lightweight discovery, then requests the item's Dublin Core XML when detailed metadata is requested.

A second important correction is semantic: an Omeka import/add date is not the historical date represented by the item. The common model now keeps `date_raw`, `archive_added_raw`, and our own `ingested_at` separate.

## Internet Archive – Understanding 9/11

The adapter targets the public `911` collection through Internet Archive's advanced-search JSON endpoint and deliberately treats search metadata and detailed item metadata as separate stages.

Detailed item requests now summarize the file manifest without downloading media, including:

- original vs derivative file counts;
- formats;
- duration candidates;
- likely primary audio/video files;
- transcript/caption sidecars such as WebVTT/SRT when present.

Internet Archive items can belong to many auxiliary collections, including favorites. The configured research collection is therefore retained as lineage while the full source membership array remains untouched in `metadata_raw`.

## NIST WTC visual evidence

NIST is a primary synchronization source, not merely another media archive. NIST documented a visual database containing **6,899 photographs and 6,977 video clips**, with **3,279 photographs and 2,772 video clips timed to within approximately three seconds or better** during the investigation.

The documented NIST schema includes fields such as photographer/videographer, shot-from location, date recorded, end time, duration, time uncertainty, view direction, copyright/use restrictions, and event/content tags. The project now has:

- a metadata-only landing/repository inventory adapter;
- a schema-aware organized-media normalizer ready for a structured export;
- `capture_time` claims that preserve NIST timing uncertainty rather than flattening timing into a generic date field.

See `docs/NIST_METADATA_STRATEGY.md`.

## 191-record benchmark — first semantic work queue

A successful live GitHub Actions run collected and processed **191 metadata records**:

| Input | Records |
|---|---:|
| NIST repository inventory | 6 |
| Voices of 9.11 detailed sample | 20 |
| FDNY Incident Action Plans detailed sample | 20 |
| Sonic Memorial detailed sample | 20 |
| Internet Archive search sample | 100 |
| Internet Archive detailed sample | 25 |

Source totals were 125 Internet Archive records, 60 September 11 Digital Archive records, and 6 NIST repository records.

Field coverage in that benchmark was:

| Field | Populated |
|---|---:|
| collection lineage | 100.00% |
| title | 97.91% |
| archive-added date | 96.86% |
| media type | 79.06% |
| description | 74.35% |
| historical/source date | 65.45% |
| rights | 3.14% |
| creator/source identity | 0.00% |
| location | 0.00% |

The metadata-only duplicate pass proposed **0 high-confidence duplicates** at the conservative 0.86 threshold. That is evidence that richer identifiers, hashes, source/sequence metadata, and eventually perceptual fingerprints will be needed; it is not evidence that the collections contain no duplicate media.

### What the first queue exposed

The first naive work queue created **722 tasks**:

- 191 creator-resolution tasks;
- 191 location-resolution tasks;
- 185 rights-resolution tasks;
- 66 time-resolution tasks;
- 49 description tasks;
- 40 media-classification tasks.

That result exposed an important modeling error: a missing generic `location_raw` field does **not** mean every record needs camera geolocation. For example, an FDNY Incident Action Plan is a document with a coverage period, not a camera.

The model and work queue have therefore been revised to distinguish semantic claim kinds:

### Temporal kinds

- `capture_time`
- `recording_time`
- `event_time`
- `document_coverage`
- `interview_time`
- `publication_time`
- `archive_ingest_time`
- `unknown`

### Spatial kinds

- `capture_location`
- `event_location`
- `testimony_location`
- `document_coverage_location`
- `subject_location`
- `unknown`

Work-queue instructions are now media/collection-aware. Photo and video records can request camera capture locations and headings; testimony records request semantically labeled testimony/event locations; repository entries do not generate historical geolocation tasks; and FDNY plan titles with explicit date ranges are resolved deterministically as `document_coverage` claims instead of being sent to an AI agent.

## Current pipeline rule

The pipeline now has three distinct layers:

1. **Raw source metadata** — immutable representation of what the archive supplied.
2. **Deterministic derived claims** — narrow transformations where the evidence is explicit, such as an exact date range in an FDNY plan title or NIST's structured visual timing metadata.
3. **Agent proposals** — uncertain enrichment work requiring evidence, confidence, semantic claim type, and later review.

No derived claim is allowed to silently overwrite raw source fields.

## Next data-quality targets

1. Obtain a stable structured representation of NIST's Organized Photos and Video Clips metadata so its existing timing/location/source work can seed the timeline directly.
2. Expand Internet Archive detailed sampling to measure transcript/caption and usable-duration availability across broadcast collections.
3. Add already-geolocated photographic datasets as spatial seeds, while preserving their own uncertainty/provenance.
4. Improve source/creator resolution before scaling broadly, because the first benchmark shows creator identity is currently the weakest common field.
5. Treat rights enrichment as a separate custodial-source workflow; public visibility must never be interpreted as redistribution permission.

## Explicitly out of scope for Phase 0

- facial identification;
- automatically declaring uncertain event times/locations verified;
- scraping around authentication, paywalls, robots restrictions, or access controls;
- bulk mirroring media with unclear rights;
- reconstructing redacted material;
- ingesting graphic/sensitive material into a public-facing surface before content-warning rules are implemented.
