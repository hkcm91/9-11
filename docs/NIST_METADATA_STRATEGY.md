# NIST WTC Metadata Strategy

Status: Phase 0 research note and implementation guidance.

## Why NIST is a primary anchor source

NIST's World Trade Center visual-evidence work is unusually important for the interactive archive because the investigation did much of the expensive synchronization work already.

NIST reports that its visual databases contained:

- 6,899 photographs;
- 6,977 video clips;
- 3,279 photographs timed to within 3 seconds or better;
- 2,772 video clips timed to within 3 seconds or better.

The investigation also documented tags and attributes including source/photographer and view direction. NIST warns that tag/attribute assignment was incomplete, so absence of a tag must never be interpreted as evidence that the depicted feature/event is absent.

## Immediate ingestion strategy

### Stage 1: repository inventory

Inventory the authoritative public repository entry points without downloading media.

Expected categories include:

- Organized Photos and Video Clips
- Original Video from Tapes
- Other Photos and Videos
- Images of Collected Steel
- Computer Simulations
- Fire Tests and Analysis

The current `NistWtcRepositoryAdapter` implements this layer.

### Stage 2: organized-media metadata

Highest priority is the Organized Photos and Video Clips collection because NIST states that tags and attributes were assigned to this subset.

Fields we should seek and preserve verbatim include:

- asset reference / record name;
- photographer/source;
- content classification;
- view direction;
- timing fields and timing precision;
- tags;
- copyright/credit information;
- any embedded-camera metadata separately from NIST-derived timing.

Do not flatten embedded-camera timestamps and NIST analytical timestamps into the same field. They are different evidence classes.

### Stage 3: timing anchors

Create `TemporalClaim` records from NIST timing metadata rather than overwriting raw source dates.

A NIST-derived timing claim should capture:

- exact or bounded event time;
- uncertainty / precision;
- NIST record identifier;
- method/source note where available;
- review status;
- relationship to original media asset.

NIST timing claims should initially be treated as high-quality historical evidence, but remain traceable and correctable rather than becoming immutable application truth.

### Stage 4: duplicate/original-media reconciliation

NIST explicitly notes that copies of organized photos/video may also appear under Other Photos and Videos or Original Video from Tapes without the same tags/attributes.

Therefore:

- never assume records in different NIST folders are distinct media;
- use asset names, source/photographer, sequence, duration, file hashes (where lawful/available), and perceptual fingerprints to reconcile copies;
- preserve each repository occurrence as a source record even when multiple occurrences resolve to one canonical media entity.

## Rights rule

Public availability is not a redistribution license. NIST states that repository material can include third-party copyrighted media. The project should therefore ingest metadata and provenance first, then mirror only media whose reuse status is explicitly compatible.

## Next engineering target

Once stable structured metadata endpoints or export files for Organized Photos and Video Clips are identified, implement a second NIST adapter that emits one `SourceItem` per photo/video record. The current landing-page adapter should remain as the authoritative repository-discovery layer.
