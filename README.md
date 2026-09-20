# Historical Evidence Engine — and the 9/11 Interactive Archive

A research-first project for building trustworthy, explorable maps and
timelines of publicly available historical media, testimony, events, people and
places.

The codebase is now two layers:

- **Historical Evidence Engine** (`src/historical_engine/`) — a reusable,
  provenance-first engine for historical archives: source registration,
  metadata-first ingestion, raw-source preservation, normalization, duplicate
  detection, claims, an evidence graph, agent proposals, review, work queues
  and query. It contains no assumptions about any particular corpus.
- **Collections** (`src/evidence_collections/`) — one directory per historical
  corpus, supplying its ontology, source registry, rules, hooks and adapters.

```text
Historical Evidence Engine
        |
        +-- september11     the 9/11 archive and research pipeline
        +-- demo_history    a tiny synthetic corpus, architectural validation
        +-- future collections
```

The September 11 collection is the first and the reason the engine exists. It
works exactly as it did before the engine was extracted.

Within a collection, the project is still split into two concerns:

- **Archive Workbench** — ingest, normalize, deduplicate, geolocate,
  synchronize, source, review and improve historical records.
- **Public Explorer** — a map + timeline interface for exploring synchronized
  photos, video, audio, testimony, people, places and story threads.

The guiding principle is unchanged: **never replace the source record with an
AI guess.** Raw source metadata remains immutable; derived claims carry
evidence, uncertainty, provenance and review history. AI proposes; a human
reviews; nothing verifies itself.

## Getting started

```bash
python -m pip install -e .[dev]
pytest -q

archive-ingest list-collections --verbose
archive-ingest --collection september11 list-sources
archive-ingest run-demo-pipeline --database demo.sqlite
```

`--collection` is optional; omitting it uses the transitional `september11`
default so existing commands and workflows keep working.

## Documentation

The [public-interest document library](docs/DOCUMENT_LIBRARY.md) adds a local
searchable reader, preserved document versions, page citations, and Jev-assisted
comparisons alongside the existing map. Start with `archive-library serve` after
installing `.[documents]` and importing/reviewing a source manifest.
For the 49-file National Archives Pentagon Papers inventory, restartable bulk
downloads, and validated Cablegate samples, see the guide's larger-source batches.

| Document | What it covers |
| --- | --- |
| `docs/ENGINE.md` | The engine, what a collection defines, the claim lifecycle, the evidence graph, AI boundaries, and how to add a collection |
| `docs/ENGINE_REFACTOR.md` | The architecture audit, per-module classification, migration risks and what remains 9/11-specific |
| `docs/DATA_MODEL.md` | The data model |
| `docs/PLAN.md` | The implementation roadmap |
| `docs/PHASE0_*.md`, `docs/ADAPTER_911DA.md`, `docs/NIST_METADATA_STRATEGY.md` | September 11 source research and adapter notes |
