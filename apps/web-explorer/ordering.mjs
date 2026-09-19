// Reference suggestions never replace a source record's time or coordinates.
export function indexOrdering(data, items, window = null) {
  const parents = new Map(items.map(item => [item.id, item]));
  const assets = new Map(data.assets.map(asset => [asset.asset_id, asset]));
  const byParent = new Map(), minutes = new Map();
  for (const asset of assets.values()) {
    if (!byParent.has(asset.parent_id)) byParent.set(asset.parent_id, []);
    byParent.get(asset.parent_id).push(asset);
    if (!parents.has(asset.parent_id) || asset.status !== "source_reported_minute") continue;
    for (const minute of asset.candidate_minutes || []) {
      if (window && (Date.parse(minute) < Date.parse(window.start) || Date.parse(minute) > Date.parse(window.end))) continue;
      if (!minutes.has(minute)) minutes.set(minute, []);
      minutes.get(minute).push(asset);
    }
  }
  return { parents, assets, byParent, minutes: new Map([...minutes].sort()) };
}

const labels = {
  source_reported_minute: "Source-reported minute · not independently verified",
  anchor_match_needs_review: "Possible NIST match · needs review",
  group_timing_only: "Collection time only · individual capture time unknown",
  range_only: "Time range · exact minute unknown",
  open_bound_only: "Before / after bound only",
  unplaced: "Capture time unknown",
  broadcast_interval_only: "Broadcast interval · not a camera capture time",
};

export function installOrdering(data, items, ui) {
  const index = indexOrdering(data, items, ui.window);
  const e = ui.escapeHtml;
  const link = (url, text) => `<a href="${e(ui.safeSourceUrl(url))}" target="_blank" rel="noopener noreferrer">${e(text)}</a>`;
  const panel = document.getElementById("ordering-panel");
  const timedCount = [...index.minutes.values()].reduce((sum, assets) => sum + assets.length, 0);
  panel.innerHTML = `<p class="fine-print">${timedCount} images with source-reported minutes within the map’s time window. All times EDT; camera-clock accuracy may be unknown.</p>
    <label class="field"><span>Jump to a reported minute</span><select id="ordering-minute"><option value="">Choose a minute…</option>${[...index.minutes].map(([minute, assets]) => `<option value="${e(minute)}">${e(ui.fmtShort(new Date(minute)))} · ${assets.length} image(s)</option>`).join("")}</select></label>
    <div id="ordering-results" class="ordering-results"></div>
    <details><summary>Proposed photo sequences</summary><p class="fine-print">Order is suggested; intervals between photos are unknown. Jev reviewed text observations. Neither NIST image match established an exact capture minute.</p><div id="ordering-sequences"></div></details>
    <details><summary>${data.anchors.length} NIST reference images</summary>${data.anchors.map(anchor => `<p class="fine-print">${link(anchor.source_url, `Figure ${anchor.figure} · ${anchor.creator}`)}<br>Reported ${e(anchor.reported_time.slice(11,19))} EDT. Per-image uncertainty not stated.</p>`).join("")}</details>`;
  const assetButton = (asset, container) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ordering-button";
    const mapped = Boolean(index.parents.get(asset.parent_id)?.location);
    button.textContent = `${asset.observation?.filename || asset.title || "Image"} · ${mapped ? "show camera record" : "open record (no mapped location)"}`;
    button.disabled = !index.parents.has(asset.parent_id);
    button.addEventListener("click", () => ui.select(asset.parent_id, asset));
    container.append(button);
  };
  document.getElementById("ordering-minute").addEventListener("change", event => {
    const minute = event.target.value;
    const results = document.getElementById("ordering-results");
    results.replaceChildren();
    if (!minute) return;
    ui.setTime(minute);
    for (const asset of index.minutes.get(minute) || []) assetButton(asset, results);
  });
  const sequences = document.getElementById("ordering-sequences");
  for (const sequence of data.sequences) {
    const list = document.createElement("ol");
    for (const id of sequence.asset_ids) {
      const asset = index.assets.get(id);
      if (!asset) continue;
      const row = document.createElement("li");
      assetButton(asset, row);
      list.append(row);
    }
    sequences.append(list);
  }
  return {
    detailHtml(parentId) {
      const assets = index.byParent.get(parentId) || [];
      if (!assets.length) return "";
      return `<div class="detail-section"><div class="detail-label">Individual media &amp; ordering</div><p class="fine-print">Map position belongs to the source camera record. Individual attachments have no separately verified location. Suggested matches do not change the map clock or source time.</p>${assets.map(asset => {
        const anchor = data.anchors.find(a => a.id === asset.anchor_id);
        const reviews = (asset.jev_reviews || []).map(review => `${review.object_id === asset.anchor_id ? "Anchor match" : "Next-image order"}: ${review.answer} (${Math.round(review.confidence * 100)}% confidence)`).join("; ");
        return `<div class="ordering-asset">${link(asset.url, asset.observation?.filename || asset.title || "Open individual media")}<p>${e(labels[asset.status] || asset.status)}</p>${asset.status === "source_reported_minute" ? `<p>${e((asset.candidate_minutes || []).map(m => ui.fmtShort(new Date(m))).join(", "))} EDT</p>` : ""}${asset.observation ? `<p>${e(asset.observation.observation)}</p>` : ""}${anchor ? `<p>${link(anchor.source_url, `NIST figure ${anchor.figure}`)} · reported ${e(anchor.reported_time.slice(11,19))} EDT; uncertainty unknown. Match remains proposed.</p>` : ""}${reviews ? `<p class="fine-print">Jev · ${e(reviews)}</p>` : ""}</div>`;
      }).join("")}</div>`;
    },
  };
}
