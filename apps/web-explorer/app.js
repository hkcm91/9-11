const DATA_URL = "./data/explorer.json";

const state = {
  payload: null,
  items: [],
  visible: [],
  selectedId: null,
  markers: new Map(),
  map: null,
};

const el = (id) => document.getElementById(id);
const statusEl = el("status");
const timelineEl = el("timeline");
const clockEl = el("clock");
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
    verified: "#79aa8c",
    reviewed: "#7aa2c8",
    disputed: "#bb7777",
    proposed: "#d6a85f",
  })[status] || "#aeb5bc";
}

function initMap() {
  state.map = L.map("map", {
    center: [40.7115, -74.0125],
    zoom: 15,
    minZoom: 11,
    maxZoom: 19,
    zoomControl: true,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(state.map);
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
  updateClock();
}

function currentHistoricalTime() {
  const start = parseTime(state.payload.window.start);
  return new Date(start.getTime() + Number(timelineEl.value) * 60000);
}

function updateClock() {
  clockEl.textContent = fmtTime(currentHistoricalTime());
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
  renderList();
  renderStats();
  updateClock();
}

function renderMarkers() {
  for (const marker of state.markers.values()) marker.remove();
  state.markers.clear();

  for (const item of state.visible) {
    if (!item.location) continue;
    const status = claimStatus(item);
    const marker = L.circleMarker(
      [item.location.latitude, item.location.longitude],
      {
        radius: item.id === state.selectedId ? 9 : 6,
        weight: item.id === state.selectedId ? 3 : 1.5,
        color: markerColor(status),
        fillColor: markerColor(status),
        fillOpacity: .72,
      },
    ).addTo(state.map);

    marker.bindPopup(`
      <div class="map-popup">
        <strong>${escapeHtml(item.title || "Untitled record")}</strong>
        <span>${escapeHtml(item.creator || item.source_id)} · ${escapeHtml(fmtTime(item.time?.start_time || item.time?.end_time))}</span>
      </div>
    `);
    marker.on("click", () => selectItem(item.id, false));
    state.markers.set(item.id, marker);
  }
}

function renderList() {
  const container = el("record-list");
  container.replaceChildren();

  const template = el("record-card-template");
  for (const item of state.visible.slice(0, 250)) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.id = item.id;
    if (item.id === state.selectedId) node.classList.add("selected");
    node.querySelector(".record-card-time").textContent =
      fmtTime(item.time?.start_time || item.time?.end_time);
    node.querySelector(".record-card-title").textContent = item.title || "Untitled record";
    node.querySelector(".record-card-meta").textContent =
      [item.creator, item.media_type, item.source_id].filter(Boolean).join(" · ");
    const status = claimStatus(item);
    const confidence = Math.round(Math.max(item.time?.confidence || 0, item.location?.confidence || 0) * 100);
    node.querySelector(".record-card-claim").textContent = `${status} · ${confidence}% confidence`;
    node.addEventListener("click", () => selectItem(item.id, true));
    container.appendChild(node);
  }

  if (!state.visible.length) {
    const empty = document.createElement("p");
    empty.className = "fine-print";
    empty.textContent = "No records match this moment and filter set.";
    container.appendChild(empty);
  }
}

function renderStats() {
  el("visible-count").textContent = state.visible.length.toLocaleString();
  el("mapped-count").textContent = state.visible.filter((item) => item.location).length.toLocaleString();
  el("source-count").textContent = new Set(state.visible.map((item) => item.source_id)).size.toLocaleString();
  el("verified-count").textContent = state.visible.filter(
    (item) => item.time?.status === "verified" || item.location?.status === "verified"
  ).length.toLocaleString();
}

function claimHtml(title, claim, kindField) {
  if (!claim) return "";
  const status = escapeHtml(claim.status || "proposed");
  const confidence = Math.round((claim.confidence || 0) * 100);
  const rows = [
    ["Type", claim[kindField]],
    ["Status", `<span class="status-badge ${status}">${status}</span>`],
    ["Confidence", `${confidence}%`],
    ["Method", claim.method || "—"],
  ];

  if (kindField === "time_kind") {
    rows.push(["Start", claim.start_time ? fmtTime(claim.start_time) : "open"]);
    rows.push(["End", claim.end_time ? fmtTime(claim.end_time) : "open"]);
  } else {
    rows.push(["Coordinates", `${Number(claim.latitude).toFixed(5)}, ${Number(claim.longitude).toFixed(5)}`]);
    if (claim.accuracy_radius_m != null) rows.push(["Accuracy radius", `${claim.accuracy_radius_m} m`]);
    if (claim.heading_deg != null) rows.push(["Heading", `${claim.heading_deg}°`]);
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
  const entityText = item.entities?.length
    ? item.entities
        .map((entity) => `${escapeHtml(entity.role || entity.entity_kind)}: ${escapeHtml(entity.normalized_name || entity.name_raw)}`)
        .join("<br>")
    : "None exported";

  detailEl.innerHTML = `
    <div class="detail-section">
      <p class="eyebrow">Evidence record</p>
      <h2>${escapeHtml(item.title || "Untitled record")}</h2>
      <div class="detail-value">${escapeHtml(item.description || "No source description.")}</div>
    </div>
    <div class="detail-section">
      <div class="detail-label">Source</div>
      <div class="detail-value">
        ${escapeHtml(item.source_id)}<br>
        ${escapeHtml(item.creator || "Creator not stated")}<br>
        ${escapeHtml(item.collection || "Collection not stated")}<br>
        <a class="source-link" href="${escapeHtml(safeSourceUrl(item.source_url))}" target="_blank" rel="noopener noreferrer">Open source record ↗</a>
      </div>
    </div>
    ${claimHtml("Timeline claim", item.time, "time_kind")}
    ${claimHtml("Location claim", item.location, "location_kind")}
    <div class="detail-section">
      <div class="detail-label">Entity references</div>
      <div class="detail-value">${entityText}</div>
    </div>
    <div class="detail-section">
      <div class="detail-label">Rights note</div>
      <div class="detail-value">${escapeHtml(item.rights || "No reusable-rights conclusion exported. Refer to the source record.")}</div>
    </div>
    <div class="detail-section">
      <div class="detail-label">Source observations</div>
      <div class="detail-value">${Number(item.observation_count || 0).toLocaleString()} preserved observation(s)</div>
    </div>
  `;

  if (focusMap && item.location) {
    state.map.flyTo([item.location.latitude, item.location.longitude], Math.max(state.map.getZoom(), 16), {
      duration: .5,
    });
    state.markers.get(item.id)?.openPopup();
  }
  renderMarkers();
  renderList();
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
  el("reset-time").addEventListener("click", () => {
    timelineEl.value = "0";
    applyFilters();
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
    configureMediaTypes();
    statusEl.textContent = `${state.payload.item_count.toLocaleString()} reconstruction-oriented records · read model v${state.payload.schema_version}`;
    applyFilters();
  } catch (error) {
    statusEl.textContent = "Explorer data could not be loaded.";
    el("record-list").innerHTML = `
      <p class="fine-print">
        Generate <code>data/explorer.json</code> with the archive-export-explorer command,
        then serve this directory over HTTP.
      </p>`;
    console.error(error);
  }
}

load();
