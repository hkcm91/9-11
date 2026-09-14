# Phase 0 Source Inventory

Status: initial authoritative/public-source pass.

This phase is intentionally metadata-first. The objective is to understand what is publicly discoverable, how it can be accessed, how reusable it is, and how much value it offers for later synchronization/geolocation work before attempting large-scale downloading.

## Initial high-value sources

### 1. NIST World Trade Center Disaster Investigation Materials

URL: https://www.nist.gov/world-trade-center-investigation/photos-videos-and-simulations

Why it matters:
- thousands of images and hundreds of hours of video are publicly available through the NIST disaster repository;
- includes organized photo/video clips, original video from tapes, documents, and investigation-generated material;
- especially valuable for later timestamp synchronization and camera/source reconstruction.

Access / rights:
- public release repository;
- NIST explicitly warns that some collected material is copyrighted by private individuals or organizations;
- therefore ingest metadata and identifiers freely, but treat media mirroring as item-specific.

Priority: CRITICAL.

### 2. September 11 Digital Archive

URL: https://911digitalarchive.org/
Browse: https://911digitalarchive.org/items/browse

Why it matters:
- archive states it contains 150,000+ digital items overall;
- current browse interface exposes 70,000+ catalogued item records;
- includes first-hand stories, images, video, audio, email, documents, and historical web material;
- the browse system exposes machine-readable formats including JSON, CSV, RDF, and Omeka XML, making it one of the best first ingestion targets.

Priority: CRITICAL and likely first adapter.

### 3. Library of Congress preservation record

URL: https://www.loc.gov/item/2003615054/

Why it matters:
- authoritative preservation/provenance record for the September 11 Digital Archive;
- useful for authority metadata and understanding collection lineage rather than as the primary item-level ingest endpoint.

Priority: HIGH for provenance.

### 4. National Archives - 9/11 Commission Records

URL: https://www.archives.gov/research/9-11

Why it matters:
- official records of the 9/11 Commission;
- interviews, hearings, documents, and investigation records can provide authoritative anchors for people, events, organizations, and timelines;
- NARA reports approximately 570 cubic feet of textual records, though a substantial portion remains classified.

Priority: HIGH.

### 5. National September 11 Memorial & Museum Collection

URL: https://911memorial.org/visit/museum/collection
Catalog: https://collection.911memorial.org/

Why it matters:
- Museum states its permanent collection contains 83,000+ artifacts;
- includes material evidence, first-person testimony, historical records, oral histories, media, and special collections;
- public catalog is a curated subset and is continually growing.

Access / rights:
- index public catalog records first;
- do not assume public catalog display grants redistribution rights.

Priority: CRITICAL for authority metadata, oral histories, and story-thread building.

### 6. Smithsonian National Museum of American History

URL: https://americanhistory.si.edu/collections/object-groups/september-11
Photos: https://americanhistory.si.edu/collections/object-groups/september-11/photographs

Why it matters:
- Congress designated the Smithsonian/NMAH as the national repository for September 11 collections;
- NMAH describes 600+ artifacts in the broader collection;
- the Photographic History Collection describes more than 2,400 September 11 photographic objects.

Priority: HIGH.

### 7. Internet Archive - Understanding 9/11: A Television News Archive

URL: https://archive.org/details/911

Why it matters:
- major source for time-continuous television coverage;
- broadcast timelines provide valuable synchronization anchors for later video/audio reconstruction;
- Internet Archive metadata APIs may permit straightforward catalog ingestion.

Access / rights:
- item metadata and licenses must be preserved;
- streaming availability does not itself imply redistribution rights.

Priority: CRITICAL.

### 8. Naval History and Heritage Command - AR/670 Pentagon Attack Collection

URL: https://www.history.navy.mil/research/archives/Collections/ncdu-det-206/2001/9-11-pentagon-attack.html

Why it matters:
- oral histories from Pentagon survivors, rescuers, responders, recovery/identification teams, and support personnel;
- released interviews often include dedicated pages, summaries, transcripts, related photos, and links to people involved in the same events;
- unusually useful for entity/event graph construction because many records are already cross-linked.

Important limitation:
- only a portion of the full collection is authorized for public release;
- preserve existing redactions and never infer or reconstruct redacted material.

Priority: HIGH.

### 9. Columbia University September 11 Oral History Project

URLs:
- https://www.ccohr.incite.columbia.edu/911-oral-history-project
- https://www.incite.columbia.edu/projects/september-11-2001-oral-histories

Why it matters:
- Columbia reports more than 900 recorded hours involving 600+ people;
- 687 hours with 351 individuals are reported as open and publicly available;
- began interviewing soon after the attacks, making it valuable for contemporaneous memory and long-form personal narratives.

Priority: CRITICAL for people/story/event graph work.

### 10. Voices of 9.11

URLs:
- https://hereisnewyorkv911.org/
- https://www.911digitalarchive.org/collections/show/267

Why it matters:
- more than 500 self-directed video testimonies recorded in 2002-2003;
- participant-controlled format makes it a rich complementary testimony collection;
- also provides a useful example of a collection mirrored/preserved through multiple institutions.

Priority: HIGH.

## Phase 0 classification rules

Every source must distinguish these concepts:

- `public_access`: Can the public currently reach records/media?
- `rights_status`: May the project copy/rehost/reuse it?
- `access_method`: Web catalog, API, export endpoint, PDFs, repository, etc.
- `metadata_quality`: How structured and useful is existing metadata?
- `ingest_mode`: Metadata only, transcript, authority metadata, or media where clearly permitted.
- `priority`: Historical/information value, not merely collection size.

`public_access = true` MUST NOT be interpreted as `rights_status = reusable`.

## Recommended ingestion order

1. September 11 Digital Archive metadata/export adapter.
2. NIST repository collection/metadata inventory.
3. Internet Archive Understanding 9/11 metadata + broadcast schedule inventory.
4. Columbia oral-history metadata inventory.
5. 9/11 Memorial public-catalog metadata inventory.
6. Navy AR/670 released interview/transcript metadata.
7. Smithsonian photographic-object metadata.
8. NARA 9/11 Commission authority/event records.
9. Voices of 9.11 metadata and cross-source reconciliation.
10. Library of Congress authority/provenance links.

This order deliberately favors sources that can seed many downstream relationships early: timestamps, people, locations, source identities, and continuous media sequences.

## Phase 0 next tasks

- determine whether the September 11 Digital Archive's Omeka endpoints can be consumed directly and document request limits;
- inventory NIST repository hierarchy and stable media identifiers without bulk downloading media;
- enumerate the Internet Archive Understanding 9/11 collection and determine programmatic metadata access;
- record terms/robots/access constraints for every enabled source;
- define a source-item fixture format and ingest 25-50 records from at least three structurally different sources;
- measure duplicate/overlap patterns across those fixtures;
- add secondary/community projects (photo maps, videographer maps, preservation groups) only after the institutional backbone is represented.

## Explicitly out of scope for Phase 0

- facial identification;
- automatically declaring event times/locations verified;
- scraping around authentication, paywalls, robots restrictions, or access controls;
- bulk mirroring media with unclear rights;
- ingesting graphic/sensitive material into a public-facing surface before content-warning rules are implemented.
