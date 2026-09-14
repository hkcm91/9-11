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

Do **not** treat all 70k records as equivalent evidence. Collection membership should be preserved as a first-class field so event-day primary media, later oral histories, anniversary recollections, institutional records, and recovery documents can be filtered and weighted differently.

For the first research corpus, prioritize collections that improve reconstruction:

1. event-day photo/video/audio where available;
2. named oral histories with explicit locations/times;
3. FDNY / official operational records;
4. continuous audio/video sources that can become synchronization anchors.

Large retrospective story collections are still valuable, but they should not dominate the first reconstruction sample simply because they are numerous.

## Internet Archive – Understanding 9/11

The existing adapter targets the public `911` collection through Internet Archive's advanced-search JSON endpoint and deliberately collects metadata only. The first sample workflow requests 100 records so we can measure field coverage before widening the crawl.

## First corpus experiment

The `sample-corpus` GitHub Action collects:

- 100 September 11 Digital Archive metadata records;
- 100 Internet Archive records;
- a combined field-coverage profile;
- conservative duplicate candidates;
- a SHA-256 manifest of generated artifacts.

Raw media is **not** downloaded.

The purpose of this first 200-record experiment is to answer four questions before scaling:

1. Which normalized fields are actually populated reliably?
2. Which source-specific fields need to be promoted into the common model?
3. How often do obvious cross-source duplicates appear?
4. What additional identifiers are needed to preserve provenance and collection lineage?
