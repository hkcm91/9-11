# Phase 0 sample 001 — live metadata experiment

Date: 2026-09-14

## Corpus

The second live sample collected **160 public metadata records**:

- 20 Voices of 9.11 records (September 11 Digital Archive collection 267), enriched through DCMES XML;
- 20 FDNY Incident Action Plan records (collection 11), enriched through DCMES XML;
- 20 Sonic Memorial Project records (collection 266), enriched through DCMES XML;
- 100 Internet Archive `911` television-news records.

No raw media was downloaded.

## Observed metadata coverage

From the 160-record sample before the historical-date/archive-date split was applied:

- title: 97.5%
- description: 70.62%
- collection lineage: 100%
- creator: 0%
- location: 0%
- rights: 0%

The absence of creator/location/rights in this sample is a **source-metadata limitation**, not evidence that those facts do not exist. Those fields will require additional source-specific enrichment or research.

## Important findings

### 1. September 11 Digital Archive browse JSON is an enumeration feed

The public JSON browse endpoint returns an envelope such as:

```json
{
  "items": [
    {
      "collection_id": 267,
      "added": "2014-01-16 12:31:31",
      "id": 96746
    }
  ],
  "total_results": 517
}
```

It does not expose the descriptive fields visible on the HTML item page.

**Decision:** use browse JSON for stable IDs and collection membership only, then enrich selected records through the item's DCMES XML export.

### 2. DCMES XML is a useful structured detail layer

Per-item DCMES enrichment recovered titles reliably and descriptions for many Sonic Memorial records without brittle HTML scraping.

Example observed record:

- title: `Robert Olin's Office in the WTC [Archival]`
- description: audio derived from a videotape made in the WTC office two weeks before the attacks
- collection: Sonic Memorial Project (266)

### 3. Archive ingest dates are not historical dates

The September 11 Digital Archive enumeration feed includes `added` timestamps from its later Omeka migration/import. These were initially landing in `date_raw`, which would be dangerous for a historical timeline.

**Decision:** split date semantics:

- `date_raw`: date represented by / asserted about the historical material;
- `archive_added_raw`: date the source archive publicly added/imported the record;
- `ingested_at`: date our system fetched the record.

No timeline code should infer event time from `archive_added_raw`.

### 4. Internet Archive collection membership is noisy

Internet Archive records can belong simultaneously to the canonical `911` collection, channel collections, television archive collections, and arbitrary `fav-*` collections.

**Decision:** `collection_raw` records the collection intentionally queried by the adapter (currently `911`). The full membership list remains preserved in `metadata_raw` for later subcollection analysis.

### 5. Random archive sampling is not representative

The first unfiltered September 11 Digital Archive sample disproportionately surfaced later anniversary submissions.

**Decision:** sample deliberately by collection and evidence value. The first targeted collections are:

- Voices of 9.11 (267)
- FDNY Incident Action Plans (11)
- Sonic Memorial Project (266)

This makes the early corpus more useful for reconstruction than simply ingesting the newest or first N archive records.

### 6. Metadata-only dedupe found no high-confidence pairs yet

At a threshold of 0.86, the 160-record sample produced zero duplicate candidates.

This is not surprising: the collections sampled are structurally different, and cross-source duplicate detection will eventually need media fingerprints, original-source identifiers, durations, broadcast timing, and/or richer descriptive metadata.

## Next experiment

1. rerun the same targeted corpus with corrected date semantics and media-type profiling;
2. add richer Internet Archive item-detail metadata for broadcast duration and file/original identifiers;
3. inventory a first NIST photo/video collection and preserve its stable identifiers;
4. add explicit evidence-class labels such as `event_day_primary`, `oral_history`, `operational_record`, `later_recollection`, and `broadcast`;
5. begin temporal extraction only after those evidence classes exist.
