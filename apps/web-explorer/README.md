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
Tower sequence beginning at NIST's 09:58:59 EDT collapse-initiation time**. Upper
section descent/tilt, progressive removal of lower sections, façade fragments,
and dust are deterministic functions of historical time. These are animation
parameters, not measured trajectories, a physical simulation, or a footage-
calibrated reconstruction. The North Tower still changes directly to rubble at
10:28:22 EDT; a detailed North Tower collapse sequence is deferred.

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

The selected historical second drives `getSceneState()` in `scene.mjs`. Both
renderers and the timeline anchors share one set of NIST event times: North impact
08:46:30, South impact 09:02:59, South collapse initiation 09:58:59 and North collapse
initiation 10:28:22 (September 11, 2001, EDT). NIST estimates approximately one-second
accuracy for these events. Other sources can use different time conventions; this
choice does not retime the evidence records. Scrubbing backward restores earlier
states. Evidence filters and the time window do not change the scene clock.

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

### Geographic and architectural references

`references/memorial-pools.geojson` preserves the OSM North/South Pool polygons
(ways 697722178 and 697722181, version 9, retrieved 2026-09-19). Their polygon
centers and edge orientation provide approximate geographic registration. The
Memorial describes the pools as sitting within the former tower footprints:
[Memorial reference](https://www.911memorial.org/visit/memorial/about-memorial).
This is not a survey, and the pool dimensions are not reused as tower dimensions.
Both renderers share the derived centers and -29.117° local-axis rotation.
The geographic data are © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright).

The detailed model uses approximately 3 m diagonal corner bevels, 59 flat-face
column lines at 1.016 m spacing, and mechanical bands associated with floors 7–8,
41–42, 75–76 and 108–109. References: [NIST NCSTAR 1, Table 1–1 and tower description](https://nvlpubs.nist.gov/nistpubs/Legacy/NCSTAR/ncstar1.pdf)
and [NIST structural interim report](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication1000-5v5.pdf).
Floor elevations are still normalized across the total model height, not extracted
from architectural elevation drawings. Roof details, impact-hole contours and the
plaza remain approximate. Reduced façade contrast limits distant aliasing.

[Timing source: NIST visual evidence paper, p. 3](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=100911).
The interface exposes these references in “Reconstruction sources & limits”.

Upper structural sections now retain full scale while separating; they no longer
shrink as a visual proxy for breakup. Roof details follow their section. The
motion curves and particle trajectories remain authored approximations. Soft
camera-facing density patches replace the previous spherical smoke/dust volumes;
these atmospheric shapes and fade rates have not been calibrated to footage.

Further accuracy work needs reviewed architectural elevations, precisely timed
camera views for motion comparison, and a sourced North Tower collapse sequence.
The Explorer does not currently provide story threads, full camera frustums,
authentication, or reviewer actions.


### Aircraft approaches and impact cues

The detailed scene includes neutral, approximately 767-sized procedural aircraft.
“Inspect Flight 11 approach” and “Inspect Flight 175 approach” pause eight seconds
before contact and select 1× playback; press Play to inspect. Each model appears
only in the final 12 seconds before impact, disappears at contact, and is followed
by a muted six-second impact cue and the existing damage/smoke state. There is no
sound, flash, loop, or independent clock. Reverse scrubbing restores the aircraft.
Disabling reconstructed motion hides aircraft and transient impact cues; the
historical damage states remain. The simplified fallback retains its damage and
smoke states and disables the aircraft inspection shortcuts.

The short straight approach uses central estimates from
[NIST NCSTAR 1, Table 6–4](https://tsapps.nist.gov/publication/get_pdf.cfm?lang=en&pub_id=909017):
443/542 mph speeds, 10.6°/6° downward approach, 180.3°/13° clockwise headings from
Plan North, and 25°/38° left-wing-down bank for Flight 11/175 respectively.
The model's local north axis represents Plan North. Constant speed and attitude
are extrapolated backward for visualization, not measured flight paths. Impact
altitudes use the existing approximate damage-zone midpoints; South's lateral
contact is offset approximately 7 m. Aircraft details and cue size/duration are
illustrative, not a validated aircraft or fuel-fire simulation.

City massing now excludes polygons touching or intersecting the reconstruction
area using a distance filter (with a 1 m tolerance). The former `within` expression
supports points/lines, not building polygons, and allowed modern WTC structures to
overlap the reconstructed towers. Simplified tower layers also remain explicitly
hidden whenever the detailed renderer is active, including after toggle changes.


### Localized flames

Small flame shapes sit on each tower's damaged facade from impact until collapse
initiation. They are illustrative fire indicators, not evidence of exact flame
locations, temperatures, intensity, or fire spread. The detailed renderer uses
soft translucent flame textures with slow variation driven only by historical
time. Pause freezes them; reverse scrubbing restores the same shape. Turning off
Reconstructed motion keeps a static flame shape. The lightweight fallback uses
small amber facade patches. Both paths remove flames at collapse initiation and
hide them with the historical reconstruction toggle. No flash, sound, or separate
animation loop is added.
