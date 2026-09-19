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

- Stylized pitched Lower Manhattan map (MapLibre GL + OpenFreeMap)
- GPU-rendered 3D city massing with a historical WTC exclusion area
- Georeferenced 3D North/South Tower reconstruction, including the North Tower antenna
- Independent toggles for city massing, historical WTC reconstruction, footprint reference, and camera heading
- September 11 morning timeline scrubber
- configurable visible-time window
- media type / confidence / text filters
- mappable untimed evidence toggle
- record cards and source links
- selected temporal/location claim status, confidence, method, and uncertainty
- entity references and rights note
- no mutation or verification actions

## Intentional limits

### Time-aware WTC scene

The selected timeline minute drives `getSceneState()` in `scene.mjs`. Both towers
begin intact; North is impacted at 08:46, South at 09:03, South is collapsed at
09:59, and North at 10:28 (September 11, 2001, EDT). These intentionally rounded
anchors match the existing timeline, not second-level event timestamps. Scrubbing
backward restores earlier states. Evidence filters and the evidence time window
do not change the scene clock. The reconstruction toggle hides all scene layers.

Standing towers use the existing footprints and heights. Thin dark patches mark
the approximate north face / floors 93–99 of North and south face / floors 77–85
of South, offset toward its east side. Floor bands are mapped approximately to
350–377 m and 290–324 m, not surveyed elevations. Historical placement references:
[NIST progress report](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication1000-5v1.pdf)
and [NIST December 2003 report](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=860539).

Smoke uses static translucent polygon volumes at impact height. Collapsed states
replace the tower and antenna with low debris and light ground-level dust.
These are symbolic state indicators, not measured damage, plume direction,
dispersion, debris extent, or a collapse simulation. Dust persists as a collapsed
state cue; it does not claim a constant historical dust concentration. There are
no flames, disaster animation loops, extra timers, or transition animations.
Nearby buildings remain modern context. Detailed plaza geometry, façade models,
atmospheric refinement and optional subtle transitions are deferred.

Run scene boundary, geometry, and reverse-scrub checks with:

```bash
node --test apps/web-explorer/scene.test.mjs
```

This is not yet the final public product. The current Twin Towers are lightweight
geographic extrusions intended to establish the historical-atlas camera, scale, and
site placement. Detailed GLB/Three.js architecture can replace them without changing
the evidence model. The explorer does not currently provide story threads, full
camera frustums, authentication, or reviewer actions. Those should be added only after the first
mixed real corpus shows which read-model fields are stable enough to expose.
