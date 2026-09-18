# WikiLeaks Collection Probe

This probe tests whether the current provenance-first archive model can accept
WikiLeaks datasets without creating a separate application or weakening the
historical-evidence rules already used by the September 11 collection.

## Result

The initial answer is **yes**.

Two materially different WikiLeaks datasets fit the current `SourceItem`
contract:

1. **PlusD / Cablegate** — document-centric diplomatic records.
2. **Iraq/Afghan War Diaries** — event-centric SIGACT records.

They exercise different sides of the engine and are useful as early
cross-domain validation.

## Public structures observed

### PlusD / Cablegate

The public PlusD interface exposes a formal cable reference and searchable
metadata such as:

- date
- subject
- origin / sender
- destination(s)
- original classification
- TAGS
- document text
- references to other cables
- references from other cables

Example formal reference inspected during the probe:

- `09STATE122615_a`

The formal reference is suitable as the stable `source_item_id`.

### War Diaries

Individual War Diaries records expose fields including:

- public record identifier
- tracking number
- type
- category
- region
- reporting unit
- unit name
- unit type
- casualty counts
- MGRS
- originator / updater groups
- CCIR
- SIGACT
- affiliation
- classification
- event timestamp
- narrative text

This already resembles a structured historical event record.

## Mapping to the engine

### Cablegate

```text
formal reference -> SourceItem.source_item_id
subject          -> title_raw
origin           -> creator_raw
document date    -> date_raw
body             -> description_raw
classification   -> metadata_raw
TAGS             -> metadata_raw
cross references -> metadata_raw initially; graph edges later
```

### War Diaries

```text
public id        -> SourceItem.source_item_id
tracking number  -> metadata_raw
title            -> title_raw
reporting unit   -> creator_raw
event timestamp  -> date_raw
region + MGRS    -> location_raw
narrative        -> description_raw
casualty fields  -> metadata_raw
classification   -> metadata_raw
```

## What this validates

The September 11 repository's foundational separation still works:

```text
raw/source observation
        -> normalization
        -> deterministic claims where possible
        -> machine proposals
        -> evidence-backed review
        -> verified/disputed/rejected state
```

WikiLeaks records do **not** require a separate evidence model.

## What still needs generalizing

The existing engine is currently more media/archive-oriented than diplomatic
document/event oriented. Before broad ingestion, the following should become
generic first-class concepts:

- `Event`
- `Relationship`
- `Claim`
- claim-to-claim support / contradiction
- collection-aware record roles
- generic source adapters independent of September-11 source IDs

For PlusD, cable-to-cable references should eventually become typed
relationships rather than remaining only metadata.

For War Diaries, MGRS should become a spatial claim through a deterministic
converter while preserving the original MGRS string.

## Collection design

Recommended collection IDs:

- `wikileaks-cablegate`
- `wikileaks-war-diaries-iraq`
- `wikileaks-war-diaries-afghanistan`

Do not treat all WikiLeaks releases as one homogeneous source. Each release
should retain its own schema, provenance, and semantics while sharing the
generic engine.

## Fetching strategy

This branch deliberately adds normalization before a bulk crawler.

The public sites are useful for structure discovery and small samples, but a
large import should prefer a legitimate bulk dataset or stable mirror when one
is available instead of repeatedly crawling search-result HTML.

Recommended sequence:

1. normalize captured/sample records
2. verify pipeline compatibility
3. identify bulk source / mirror
4. build a resumable metadata collector
5. ingest a 50-100 record Cablegate sample
6. ingest a 50-100 record War Diaries sample
7. run dedupe, temporal, spatial, entity, and work-queue passes
8. inspect failures before scaling

## Repo decision

Do **not** split into a new repository yet.

WikiLeaks should first run as another collection against the same engine. Once
both September 11 and WikiLeaks use the same core with collection-specific
configuration, extracting the generic engine into its own repository/package
will be evidence-driven rather than speculative.


## Implemented commands

Bulk-file imports are now wired into the existing CLI:

```bash
archive-ingest import-wikileaks-plusd cables.csv --limit 100 --output artifacts/raw/plusd.jsonl
archive-ingest import-wikileaks-war-diaries iraq-war-diary-redacted.csv --limit 100 --output artifacts/raw/war-diaries.jsonl
```

The adapters also accept JSON, JSONL, and NDJSON for local imports.

After normalization, the records can be passed through the unchanged shared pipeline:

```bash
archive-ingest profile-jsonl artifacts/raw/*.jsonl --output artifacts/reports/profile.json
archive-ingest derive-temporal-claims artifacts/raw/*.jsonl --output artifacts/reports/temporal-claims.jsonl
archive-ingest derive-spatial-claims artifacts/raw/*.jsonl --output artifacts/reports/spatial-claims.jsonl
archive-ingest derive-entity-claims artifacts/raw/*.jsonl --output artifacts/reports/entity-claims.jsonl
archive-ingest build-work-queue artifacts/raw/*.jsonl --output artifacts/reports/work-queue.jsonl
archive-ingest build-store --database artifacts/wikileaks.sqlite --records artifacts/raw/*.jsonl
```

A manual GitHub Actions workflow, `.github/workflows/wikileaks-sample.yml`,
accepts public HTTPS CSV URLs and imports up to 100 records from each supplied
dataset before exercising the shared evidence pipeline and uploading the
resulting SQLite store/reports as an artifact.

## Event-record semantics

War Diaries rows are now treated as generic `event_record` records rather
than unknown media. Research tasks use `event_time` and `event_location`
semantics.

If a War Diaries record has an MGRS grid reference but no latitude/longitude,
the work queue explicitly creates a location-resolution task. The raw MGRS
value remains preserved; the engine does not invent coordinates.

## Verification status

The original adapter compatibility tests passed on the initial probe commit.
Later app-authored commits did not automatically retrigger the repository's PR
workflow, so the newest implementation should be CI-run manually before merge.
