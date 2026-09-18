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
