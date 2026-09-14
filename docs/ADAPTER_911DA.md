# September 11 Digital Archive adapter

The first Phase 0 adapter is metadata-only by design.

## Source

- Site: `https://911digitalarchive.org`
- Platform: Omeka
- Public browse count observed during Phase 0 research: 70,359 items
- Browse UI advertises: Atom, CSV, DC-RDF, DCMES XML, JSON, Omeka XML, RSS2

The adapter uses the JSON browse output exposed by the public item browser.

## Safety / archival rules

- Do not bulk-download media through this adapter.
- Preserve each complete source JSON object in `SourceItem.metadata_raw`.
- Treat Dublin Core / Omeka rights text as source metadata, not as a blanket reuse grant.
- Do not infer that publicly viewable media may be mirrored.
- Keep a default request delay of one second and identify the project in the User-Agent.
- Stop cleanly on empty pages and allow bounded `max_items` / `max_pages` runs.

## Usage

After installing the project:

```bash
archive-ingest sample-911da --limit 50 --output data/fixtures/911da-sample.jsonl
```

To sample one collection:

```bash
archive-ingest sample-911da --collection 139 --limit 25 --output data/fixtures/911da-videos.jsonl
```

Collection `139` is currently the site's `911 Videos` collection and is useful for exercising media-oriented metadata. Collection IDs are source identifiers and must be preserved rather than re-numbered internally.

## Normalization

The adapter extracts conservative raw display fields where present:

- Title
- Creator / Contributor
- Description / Abstract
- Date
- Spatial Coverage / Coverage
- Rights

Extraction never removes or rewrites the source payload. If an Omeka field cannot be interpreted confidently, it remains available in `metadata_raw` for future adapters/enrichment passes.

## Next step

Run the CLI against the live source to create the first 25–50 record fixture, inspect shape differences across collections, and only then expand the parser. The unit tests intentionally use a source-shaped fixture rather than assuming undocumented fields beyond the standard Omeka structures the site advertises.
