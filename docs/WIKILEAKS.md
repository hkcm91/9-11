# WikiLeaks collection

The WikiLeaks collection is the first non-9/11 production-style corpus running
on the Historical Evidence Engine.

It currently supports:

- PlusD / Cablegate diplomatic records
- Iraq / Afghanistan War Diaries SIGACT records
- CSV, JSON, JSONL and NDJSON local imports
- collection-aware research roles and work-queue semantics
- provenance-preserving import into the existing SQLite evidence store

## Commands

```bash
archive-ingest import-wikileaks-plusd cables.csv --limit 100 --output artifacts/raw/plusd.jsonl
archive-ingest import-wikileaks-war-diaries war-diaries.csv --limit 100 --output artifacts/raw/war-diaries.jsonl

archive-ingest --collection wikileaks profile-jsonl artifacts/raw/*.jsonl --output artifacts/reports/profile.json
archive-ingest --collection wikileaks derive-temporal-claims artifacts/raw/*.jsonl --output artifacts/reports/temporal-claims.jsonl
archive-ingest --collection wikileaks derive-spatial-claims artifacts/raw/*.jsonl --output artifacts/reports/spatial-claims.jsonl
archive-ingest --collection wikileaks derive-entity-claims artifacts/raw/*.jsonl --output artifacts/reports/entity-claims.jsonl
archive-ingest --collection wikileaks build-work-queue artifacts/raw/*.jsonl --output artifacts/reports/work-queue.jsonl
```

## Evidence semantics

A leaked record is a source record, not an established fact.

The collection ontology explicitly preserves the distinction between mention,
association, allegation, corroboration, contradiction and established claims.
Named-person entity resolution and consequential relationship/claim linking are
routed for human review.

## War Diaries

MGRS and region fields are preserved in raw metadata. They do not automatically
become a precise `location_raw` value. If no explicit named location exists,
the record remains unresolved spatially and the work queue creates an
`event_location` research task.

Casualty fields are likewise preserved as source assertions and are not
promoted into verified claims merely because they are present in a record.

## Cablegate

Formal references/MRNs, classification, routing destinations, TAGS and
cross-cable references are retained in `metadata_raw`. Cable-to-cable
references are candidates for future typed graph relationships; ingestion does
not automatically treat a reference as corroboration.

## Architecture

This collection lives under `src/evidence_collections/wikileaks/` rather than
inside the generic engine. The engine remains unaware of WikiLeaks-specific
source IDs and event semantics.


## First-pass evidence graph

The collection now supplies the engine's generic `derive_graph` hook.

For Cablegate records it deterministically proposes:

- one document node for the cable
- sender/origin organization nodes
- destination organization nodes
- referenced-cable document nodes
- typed `sent_from`, `sent_to`, and `references_document` relationships

For War Diaries records it proposes:

- one document node representing the source record
- one `sigact` event
- the reporting military unit when available
- region and raw MGRS place nodes
- typed `describes`, `reported_by`, `located_in`, and `occurred_at` relationships

Every derived object remains `proposed`, cites the source record, and carries a
deterministic provenance method. The graph pass does not assert corroboration or
established fact.

Build the graph with:

```bash
archive-ingest --collection wikileaks build-graph artifacts/raw/*.jsonl \
  --database artifacts/wikileaks.sqlite \
  --stats-output artifacts/reports/graph-stats.json
```

## Real regression sample

`src/evidence_collections/wikileaks/fixtures/real_sample.jsonl` contains two
small records manually transcribed from the public archive for regression
testing:

- PlusD cable `09STATE122615_a`
- War Diaries record `7893F7C5-E13B-4C3D-8B4A-75B93202ED14`

The fixture intentionally contains only enough source metadata to exercise
provenance, routing, event and relationship behavior; it is not intended to
replace the original documents.

Running the `wikileaks-sample` GitHub Action without dataset URLs uses this
fixture automatically. Supplying public CSV URLs instead exercises up to the
requested sample limit (100 by default).


## 200-record validation milestone

The `wikileaks-sample` workflow now doubles as a graph-quality validation job.

Set:

- `plusd_url` to a public Cablegate/PlusD CSV
- `war_diaries_url` to a public War Diaries CSV
- `sample_limit` to `100`

When both datasets are supplied, the workflow requires at least 100 normalized
records from each source, producing the intended 200-record validation corpus.

After graph materialization it runs:

```bash
archive-ingest --collection wikileaks analyze-graph-quality \
  --database artifacts/wikileaks.sqlite \
  --json-output artifacts/reports/graph-quality.json \
  --markdown-output artifacts/reports/graph-quality.md
```

The quality report checks:

- source counts
- node / event / relationship counts
- relationship predicates and assertion levels
- placeholder entities such as `Not Provided`
- duplicate canonical-name/type pressure
- isolated nodes
- dangling relationship endpoints
- events with missing or invalid times
- graph relationship density
- high-degree nodes that may indicate over-broad normalization

The report is descriptive. It never merges entities, removes records, upgrades
assertion strength, or verifies a claim automatically.

For bulk-source discovery, prefer stable public mirrors or institutional archive
copies rather than scraping the live search UI repeatedly. The workflow keeps
dataset URLs as explicit inputs so the exact source used for a validation run is
preserved in the Actions run metadata.
