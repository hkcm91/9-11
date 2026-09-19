# September 11 Explorer MVP

This is the first read-only public surface for the September 11 collection.

It is deliberately a **static consumer of an exported read model**. The browser
does not open SQLite, ingest sources, run AI, or change claim status. Research
logic stays in the Historical Evidence Engine / Archive Workbench.

## Generate the data

After building an evidence store:

```bash
archive-export-explorer \
  --database artifacts/archive.sqlite \
  --output apps/web-explorer/data/explorer.json \
  --start 2001-09-11T08:00:00-04:00 \
  --end 2001-09-11T12:00:00-04:00
```

The exporter chooses one displayable temporal and spatial claim per record while
preserving the selected claim's confidence, status, method, and provenance
fields. Broad administrative/document dates are not used to position a record
on the historical timeline.

## Run locally

Serve the directory over HTTP so the browser can fetch the JSON file:

```bash
python -m http.server 8000 --directory apps/web-explorer
```

Then open `http://localhost:8000`.

## Current MVP

- Lower Manhattan map (Leaflet + OpenStreetMap)
- September 11 morning timeline scrubber
- configurable visible-time window
- media type / confidence / text filters
- mappable untimed evidence toggle
- record cards and source links
- selected temporal/location claim status, confidence, method, and uncertainty
- entity references and rights note
- no mutation or verification actions

## Intentional limits

This is not yet the final public product. It does not currently provide media
previews, story threads, sensitive-content classification, camera frustums,
authentication, or reviewer actions. Those should be added only after the first
mixed real corpus shows which read-model fields are stable enough to expose.
