import * as maplibregl from "https://unpkg.com/maplibre-gl@6.10.0/dist/maplibre-gl.mjs";

import { getSceneState, SCENE_LAYERS, updateSceneSources } from "./scene.mjs";

import { timeBounds, matchesHistoricalTime, summarizeTimes } from "./evidence-time.mjs";

const DATA_URL = "./data/explorer.json";

const EVENT_ANCHORS = [
  { time: "2001-09-11T08:46:00-04:00", label: "8:46", detail: "Flight 11 impact" },
  { time: "2001-09-11T09:03:00-04:00", label: "9:03", detail: "Flight 175 impact" },
  { time: "2001-09-11T09:37:00-04:00", label: "9:37", detail: "Pentagon impact" },
  { time: "2001-09-11T09:59:00-04:00", label: "9:59", detail: "South Tower collapse" },
  { time: "2001-09-11T10:03:00-04:00", label: "10:03", detail: "Flight 93 crash" },
  { time: "2001-09-11T10:28:00-04:00", label: "10:28", detail: "North Tower collapse" },
];

const MAP_STYLE = "https://tiles.openfreemap.org/styles/fiord";
const MAP_HOME = {
  center: [-74.0130, 40.7131],
  zoom: 15.1,
  pitch: 58,
  bearing: 27,
};

const WTC_SITE = {
  type: "Feature",
  properties: { name: "World Trade Center historical reconstruction area" },
  geometry: {
    type: "Polygon",
    coordinates: [[
      [-74.01475, 40.71035],
      [-74.01155, 40.71035],
      [-74.01125, 40.71365],
      [-74.01455, 40.71370],
      [-74.01475, 40.71035],
    ]],
  },
};

const state = {
  payload: null,
  items: [],
  visible: [],
  selectedId: null,
  markers: new Map(),
  map: null,
  mapReady: false,
  sceneKey: null,
};

const el = (id) => document.getElementById(id);
const statusEl = el("status");
const timelineEl = el("timeline");
const clockEl = el("clock");
const mapClockEl = el("map-clock");
const mediaFilterEl = el("media-filter");
const confidenceEl = el("confidence-filter");
const confidenceValueEl = el("confidence-value");
const untimedEl = el("untimed-toggle");
const searchEl = el("search");
const detailEl = el("detail");

function parseTime(value) {
  return value ? new Date(value) : null;
}

function minutesBetween(a, b) {
  return Math.round((b.getTime() - a.getTime()) / 60000);
}

function fmtTime(value) {
  const date = value instanceof Date ? value : parseTime(value);
  if (!date) return "Untimed";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function fmtShort(value) {
  const date = value instanceof Date ? value : parseTime(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function mediaElementHtml(media) {
  if (!media) return "";
  const url = safeSourceUrl(media.url);
  const thumbnail = safeSourceUrl(media.thumbnail_url);
  const name = escapeHtml(media.name || "Source media");
  const host = escapeHtml(media.host || "Source");
  const sourceNote = media.preview_only ? "Source-hosted preview" : "Remote source media";

  if (media.kind === "image") {
    const src = thumbnail !== "#" ? thumbnail : url;
    if (src === "#") return "";
    return `
      <figure class="media-preview">
        <img src="${escapeHtml(src)}" alt="${name}" loading="lazy" decoding="async">
        <figcaption>${host} · ${sourceNote}</figcaption>
      </figure>`;
  }

  if (media.kind === "video" && url !== "#") {
    const poster = thumbnail !== "#" ? ` poster="${escapeHtml(thumbnail)}"` : "";
    return `
      <figure class="media-preview">
        <video controls preload="metadata" playsinline${poster}>
          <source src="${escapeHtml(url)}">
          Your browser could not play this source-hosted video.
        </video>
        <figcaption>${host} · no autoplay</figcaption>
      </figure>`;
  }

  if (media.kind === "audio" && url !== "#") {
    return `
      <figure class="media-preview media-preview-audio">
        <audio controls preload="none">
          <source src="${escapeHtml(url)}">
          Your browser could not play this source-hosted audio.
        </audio>
        <figcaption>${host} · no autoplay</figcaption>
      </figure>`;
  }

  if (thumbnail !== "#") {
    return `
      <figure class="media-preview">
        <img src="${escapeHtml(thumbnail)}" alt="${name}" loading="lazy" decoding="async">
        <figcaption>${host} · source item thumbnail</figcaption>
      </figure>`;
  }

  return "";
}

function mediaSectionHtml(item) {
  const media = item.media;
  if (!media) return "";

  if (media.sensitive) {
    const reasons = Array.isArray(media.sensitivity_reasons) && media.sensitivity_reasons.length
      ? media.sensitivity_reasons.join(", ")
      : "source sensitivity flag";
    return `
      <div class="detail-section">
        <div class="detail-label">Media</div>
        <div class="sensitive-media-gate">
          <strong>Sensitive source media</strong>
          <p>This record is flagged by the source for ${escapeHtml(reasons)}. The media is not loaded until you choose to reveal it.</p>
          <button type="button" class="secondary-button" data-reveal-sensitive>Reveal media</button>
        </div>
      </div>`;
  }

  const mediaHtml = mediaElementHtml(media);
  if (!mediaHtml) return "";
  return `
    <div class="detail-section">
      <div class="detail-label">Media</div>
      ${mediaHtml}
    </div>`;
}

function claimStatus(item) {
  return item.time?.status || item.location?.status || "proposed";
}

function markerColor(status) {
  return ({
    verified: "#779d83",
    reviewed: "#7f9eb8",
    disputed: "#b77676",
    proposed: "#d4a75e",
  })[status] || "#a8afb4";
}

function mediaSymbol(mediaType) {
  const value = String(mediaType || "").toLowerCase();
  if (value.includes("photo") || value.includes("image")) return "●";
  if (value.includes("video") || value.includes("moving")) return "◆";
  if (value.includes("audio") || value.includes("sound")) return "▲";
  return "■";
}

function stylizeBasemap() {
  for (const layer of state.map.getStyle().layers || []) {
    try {
      if (layer.type === "fill-extrusion") {
        state.map.setLayoutProperty(layer.id, "visibility", "none");
        continue;
      }

      const id = layer.id.toLowerCase();
      if (layer.type === "symbol" && /(poi|shop|amenity|transit|airport|housenumber)/.test(id)) {
        state.map.setLayoutProperty(layer.id, "visibility", "none");
      } else if (layer.type === "background") {
        state.map.setPaintProperty(layer.id, "background-color", "#0f1a21");
      } else if (layer.type === "fill" && /(water|ocean|river|lake)/.test(id)) {
        state.map.setPaintProperty(layer.id, "fill-color", "#17303a");
        state.map.setPaintProperty(layer.id, "fill-opacity", 0.96);
      } else if (layer.type === "fill" && /(park|landcover|landuse|wood|grass)/.test(id)) {
        state.map.setPaintProperty(layer.id, "fill-color", "#26353a");
        state.map.setPaintProperty(layer.id, "fill-opacity", 0.72);
      } else if (layer.type === "line" && /(road|street|motorway|highway|path)/.test(id)) {
        state.map.setPaintProperty(layer.id, "line-color", "#69747b");
        state.map.setPaintProperty(layer.id, "line-opacity", 0.42);
      }
    } catch (error) {
      console.debug("Basemap style layer left unchanged:", layer.id, error);
    }
  }

  try {
    state.map.setLight({
      anchor: "map",
      color: "#f3ead7",
      intensity: 0.42,
      position: [1.15, 210, 38],
    });
  } catch (error) {
    console.debug("Map light customization unavailable", error);
  }
}

function addHistoricalLayers() {
  const labelLayerId = (state.map.getStyle().layers || [])
    .find((layer) => layer.type === "symbol" && layer.layout?.["text-field"])?.id;

  state.map.addSource("openfreemap-buildings", {
    type: "vector",
    url: "https://tiles.openfreemap.org/planet",
  });

  const massingLayer = {
    id: "city-massing",
    source: "openfreemap-buildings",
    "source-layer": "building",
    type: "fill-extrusion",
    minzoom: 13.5,
    filter: [
      "all",
      ["!=", ["get", "hide_3d"], true],
      ["!", ["within", WTC_SITE]],
    ],
    paint: {
      "fill-extrusion-color": "#89939a",
      "fill-extrusion-height": [
        "coalesce",
        ["get", "render_height"],
        ["get", "height"],
        10,
      ],
      "fill-extrusion-base": [
        "coalesce",
        ["get", "render_min_height"],
        ["get", "min_height"],
        0,
      ],
      "fill-extrusion-opacity": 0.58,
      "fill-extrusion-vertical-gradient": true,
    },
  };

  try {
    state.map.addLayer(massingLayer, labelLayerId);
  } catch (error) {
    console.warn("WTC exclusion expression unavailable; rendering city massing without exclusion.", error);
    massingLayer.filter = ["!=", ["get", "hide_3d"], true];
    state.map.addLayer(massingLayer, labelLayerId);
  }

  state.map.addSource("wtc-site", { type: "geojson", data: WTC_SITE });
  state.map.addLayer({
    id: "wtc-reference-fill",
    type: "fill",
    source: "wtc-site",
    paint: {
      "fill-color": "#d9c89f",
      "fill-opacity": 0.055,
    },
  }, labelLayerId);
  state.map.addLayer({
    id: "wtc-reference-line",
    type: "line",
    source: "wtc-site",
    paint: {
      "line-color": "#d9c89f",
      "line-width": 1.25,
      "line-opacity": 0.7,
      "line-dasharray": [3, 2],
    },
  }, labelLayerId);

  state.map.addSource("historical-wtc", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  state.map.addLayer({
    id: "historical-wtc-3d",
    type: "fill-extrusion",
    source: "historical-wtc",
    paint: {
      "fill-extrusion-color": [
        "match",
        ["get", "kind"],
        "antenna", "#ded6c7",
        "damage", "#443b37",
        "debris", "#8e877b",
        "#c3c7c7",
      ],
      "fill-extrusion-height": ["get", "height"],
      "fill-extrusion-base": ["get", "base"],
      "fill-extrusion-opacity": 0.97,
      "fill-extrusion-vertical-gradient": true,
    },
  }, labelLayerId);

  for (const [id, color, opacity] of [["wtc-smoke", "#8c8882", 0.42], ["wtc-dust", "#b2a797", 0.18]]) {
    state.map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    state.map.addLayer({
      id, source: id, type: "fill-extrusion",
      paint: {
        "fill-extrusion-color": color,
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": ["get", "base"],
        "fill-extrusion-opacity": opacity,
        "fill-extrusion-vertical-gradient": false,
      },
    }, labelLayerId);
  }

  state.map.addSource("wtc-labels", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  state.map.addLayer({
    id: "historical-wtc-labels",
    type: "symbol",
    source: "wtc-labels",
    minzoom: 14.2,
    layout: {
      "text-field": ["get", "label"],
      "text-font": ["Noto Sans Regular"],
      "text-size": 10,
      "text-letter-spacing": 0.18,
      "text-offset": [0, 2.2],
      "text-anchor": "top",
      "text-allow-overlap": false,
    },
    paint: {
      "text-color": "#eee7d8",
      "text-halo-color": "#132029",
      "text-halo-width": 1.6,
      "text-opacity": 0.88,
    },
  });

  state.map.addSource("selected-heading", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  state.map.addLayer({
    id: "selected-heading-line",
    type: "line",
    source: "selected-heading",
    layout: { visibility: "none" },
    paint: {
      "line-color": "#e5d5b3",
      "line-width": 2,
      "line-opacity": 0.92,
      "line-dasharray": [3, 2],
    },
  });

  updateLayerVisibility();
}

function setLayerVisibility(ids, visible) {
  if (!state.mapReady) return;
  for (const id of ids) {
    if (state.map.getLayer(id)) {
      state.map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    }
  }
}

function updateLayerVisibility() {
  setLayerVisibility(
    ["wtc-reference-fill", "wtc-reference-line"],
    el("footprint-toggle").checked,
  );
  setLayerVisibility(["city-massing"], el("buildings-toggle").checked);
  setLayerVisibility(
    SCENE_LAYERS,
    el("wtc3d-toggle").checked,
  );
}

function initMap() {
  state.map = new maplibregl.Map({
    container: "map",
    style: MAP_STYLE,
    center: MAP_HOME.center,
    zoom: MAP_HOME.zoom,
    minZoom: 12,
    maxZoom: 19,
    pitch: MAP_HOME.pitch,
    bearing: MAP_HOME.bearing,
    maxPitch: 75,
    canvasContextAttributes: { antialias: true },
    attributionControl: true,
  });

  state.map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");

  state.map.on("load", () => {
    stylizeBasemap();
    addHistoricalLayers();
    state.mapReady = true;
    updateHistoricalScene();
    updateLayerVisibility();
    renderHeading();
  });

  state.map.on("error", (event) => {
    if (event?.error) console.error("MapLibre:", event.error);
  });
}

function configureTimeline() {
  const start = parseTime(state.payload.window.start);
  const end = parseTime(state.payload.window.end);
  const totalMinutes = Math.max(1, minutesBetween(start, end));
  timelineEl.min = "0";
  timelineEl.max = String(totalMinutes);
  timelineEl.value = "0";
  el("time-start").textContent = fmtShort(start);
  el("time-end").textContent = fmtShort(end);
  renderEventAnchors(start, end);
  renderDensity(start, end, totalMinutes);
  updateClock();
}

function renderEventAnchors(start, end) {
  const band = el("event-band");
  band.replaceChildren();
  const total = end.getTime() - start.getTime();

  for (const event of EVENT_ANCHORS) {
    const eventTime = parseTime(event.time);
    if (!eventTime || eventTime < start || eventTime > end) continue;
    const anchor = document.createElement("div");
    anchor.className = "event-anchor";
    anchor.style.left = `${((eventTime.getTime() - start.getTime()) / total) * 100}%`;
    anchor.innerHTML = `<strong>${escapeHtml(event.label)}</strong><span>${escapeHtml(event.detail)}</span>`;
    band.appendChild(anchor);
  }
}

function representativeItemTime(item) {
  if (!item.time) return null;
  return parseTime(item.time.start_time || item.time.end_time);
}

function renderDensity(start, end, totalMinutes) {
  const band = el("density-band");
  band.replaceChildren();
  const bins = Math.max(80, Math.min(180, totalMinutes));
  const counts = Array.from({ length: bins }, () => 0);
  const span = end.getTime() - start.getTime();

  for (const item of state.items) {
    const time = representativeItemTime(item);
    if (!time || time < start || time > end) continue;
    const ratio = (time.getTime() - start.getTime()) / span;
    const index = Math.min(bins - 1, Math.max(0, Math.floor(ratio * bins)));
    counts[index] += 1;
  }

  const max = Math.max(1, ...counts);
  for (const count of counts) {
    const node = document.createElement("span");
    node.className = "density-bin";
    node.style.height = `${2 + (count / max) * 17}px`;
    node.style.opacity = String(.18 + (count / max) * .62);
    band.appendChild(node);
  }
}

function currentHistoricalTime() {
  const start = parseTime(state.payload.window.start);
  return new Date(start.getTime() + Number(timelineEl.value) * 60000);
}

function updateHistoricalScene() {
  if (!state.payload) return;
  const scene = getSceneState(currentHistoricalTime());
  const key = `${scene.north}/${scene.south}`;
  const descriptions = { intact: "intact", impacted: "impact damage / smoke", collapsed: "collapsed / debris" };
  el("scene-status").textContent = `North: ${descriptions[scene.north]} · South: ${descriptions[scene.south]}`;
  if (!state.mapReady || key === state.sceneKey) return;
  updateSceneSources(state.map, scene);
  state.sceneKey = key;
}

function updateClock() {
  const label = fmtTime(currentHistoricalTime());
  updateHistoricalScene();
  clockEl.textContent = label;
  mapClockEl.textContent = label;
}

function configureMediaTypes() {
  const values = [...new Set(state.items.map((item) => item.media_type).filter(Boolean))].sort();
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value[0].toUpperCase() + value.slice(1);
    mediaFilterEl.appendChild(option);
  }
}

function applyFilters() {
  if (!state.payload) return;

  const current = currentHistoricalTime();
  const windowMinutes = Number(el("window-size").value);
  const mediaType = mediaFilterEl.value;
  const minConfidence = Number(confidenceEl.value) / 100;
  const search = searchEl.value.trim().toLowerCase();

  state.visible = state.items.filter((item) => {
    if (!matchesHistoricalTime(item, current, windowMinutes, untimedEl.checked)) return false;
    if (mediaType !== "all" && item.media_type !== mediaType) return false;

    const confidence = Math.max(item.time?.confidence || 0, item.location?.confidence || 0);
    if (confidence < minConfidence) return false;

    if (search) {
      const haystack = [
        item.title,
        item.creator,
        item.source_id,
        item.collection,
        item.description,
      ].filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });

  renderMarkers();
  renderEvidenceStrip();
  renderStats();
  updateClock();
  const { timed, untimed } = summarizeTimes(state.visible);
  el("moment-summary").textContent = `${timed.toLocaleString()} timed records near this moment${untimed ? ` · ${untimed.toLocaleString()} untimed (not matched to clock)` : ""}`;
  el("map-window-label").textContent = `Timed evidence within ± ${windowMinutes} minutes${untimed ? " · untimed records also shown" : ""}`;
}

function evidenceTimeLabel(item) {
  const bounds = timeBounds(item);
  if (!bounds) return "Capture time unknown · not matched to clock";
  return bounds.start === bounds.end ? fmtTime(new Date(bounds.start))
    : `${fmtShort(new Date(bounds.start))}–${fmtShort(new Date(bounds.end))} (time range)`;
}

function renderMarkers() {
  for (const entry of state.markers.values()) {
    entry.popup?.remove();
    entry.marker.remove();
  }
  state.markers.clear();

  for (const item of state.visible) {
    if (!item.location) continue;

    const status = claimStatus(item);
    const selected = item.id === state.selectedId;
    const symbol = mediaSymbol(item.media_type);
    const node = document.createElement("button");
    node.type = "button";
    node.className = "evidence-map-marker " + status + (selected ? " selected" : "");
    node.style.setProperty("--marker-status", markerColor(status));
    node.innerHTML = "<span>" + escapeHtml(symbol) + "</span>";
    node.setAttribute("aria-label", item.title || "Evidence record");
    node.title = item.title || "Evidence record";

    const marker = new maplibregl.Marker({
      element: node,
      anchor: "center",
    })
      .setLngLat([item.location.longitude, item.location.latitude])
      .addTo(state.map);

    const tooltipThumb = item.media && !item.media.sensitive
      ? safeSourceUrl(item.media.thumbnail_url || (item.media.kind === "image" ? item.media.url : null))
      : "#";
    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 18,
      className: "archive-map-popup",
    }).setHTML(
      '<div class="map-popup">' +
      (tooltipThumb !== "#" ? '<img class="map-popup-thumb" src="' + escapeHtml(tooltipThumb) + '" alt="">' : "") +
      "<strong>" + escapeHtml(item.title || "Untitled record") + "</strong><span>" +
      escapeHtml(symbol) + " " +
      escapeHtml(item.media_type || "record") + " · " +
      escapeHtml(evidenceTimeLabel(item)) +
      "</span></div>"
    );

    node.addEventListener("mouseenter", () => {
      popup
        .setLngLat([item.location.longitude, item.location.latitude])
        .addTo(state.map);
    });
    node.addEventListener("mouseleave", () => popup.remove());
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      selectItem(item.id, false);
    });

    state.markers.set(item.id, { marker, popup, element: node });
  }

  renderHeading();
}

function renderHeading() {
  if (!state.mapReady || !state.map.getSource("selected-heading")) return;

  const source = state.map.getSource("selected-heading");
  const empty = { type: "FeatureCollection", features: [] };

  if (!el("heading-toggle").checked || !state.selectedId) {
    source.setData(empty);
    setLayerVisibility(["selected-heading-line"], false);
    return;
  }

  const item = state.items.find((candidate) => candidate.id === state.selectedId);
  if (!item?.location || item.location.heading_deg == null) {
    source.setData(empty);
    setLayerVisibility(["selected-heading-line"], false);
    return;
  }

  const lat0 = Number(item.location.latitude);
  const lon0 = Number(item.location.longitude);
  const distanceM = 115;
  const bearing = Number(item.location.heading_deg) * Math.PI / 180;
  const northM = Math.cos(bearing) * distanceM;
  const eastM = Math.sin(bearing) * distanceM;
  const lat1 = lat0 + northM / 111320;
  const lon1 = lon0 + eastM / (111320 * Math.cos(lat0 * Math.PI / 180));

  source.setData({
    type: "Feature",
    properties: {},
    geometry: {
      type: "LineString",
      coordinates: [[lon0, lat0], [lon1, lat1]],
    },
  });
  setLayerVisibility(["selected-heading-line"], true);
}

function renderEvidenceStrip() {
  const container = el("evidence-strip");
  container.replaceChildren();
  const template = el("evidence-card-template");

  const sorted = [...state.visible].sort((a, b) => {
    const aTime = representativeItemTime(a)?.getTime() ?? Number.MAX_SAFE_INTEGER;
    const bTime = representativeItemTime(b)?.getTime() ?? Number.MAX_SAFE_INTEGER;
    return aTime - bTime;
  });

  el("evidence-strip-count").textContent = `${Math.min(sorted.length, 80)} shown`;

  for (const item of sorted.slice(0, 80)) {
    const node = template.content.firstElementChild.cloneNode(true);
    if (item.id === state.selectedId) node.classList.add("selected");

    node.querySelector(".evidence-card-symbol").textContent = mediaSymbol(item.media_type);
    node.querySelector(".evidence-card-time").textContent = evidenceTimeLabel(item);
    node.querySelector(".evidence-card-title").textContent = item.title || "Untitled record";
    node.querySelector(".evidence-card-meta").textContent =
      [item.creator, item.media_type, item.source_id].filter(Boolean).join(" · ");

    const status = claimStatus(item);
    const statusNode = node.querySelector(".evidence-card-status");
    statusNode.classList.add(status);
    statusNode.title = status;

    node.addEventListener("click", () => selectItem(item.id, true));
    container.appendChild(node);
  }

  if (!sorted.length) {
    const empty = document.createElement("p");
    empty.className = "fine-print";
    empty.textContent = "No evidence matches the current time and filters.";
    container.appendChild(empty);
  }
}

function renderStats() {
  el("visible-count").textContent = state.visible.length.toLocaleString();
  el("mapped-count").textContent = state.visible.filter((item) => item.location).length.toLocaleString();
  el("source-count").textContent = new Set(state.visible.map((item) => item.source_id)).size.toLocaleString();
}

function humanize(value) {
  return String(value || "—").replaceAll("_", " ");
}

function confidenceLabel(value) {
  const score = Math.round((Number(value) || 0) * 100);
  if (score >= 90) return `${score}% · high`;
  if (score >= 70) return `${score}% · moderate`;
  if (score > 0) return `${score}% · tentative`;
  return "Not scored";
}

function compactLocation(item) {
  if (!item.location) return "Not mapped";
  const kind = humanize(item.location.location_kind);
  return item.location.heading_deg == null
    ? kind
    : `${kind} · heading ${Math.round(item.location.heading_deg)}°`;
}

function claimHtml(title, claim, kindField) {
  if (!claim) return "";
  const status = escapeHtml(claim.status || "proposed");
  const rows = [
    ["Type", humanize(claim[kindField])],
    ["Status", `<span class="status-badge ${status}">${status}</span>`],
    ["Confidence", confidenceLabel(claim.confidence)],
    ["Method", humanize(claim.method)],
  ];

  if (kindField === "time_kind") {
    rows.push(["Start", claim.start_time ? fmtTime(claim.start_time) : "Open interval"]);
    rows.push(["End", claim.end_time ? fmtTime(claim.end_time) : "Open interval"]);
  } else {
    rows.push(["Coordinates", `${Number(claim.latitude).toFixed(5)}, ${Number(claim.longitude).toFixed(5)}`]);
    if (claim.accuracy_radius_m != null) rows.push(["Accuracy", `± ${claim.accuracy_radius_m} m`]);
    if (claim.heading_deg != null) rows.push(["Camera heading", `${claim.heading_deg}°`]);
  }

  return `
    <div class="detail-section">
      <div class="detail-label">${escapeHtml(title)}</div>
      <div class="claim-box">
        <dl class="claim-grid">
          ${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${key === "Status" ? value : escapeHtml(value ?? "—")}</dd>`).join("")}
        </dl>
      </div>
    </div>
  `;
}

function selectItem(id, focusMap) {
  state.selectedId = id;
  const item = state.items.find((candidate) => candidate.id === id);
  if (!item) return;

  detailEl.classList.add("open");
  const status = claimStatus(item);
  const confidence = Math.max(item.time?.confidence || 0, item.location?.confidence || 0);

  const entityText = item.entities?.length
    ? item.entities
        .map((entity) => `${escapeHtml(humanize(entity.role || entity.entity_kind))}: ${escapeHtml(entity.normalized_name || entity.name_raw)}`)
        .join("<br>")
    : "No entity references exported.";

  detailEl.innerHTML = `
    <div class="detail-hero">
      <div class="detail-kicker">
        <span class="detail-media-symbol">${escapeHtml(mediaSymbol(item.media_type))}</span>
        <div>
          <p class="eyebrow">${escapeHtml(item.media_type || "Evidence record")}</p>
          <span class="status-badge ${escapeHtml(status)}">${escapeHtml(status)}</span>
        </div>
      </div>
      <h2>${escapeHtml(item.title || "Untitled record")}</h2>
      <div class="detail-value">${escapeHtml(item.description || "No source description.")}</div>
      ${mediaSectionHtml(item)}

      <div class="detail-summary-grid">
        <div class="detail-summary-card">
          <span>When</span>
          <strong>${escapeHtml(evidenceTimeLabel(item))}</strong>
        </div>
        <div class="detail-summary-card">
          <span>Where</span>
          <strong>${escapeHtml(compactLocation(item))}</strong>
        </div>
        <div class="detail-summary-card">
          <span>Confidence</span>
          <strong>${escapeHtml(confidenceLabel(confidence))}</strong>
        </div>
        <div class="detail-summary-card">
          <span>Source</span>
          <strong>${escapeHtml(item.creator || item.source_id)}</strong>
        </div>
      </div>
    </div>

    <div class="detail-section">
      <div class="detail-label">Source record</div>
      <div class="detail-value">
        ${escapeHtml(item.source_id)}<br>
        ${escapeHtml(item.creator || "Creator not stated")}<br>
        ${escapeHtml(item.collection || "Collection not stated")}<br>
        <a class="source-link" href="${escapeHtml(safeSourceUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>
      </div>
    </div>

    ${claimHtml("Time evidence", item.time, "time_kind")}
    ${claimHtml("Location evidence", item.location, "location_kind")}

    <div class="detail-section">
      <div class="detail-label">People / organizations</div>
      <div class="detail-value">${entityText}</div>
    </div>

    <div class="detail-section">
      <div class="detail-label">Rights / publication note</div>
      <div class="detail-value">${escapeHtml(item.rights || "No reusable-rights conclusion exported. Consult the original source before reuse.")}</div>
    </div>

    <div class="detail-section">
      <div class="detail-label">Preserved observations</div>
      <div class="detail-value">${Number(item.observation_count || 0).toLocaleString()} source observation(s)</div>
    </div>
  `;

  const revealButton = detailEl.querySelector("[data-reveal-sensitive]");
  if (revealButton && item.media) {
    revealButton.addEventListener("click", () => {
      const gate = detailEl.querySelector(".sensitive-media-gate");
      if (!gate) return;
      const wrapper = document.createElement("div");
      wrapper.innerHTML = mediaElementHtml(item.media);
      const mediaNode = wrapper.firstElementChild;
      if (mediaNode) gate.replaceWith(mediaNode);
    });
  }

  if (focusMap && item.location) {
    state.map.flyTo({
      center: [item.location.longitude, item.location.latitude],
      zoom: Math.max(state.map.getZoom(), 16),
      pitch: 62,
      bearing: MAP_HOME.bearing,
      duration: 550,
      essential: true,
    });
  }
  renderMarkers();
  renderEvidenceStrip();
}

function setTimelineToIso(value) {
  const target = parseTime(value);
  const start = parseTime(state.payload.window.start);
  const end = parseTime(state.payload.window.end);
  if (!target || target < start || target > end) return;
  timelineEl.value = String(minutesBetween(start, target));
  applyFilters();
}

function wireControls() {
  timelineEl.addEventListener("input", applyFilters);
  el("window-size").addEventListener("change", applyFilters);
  mediaFilterEl.addEventListener("change", applyFilters);
  confidenceEl.addEventListener("input", () => {
    confidenceValueEl.textContent = `${confidenceEl.value}%`;
    applyFilters();
  });
  untimedEl.addEventListener("change", applyFilters);
  searchEl.addEventListener("input", applyFilters);
  el("footprint-toggle").addEventListener("change", updateLayerVisibility);
  el("buildings-toggle").addEventListener("change", updateLayerVisibility);
  el("wtc3d-toggle").addEventListener("change", updateLayerVisibility);
  el("heading-toggle").addEventListener("change", renderHeading);

  el("reset-time").addEventListener("click", () => {
    timelineEl.value = "0";
    applyFilters();
  });

  el("reset-view").addEventListener("click", () => {
    timelineEl.value = "0";
    mediaFilterEl.value = "all";
    confidenceEl.value = "0";
    confidenceValueEl.textContent = "0%";
    untimedEl.checked = false;
    searchEl.value = "";
    state.selectedId = null;
    detailEl.classList.remove("open");
    state.map.flyTo({
      center: MAP_HOME.center,
      zoom: MAP_HOME.zoom,
      pitch: MAP_HOME.pitch,
      bearing: MAP_HOME.bearing,
      duration: 650,
      essential: true,
    });
    applyFilters();
  });

  el("event-band").addEventListener("click", (event) => {
    const anchor = event.target.closest(".event-anchor");
    if (anchor?.dataset.time) setTimelineToIso(anchor.dataset.time);
  });
}

function makeEventAnchorsClickable() {
  const nodes = [...el("event-band").querySelectorAll(".event-anchor")];
  const start = parseTime(state.payload.window.start);
  const end = parseTime(state.payload.window.end);
  const visibleEvents = EVENT_ANCHORS.filter((event) => {
    const time = parseTime(event.time);
    return time && time >= start && time <= end;
  });
  nodes.forEach((node, index) => {
    node.dataset.time = visibleEvents[index]?.time || "";
    node.style.pointerEvents = "auto";
    node.style.cursor = "pointer";
    node.title = visibleEvents[index]?.detail || "";
  });
}

async function load() {
  initMap();
  wireControls();

  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
    state.items = state.payload.items || [];
    configureTimeline();
    makeEventAnchorsClickable();
    configureMediaTypes();
    const mediaCount = state.items.filter((item) => item.media).length;
    statusEl.textContent = `${state.payload.item_count.toLocaleString()} records · ${mediaCount.toLocaleString()} with media · read model v${state.payload.schema_version}`;
    applyFilters();
  } catch (error) {
    statusEl.textContent = "Explorer data could not be loaded.";
    el("evidence-strip").innerHTML = `
      <p class="fine-print">
        Generate <code>data/explorer.json</code> with the archive-export-explorer command,
        then serve this directory over HTTP.
      </p>`;
    console.error(error);
  }
}

load();
