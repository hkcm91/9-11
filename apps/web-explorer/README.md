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

Untimed records are excluded by default, including after Reset. Enable “Include
untimed records” to inspect them independently of the clock; counts and time
labels distinguish these from timed evidence. Missing capture times are never
inferred from the currently selected scene. Single-ended timestamps are treated
as instants, and records with two timestamps retain their full interval.

Pages versions local JavaScript modules and CSS with the checked-out commit so
new HTML cannot accidentally run a previously cached, pre-collapse Explorer app.

## Intentional limits

### Detailed reconstruction and South Tower replay

The default renderer now uses a Three.js custom MapLibre layer (`tower-layer.mjs`)
with locally generated, meter-based models: façade ribs and floor lines, mechanical
bands, roof equipment, a North Tower antenna, localized impact patches, a neutral
plaza surface, and rubble. No downloaded model, Blender runtime, or model license
is required. Geometry is a stylized architectural approximation, not a surveyed
building model. The existing simplified MapLibre scene remains the automatic
fallback if the detailed renderer cannot load.

The timeline has one-second resolution. Play/Pause advances the same historical
cursor used by evidence filtering, with 1×, 10× and 60× speed options. ±1s controls
and “Inspect South Tower sequence” support close inspection. Scrubbing, resetting,
changing reconstructed-motion mode, or leaving the browser tab pauses playback.
Playback stops at the timeline end and never loops or starts automatically.
Reduced-motion preferences default reconstructed motion off.

`replay.mjs` samples fixed authored poses over an **illustrative 12-second South
Tower sequence beginning at the existing rounded 09:59:00 EDT anchor**. Upper
section descent/tilt, progressive removal of lower sections, façade fragments,
and dust are deterministic functions of historical time. These are animation
parameters, not measured trajectories, a physical simulation, or a footage-
calibrated reconstruction. The North Tower still changes directly to rubble at
10:28; a detailed North Tower collapse sequence is deferred.

Smoke samples use fixed seeds and historical time rather than accumulated particle
state. Dust expands and thins over an illustrative five minutes. Pausing stops
motion; reverse seeking restores the same geometry and atmospheric state. With
reconstructed motion disabled, collapse uses the discrete states and atmospheric
forms stay spatially fixed. The reconstruction toggle hides the whole custom layer.

Historical reference: [NIST investigation scope](https://www.nist.gov/world-trade-center-investigation/about-investigation).
Rendering integration: [MapLibre Three.js custom layer](https://maplibre.org/maplibre-gl-js/docs/examples/add-a-3d-model-using-threejs/).
NIST's engineering investigation is not reproduced by this visualization. Future
work includes comparison against properly timed footage, reviewed motion curves,
more accurate plaza/context models, and detailed North Tower motion.

Run all scene, replay and time-filter checks with `node --test apps/web-explorer/*.test.mjs`.

### Simplified fallback scene

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
In the fallback, these are symbolic state indicators, not measured damage, plume direction,
dispersion, debris extent, or a collapse simulation. Dust persists as a collapsed
state cue; it does not claim a constant historical dust concentration. There are
no flames or transition animations in the fallback renderer.
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
