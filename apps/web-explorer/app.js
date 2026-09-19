const DATA_URL = "./data/explorer.json";

const EVENT_ANCHORS = [
  { time: "2001-09-11T08:46:00-04:00", label: "8:46", detail: "Flight 11 impact" },
  { time: "2001-09-11T09:03:00-04:00", label: "9:03", detail: "Flight 175 impact" },
  { time: "2001-09-11T09:37:00-04:00", label: "9:37", detail: "Pentagon impact" },
  { time: "2001-09-11T09:59:00-04:00", label: "9:59", detail: "South Tower collapse" },
  { time: "2001-09-11T10:03:00-04:00", label: "10:03", detail: "Flight 93 crash" },
  { time: "2001-09-11T10:28:00-04:00", label: "10:28", detail: "North Tower collapse" },
];

const WTC_REFERENCE = [
  {
    name: "North Tower footprint reference",
    bounds: [[40.71215, -74.01355], [40.71305, -74.01255]],
  },
  {
    name: "South Tower footprint reference",
    bounds: [[40.71095, -74.01345], [40.71185, -74.01240]],
  },
];

const state = {
  payload: null,
  items: [],
  visible: [],
  selectedId: null,
  markers: new Map(),
  map: null,
  footprintLayer: null,
  headingLayer: null,
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

function initMap() {
  state.map = L.map("map", {
    center: [40.7119, -74.0127],
    zoom: 15,
    minZoom: 12,
    maxZoom: 19,
    zoomControl: true,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(state.map);

  state.footprintLayer = L.layerGroup().addTo(state.map);
  for (const footprint of WTC_REFERENCE) {
    L.rectangle(footprint.bounds, {
      color: "#c9bfa9",
      weight: 1,
      dashArray: "4 3",
      fillColor: "#b9ab8f",
      fillOpacity: .08,
      interactive: true,
    })
      .bindTooltip(`${footprint.name} · approximate reference overlay`, {
        direction: "top",
        opacity: .9,
      })
      .addTo(state.footprintLayer);
  }
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

function updateClock() {
  const label = fmtTime(currentHistoricalTime());
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

function itemMatchesTime(item, current, windowMinutes) {
  if (!item.time) return untimedEl.checked && Boolean(item.location);
  const start = parseTime(item.time.start_time);
  const end = parseTime(item.time.end_time);
  const windowStart = new Date(current.getTime() - windowMinutes * 60000);
  const windowEnd = new Date(current.getTime() + windowMinutes * 60000);

  if (start && start > windowEnd) return false;
  if (end && end < windowStart) return false;
  if (!start && !end) return false;
  return true;
}

function applyFilters() {
  if (!state.payload) return;

  const current = currentHistoricalTime();
  const windowMinutes = Number(el("window-size").value);
  const mediaType = mediaFilterEl.value;
  const minConfidence = Number(confidenceEl.value) / 100;
  const search = searchEl.value.trim().toLowerCase();

  state.visible = state.items.filter((item) => {
    if (!itemMatchesTime(item, current, windowMinutes)) return false;
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
  el("moment-summary").textContent = `${state.visible.length.toLocaleString()} records near this moment`;
  el("map-window-label").textContent = `Evidence within ± ${windowMinutes} minutes`;
}

function renderMarkers() {
  for (const marker of state.markers.values()) marker.remove();
  state.markers.clear();

  for (const item of state.visible) {
    if (!item.location) continue;

    const status = claimStatus(item);
    const selected = item.id === state.selectedId;
    const symbol = mediaSymbol(item.media_type);
    const marker = L.marker(
      [item.location.latitude, item.location.longitude],
      {
        icon: L.divIcon({
          className: "",
          html: `<span class="evidence-map-marker ${escapeHtml(status)} ${selected ? "selected" : ""}" style="--marker-status:${markerColor(status)}"><span>${escapeHtml(symbol)}</span></span>`,
          iconSize: selected ? [30, 30] : [24, 24],
          iconAnchor: selected ? [15, 15] : [12, 12],
        }),
        riseOnHover: true,
      },
    ).addTo(state.map);

    marker.bindTooltip(
      `<div class="map-popup"><strong>${escapeHtml(item.title || "Untitled record")}</strong><span>${escapeHtml(mediaSymbol(item.media_type))} ${escapeHtml(item.media_type || "record")} · ${escapeHtml(fmtTime(item.time?.start_time || item.time?.end_time))}</span></div>`,
      { direction: "top", offset: [0, -5], opacity: .96 }
    );

    marker.on("click", () => selectItem(item.id, false));
    state.markers.set(item.id, marker);
  }

  renderHeading();
}

function renderHeading() {
  if (state.headingLayer) {
    state.headingLayer.remove();
    state.headingLayer = null;
  }
  if (!el("heading-toggle").checked || !state.selectedId) return;

  const item = state.items.find((candidate) => candidate.id === state.selectedId);
  if (!item?.location || item.location.heading_deg == null) return;

  const origin = L.latLng(item.location.latitude, item.location.longitude);
  const distanceM = 115;
  const bearing = Number(item.location.heading_deg) * Math.PI / 180;
  const northM = Math.cos(bearing) * distanceM;
  const eastM = Math.sin(bearing) * distanceM;
  const lat = origin.lat + northM / 111320;
  const lon = origin.lng + eastM / (111320 * Math.cos(origin.lat * Math.PI / 180));

  state.headingLayer = L.polyline([origin, [lat, lon]], {
    color: "#e5d5b3",
    weight: 2,
    opacity: .9,
    dashArray: "5 4",
  }).addTo(state.map);
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
    node.querySelector(".evidence-card-time").textContent = fmtTime(item.time?.start_time || item.time?.end_time);
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

      <div class="detail-summary-grid">
        <div class="detail-summary-card">
          <span>When</span>
          <strong>${escapeHtml(fmtTime(item.time?.start_time || item.time?.end_time))}</strong>
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

  if (focusMap && item.location) {
    state.map.flyTo([item.location.latitude, item.location.longitude], Math.max(state.map.getZoom(), 16), {
      duration: .45,
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
  el("footprint-toggle").addEventListener("change", () => {
    if (el("footprint-toggle").checked) state.footprintLayer.addTo(state.map);
    else state.footprintLayer.remove();
  });
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
    untimedEl.checked = true;
    searchEl.value = "";
    state.selectedId = null;
    detailEl.classList.remove("open");
    state.map.setView([40.7119, -74.0127], 15);
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
    statusEl.textContent = `${state.payload.item_count.toLocaleString()} reconstruction-oriented records · read model v${state.payload.schema_version}`;
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
