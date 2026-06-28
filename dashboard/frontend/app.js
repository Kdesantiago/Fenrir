/* Fenrir Mission Control — vanilla SPA.
   Endpoints (all same-origin):
     GET  /api/board
     POST /api/epics  POST /api/features  POST /api/stories  POST /api/tasks
     PATCH /api/{kind}/{id}/status   PATCH /api/{kind}/{id}/assign
     POST  /api/{kind}/{id}/worklog   DELETE /api/{kind}/{id}
     GET  /api/telemetry/summary | by-model | by-skill | by-day | agents
*/
"use strict";

/* ------------------------------------------------------------------ helpers */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (tag, props = {}, kids = []) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of [].concat(kids)) if (c != null) n.append(c.nodeType ? c : document.createTextNode(c));
  return n;
};

const fmtInt = (n) => (n ?? 0).toLocaleString("en-US");
const fmtTok = (n) => {
  n = n ?? 0;
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
};
const fmtUsd = (n) => "$" + (n ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtUsd4 = (n) => "$" + (n ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const esc = (s) => (s ?? "").toString().replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// milliseconds -> human ("1.2s", "3m 4s", "—" when unknown)
const fmtDur = (ms) => {
  ms = ms ?? 0;
  if (!ms) return "—";
  if (ms < 1000) return ms + "ms";
  const s = ms / 1000;
  if (s < 60) return s.toFixed(1) + "s";
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s % 60)}s`;
};
// ISO timestamp -> compact local "Jun 27, 21:21" (returns "—" when missing/invalid)
const fmtWhen = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
};

const PALETTE = ["#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#f87171", "#c084fc", "#f472b6", "#38bdf8", "#a3e635", "#fb923c"];
const colorFor = (str) => {
  let h = 0;
  for (let i = 0; i < (str || "").length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
};
const initials = (name) => (name || "?").trim().split(/[\s_-]+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "?";

/* ------------------------------------------------------------------ toasts */
function toast(msg, kind = "") {
  const t = el("div", { class: "toast " + kind, role: "status", text: msg });
  $("#toast-region").append(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(() => t.remove(), 300); }, 3200);
}

/* ------------------------------------------------------------------ API */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  setConn(res.ok);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail || detail; } catch {}
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}
const apiGet  = (p) => api(p);
const apiPost = (p, body) => api(p, { method: "POST", body: JSON.stringify(body) });
const apiPatch = (p, body) => api(p, { method: "PATCH", body: JSON.stringify(body) });
const apiDel  = (p) => api(p, { method: "DELETE" });

function setConn(ok) {
  const dot = $("#conn-status");
  dot.classList.toggle("ok", !!ok);
  dot.classList.toggle("err", !ok);
  dot.title = ok ? "Connected" : "Connection error";
}

/* ------------------------------------------------------------------ state */
const charts = {};
let board = null;
let telemetry = null;
let bydayMetric = "tokens";
let selectedProject = "all"; // "all" | "<slug>"; populated from /api/projects on boot
const filters = { epic: "", assignee: "" };
let costs = null;            // cached /api/board/costs for the selected project's board
let subagentSortByCost = true; // run table sort: true = cost desc, false = chronological (newest first)
let traceUs = "";           // cost-trace US filter ("" = all)

// readable label from a project slug, e.g. "-Users-kdesantiago-Desktop-Fenrir" -> "Fenrir"
const projectLabel = (slug) => {
  if (!slug) return "Unknown";
  const parts = slug.split("-").filter(Boolean);
  return parts[parts.length - 1] || slug;
};
// build "?project=<selected>" for telemetry endpoints
const projParam = () => "?project=" + encodeURIComponent(selectedProject);

const COLUMNS = [
  { id: "backlog", label: "Backlog" },
  { id: "todo", label: "To Do" },
  { id: "in_progress", label: "In Progress" },
  { id: "review", label: "Review" },
  { id: "done", label: "Done" },
];

/* ------------------------------------------------------------------ nav */
function initNav() {
  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
    btn.addEventListener("keydown", (e) => {
      const items = $$(".nav-item");
      const i = items.indexOf(btn);
      if (e.key === "ArrowDown" || e.key === "ArrowRight") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
      if (e.key === "ArrowUp"   || e.key === "ArrowLeft")  { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    });
  });
}
function switchView(view) {
  $$(".nav-item").forEach((b) => {
    const on = b.dataset.view === view;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  $$(".view").forEach((v) => {
    const on = v.id === "view-" + view;
    v.classList.toggle("is-active", on);
    v.hidden = !on;
  });
  // the cost trace is fetched lazily the first time (and refreshed on each visit)
  if (view === "trace") loadTrace();
  // charts need a resize nudge when revealed
  requestAnimationFrame(() => Object.values(charts).forEach((c) => c && c.resize()));
}

/* ------------------------------------------------------------------ states */
function stateMsg(target, { icon, title, msg, error }) {
  target.innerHTML = "";
  target.append(el("div", { class: "state" + (error ? " state-error" : "") }, [
    el("div", { html: icon || "" }),
    el("h3", { text: title || "" }),
    el("div", { text: msg || "" }),
  ]));
}
const ICON_EMPTY = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7h18M3 12h18M3 17h18"/></svg>';
const ICON_ERR   = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>';

/* ------------------------------------------------------------------ OVERVIEW */
async function loadOverview() {
  const body = $("#overview-body");
  $("#kpi-grid").innerHTML = Array(5).fill('<div class="skel skel-kpi"></div>').join("");
  try {
    const q = projParam();
    const [summary, byday, bymodel, agents] = await Promise.all([
      apiGet("/api/telemetry/summary" + q),
      apiGet("/api/telemetry/by-day" + q),
      apiGet("/api/telemetry/by-model" + q),
      apiGet("/api/telemetry/agents" + q),
    ]);
    telemetry = { summary, byday, bymodel, agents };
    renderKPIs(summary);
    renderScope(summary.scope);
    $("#overview-range").textContent =
      summary.first_day ? `${summary.first_day} → ${summary.last_day} · ${fmtInt(summary.sessions)} sessions` : "No telemetry recorded yet";
    renderByDay(byday);
    renderByModel(bymodel);
    renderSource(agents.by_source);
  } catch (e) {
    stateMsg(body, { icon: ICON_ERR, title: "Couldn’t load telemetry", msg: e.message, error: true });
  }
}

function renderKPIs(s) {
  const cards = [
    { label: "Total cost", value: fmtUsd(s.cost_usd), sub: `${fmtInt(s.calls)} model calls` },
    { label: "Total tokens", value: fmtTok(s.total_tokens), sub: `${fmtTok(s.cache_tokens)} cached` },
    { label: "Calls", value: fmtInt(s.calls), sub: `${(s.models || []).length} models` },
    { label: "Sessions", value: fmtInt(s.sessions), sub: `${fmtTok(s.input_tokens)} in · ${fmtTok(s.output_tokens)} out` },
    { label: "Date range", value: s.first_day ? `${s.last_day || ""}` : "—", sub: s.first_day ? `since ${s.first_day}` : "no data" },
  ];
  $("#kpi-grid").innerHTML = "";
  cards.forEach((c) =>
    $("#kpi-grid").append(el("div", { class: "kpi" }, [
      el("div", { class: "kpi-label", text: c.label }),
      el("div", { class: "kpi-value", text: c.value }),
      el("div", { class: "kpi-sub", text: c.sub }),
    ]))
  );
}

function renderScope(scope) {
  const cap = $("#scope-caption");
  if (!scope) { cap.hidden = true; cap.textContent = ""; return; }
  const label = scope === "all projects" ? "all projects" : projectLabel(scope);
  cap.hidden = false;
  cap.innerHTML = "";
  cap.append("Showing telemetry for ", el("b", { text: label }));
}

const gridColor = "rgba(255,255,255,.06)";
const tickColor = "#64708a";
function applyChartDefaults() {
  Chart.defaults.color = tickColor;
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 11;
}

function destroy(key) { if (charts[key]) { charts[key].destroy(); charts[key] = null; } }

// A chart's empty-state used to overwrite its wrap, deleting the <canvas>; the next render
// then hit `null.getContext`. These keep the wrap (anchored by data-canvas) the source of
// truth: chartEmpty() shows a message, freshCanvas() always hands back a clean canvas.
function chartWrap(id) { return document.querySelector(`.chart-wrap[data-canvas="${id}"]`); }
function chartEmpty(id, opts) { const w = chartWrap(id); if (w) stateMsg(w, opts); }
function freshCanvas(id) {
  const w = chartWrap(id);
  if (!w) return null;
  w.innerHTML = "";
  return w.appendChild(el("canvas", { id, role: "img", "aria-label": w.dataset.label || id }));
}

function renderByDay(rows) {
  destroy("byday");
  if (!rows.length) { chartEmpty("chart-byday", { icon: ICON_EMPTY, title: "No daily data", msg: "Usage will appear here." }); return; }
  const ctx = freshCanvas("chart-byday");
  if (!ctx) return;
  const labels = rows.map((r) => r.day);
  const data = rows.map((r) => r[bydayMetric]);
  const isCost = bydayMetric === "cost_usd";
  const grad = ctx.getContext("2d").createLinearGradient(0, 0, 0, 280);
  grad.addColorStop(0, "rgba(99,102,241,.35)");
  grad.addColorStop(1, "rgba(99,102,241,0)");
  charts.byday = new Chart(ctx, {
    type: "line",
    data: { labels, datasets: [{
      label: isCost ? "Cost (USD)" : "Tokens",
      data, borderColor: "#818cf8", backgroundColor: grad, fill: true,
      // few points (esp. a single day) need a visible dot — a 1-point line draws no segment
      tension: .35, borderWidth: 2, pointRadius: rows.length <= 2 ? 4 : 0,
      pointBackgroundColor: "#818cf8", pointHoverRadius: 5, pointHoverBackgroundColor: "#818cf8",
    }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => isCost ? fmtUsd4(c.parsed.y) : fmtInt(c.parsed.y) + " tokens" } } },
      scales: {
        x: { grid: { color: gridColor }, ticks: { maxRotation: 0, autoSkipPadding: 18 } },
        y: { grid: { color: gridColor }, ticks: { callback: (v) => isCost ? "$" + v : fmtTok(v) } },
      },
    },
  });
}

function renderByModel(rows) {
  destroy("bymodel");
  if (!rows.length) { chartEmpty("chart-bymodel", { icon: ICON_EMPTY, title: "No model data", msg: "" }); return; }
  const ctx = freshCanvas("chart-bymodel");
  if (!ctx) return;
  charts.bymodel = new Chart(ctx, {
    type: "doughnut",
    data: { labels: rows.map((r) => shortModel(r.key)), datasets: [{
      data: rows.map((r) => r.cost_usd), backgroundColor: rows.map((r) => colorFor(r.key)),
      borderColor: "#121826", borderWidth: 2, hoverOffset: 6,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, padding: 12 } },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${fmtUsd4(c.parsed)}` } } },
    },
  });
}

function renderSource(rows) {
  destroy("source");
  if (!rows.length) { chartEmpty("chart-source", { icon: ICON_EMPTY, title: "No agent data", msg: "" }); return; }
  const ctx = freshCanvas("chart-source");
  if (!ctx) return;
  charts.source = new Chart(ctx, {
    type: "doughnut",
    data: { labels: rows.map((r) => r.key === "main" ? "Main thread" : "Subagent"), datasets: [{
      data: rows.map((r) => r.cost_usd),
      backgroundColor: rows.map((r) => r.key === "main" ? "#6366f1" : "#22d3ee"),
      borderColor: "#121826", borderWidth: 2, hoverOffset: 6,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, padding: 12 } },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${fmtUsd4(c.parsed)}` } } },
    },
  });
}

const shortModel = (m) => (m || "").replace(/^.*?(claude|gpt|gemini)/i, "$1").replace(/-\d{8}$/, "").slice(0, 28) || m;

/* ------------------------------------------------------------------ AGENTS */
async function loadAgents() {
  const body = $("#agents-body");
  try {
    const q = projParam();
    const [bymodel, byskill, agents, subagents] = await Promise.all([
      apiGet("/api/telemetry/by-model" + q),
      apiGet("/api/telemetry/by-skill" + q),
      apiGet("/api/telemetry/agents" + q),
      apiGet("/api/telemetry/subagents" + q),
    ]);
    fillTable("#tbl-model", bymodel, (r) => shortModel(r.key));
    fillTable("#tbl-skill", byskill, (r) => r.key);
    fillTable("#tbl-source", agents.by_source, (r) => r.key === "main" ? "Main thread" : "Subagent");
    renderSourceBar(agents.by_source);
    renderSubagents(subagents);
  } catch (e) {
    stateMsg(body, { icon: ICON_ERR, title: "Couldn’t load agent data", msg: e.message, error: true });
  }
}

/* ------------------------------------------------------------------ SUBAGENTS */
let subagentRuns = []; // last-fetched runs, kept for client-side re-sort

function renderSubagents(data) {
  subagentRuns = data.runs || [];
  renderSubagentRecon(data);
  renderSubagentTypeTable(data.by_type || []);
  renderSubagentTypeBar(data.by_type || []);
  renderSubagentRuns();
}

// the reconciliation line: attributed X / total Y (Z unattributed)
function renderSubagentRecon(d) {
  const node = $("#subagent-recon");
  node.innerHTML = "";
  const total = d.subagent_total_tokens ?? 0;
  const attr = d.attributed_tokens ?? 0;
  const unattr = d.unattributed_tokens ?? 0;
  const reconciled = unattr === 0;
  node.append(
    "Attributed ",
    el("b", { text: fmtInt(attr) }),
    " / total ",
    el("b", { text: fmtInt(total) }),
    " tokens (",
    el("span", { class: reconciled ? "recon-ok" : "recon-gap", text: fmtInt(unattr) + " unattributed" }),
    ")",
  );
  node.title = `${fmtInt(attr)} attributed + ${fmtInt(unattr)} unattributed = ${fmtInt(total)} subagent tokens`;
}

function renderSubagentTypeTable(rows) {
  const tbody = $("#tbl-subagent-type tbody");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.append(el("tr", {}, el("td", { colspan: "5", class: "muted", style: "text-align:center;padding:24px", text: "No subagent runs" })));
    return;
  }
  rows.forEach((r) => {
    tbody.append(el("tr", {}, [
      el("td", { class: "k", text: r.agent_type }),
      el("td", { class: "num", text: fmtInt(r.runs) }),
      el("td", { class: "num", text: fmtTok(r.input_tokens) }),
      el("td", { class: "num", text: fmtTok(r.output_tokens) }),
      el("td", { class: "num cost", text: fmtUsd4(r.cost_usd) }),
    ]));
  });
}

function renderSubagentTypeBar(rows) {
  destroy("subagenttype");
  if (!rows.length) { chartEmpty("chart-subagent-type", { icon: ICON_EMPTY, title: "No subagent runs", msg: "" }); return; }
  const ctx = freshCanvas("chart-subagent-type");
  if (!ctx) return;
  charts.subagenttype = new Chart(ctx, {
    type: "bar",
    data: { labels: rows.map((r) => r.agent_type), datasets: [{
      label: "Cost (USD)", data: rows.map((r) => r.cost_usd),
      backgroundColor: rows.map((r) => colorFor(r.agent_type)),
      borderRadius: 6, maxBarThickness: 34,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        label: (c) => `${fmtUsd4(c.parsed.x)} · ${fmtInt(rows[c.dataIndex].runs)} runs` } } },
      scales: { x: { grid: { color: gridColor }, ticks: { callback: (v) => "$" + v } }, y: { grid: { display: false } } },
    },
  });
}

function renderSubagentRuns() {
  const tbody = $("#tbl-subagent-runs tbody");
  tbody.innerHTML = "";
  if (!subagentRuns.length) {
    tbody.append(el("tr", {}, el("td", { colspan: "8", class: "muted", style: "text-align:center;padding:24px", text: "No subagent runs recorded" })));
    return;
  }
  const rows = [...subagentRuns].sort((a, b) =>
    subagentSortByCost ? (b.cost_usd - a.cost_usd) : ((b.when || "").localeCompare(a.when || "")));
  rows.forEach((r) => {
    const ok = r.status === "completed" && r.attributed;
    tbody.append(el("tr", { title: r.description || "" }, [
      el("td", { class: "k", text: r.agent_type }),
      el("td", {}, el("span", { class: "when", text: fmtWhen(r.when) })),
      el("td", { class: "k", text: shortModel(r.model) || "—" }),
      el("td", { class: "num", text: fmtTok(r.input_tokens) }),
      el("td", { class: "num", text: fmtTok(r.output_tokens) }),
      el("td", { class: "num cost", text: fmtUsd4(r.cost_usd) }),
      el("td", { class: "num", text: fmtDur(r.duration_ms) }),
      el("td", {}, el("span", { class: "pill " + (ok ? "pill-ok" : "pill-warn"), text: r.status })),
    ]));
  });
}

function fillTable(sel, rows, labelFn) {
  const tbody = $(sel + " tbody");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.append(el("tr", {}, el("td", { colspan: "5", class: "muted", style: "text-align:center;padding:24px", text: "No data" })));
    return;
  }
  rows.forEach((r) => {
    tbody.append(el("tr", {}, [
      el("td", { class: "k", text: labelFn(r) }),
      el("td", { class: "num", text: fmtInt(r.calls) }),
      el("td", { class: "num", text: fmtTok(r.input_tokens) }),
      el("td", { class: "num", text: fmtTok(r.output_tokens) }),
      el("td", { class: "num cost", text: fmtUsd4(r.cost_usd) }),
    ]));
  });
}

function renderSourceBar(rows) {
  destroy("sourcebar");
  if (!rows.length) { chartEmpty("chart-source-bar", { icon: ICON_EMPTY, title: "No data", msg: "" }); return; }
  const ctx = freshCanvas("chart-source-bar");
  if (!ctx) return;
  charts.sourcebar = new Chart(ctx, {
    type: "bar",
    data: { labels: rows.map((r) => r.key === "main" ? "Main thread" : "Subagent"), datasets: [{
      label: "Cost (USD)", data: rows.map((r) => r.cost_usd),
      backgroundColor: rows.map((r) => r.key === "main" ? "#6366f1" : "#22d3ee"),
      borderRadius: 6, maxBarThickness: 60,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmtUsd4(c.parsed.x) } } },
      scales: { x: { grid: { color: gridColor }, ticks: { callback: (v) => "$" + v } }, y: { grid: { display: false } } },
    },
  });
}

/* ------------------------------------------------------------------ PROJECTS */
async function loadProjects() {
  const sel = $("#project-select");
  try {
    const { active, projects } = await apiGet("/api/projects");
    sel.innerHTML = "";
    sel.append(el("option", { value: "all", text: "All projects" }));
    (projects || []).forEach((slug) =>
      sel.append(el("option", { value: slug, text: projectLabel(slug), title: slug }))
    );
    // pre-select the backend's active project; fall back to "all"
    selectedProject = active && (projects || []).includes(active) ? active : "all";
    sel.value = selectedProject;
  } catch {
    // leave the static "All projects" option in place; scope to all
    selectedProject = "all";
    sel.value = "all";
  }
}

// project switch: re-fetch & re-render telemetry views only (board is project-independent)
function onProjectChange() {
  selectedProject = $("#project-select").value || "all";
  loadOverview();
  loadAgents();
  loadBoard();   // the kanban is scoped to the selected project too
  loadTrace();   // trace is board-derived → re-scope it as well
}

/* ------------------------------------------------------------------ KANBAN */
async function loadBoard() {
  const body = $("#kanban-body");
  try {
    board = await apiGet("/api/board" + projParam());
    costs = null; // board changed: drop stale cost cache, refetch lazily
    try { await ensureCosts(); } catch { /* badges stay hidden if costs unavailable */ }
    populateFilters();
    populateTraceFilter();
    renderKanban();
  } catch (e) {
    stateMsg(body, { icon: ICON_ERR, title: "Couldn’t load board", msg: e.message, error: true });
  }
}

const featureById = (id) => board.features.find((f) => f.id === id);
const epicById = (id) => board.epics.find((e) => e.id === id);
const epicOfStory = (story) => { const f = featureById(story.feature_id); return f ? epicById(f.epic_id) : null; };

/* ---- board-derived costs (per selected project; cached, refreshed on mutation) ---- */
async function ensureCosts() {
  if (costs) return costs;
  costs = await apiGet("/api/board/costs" + projParam());
  return costs;
}
// invalidate + re-render anything cost-derived after a board mutation
async function refreshCosts() {
  costs = null;
  try { await ensureCosts(); } catch { /* badges simply stay hidden */ }
  if (board) renderKanban();
}

function populateFilters() {
  const epicSel = $("#filter-epic");
  const asgSel = $("#filter-assignee");
  epicSel.innerHTML = '<option value="">All epics</option>';
  board.epics.forEach((ep) => epicSel.append(el("option", { value: ep.id, text: ep.title })));
  epicSel.value = filters.epic;

  const assignees = [...new Set(board.stories.map((s) => s.assignee).filter(Boolean))].sort();
  asgSel.innerHTML = '<option value="">All assignees</option>';
  assignees.forEach((a) => asgSel.append(el("option", { value: a, text: a })));
  asgSel.value = filters.assignee;
}

function visibleStories() {
  return board.stories.filter((s) => {
    if (filters.assignee && s.assignee !== filters.assignee) return false;
    if (filters.epic) { const ep = epicOfStory(s); if (!ep || ep.id !== filters.epic) return false; }
    return true;
  });
}

function renderKanban() {
  // empty state may have replaced the grid; rebuild the host every render
  $("#kanban-body").innerHTML = '<div class="kanban" id="kanban-cols"></div>';

  if (!board.stories.length) {
    stateMsg($("#kanban-body"), {
      icon: ICON_EMPTY, title: "No stories yet",
      msg: "Add an epic, a feature, then a story to start planning.",
    });
    return;
  }
  const grid = $("#kanban-cols");

  const stories = visibleStories();
  COLUMNS.forEach((col) => {
    const inCol = stories.filter((s) => s.status === col.id);
    const list = el("div", { class: "klist", "data-status": col.id });
    inCol.forEach((s) => list.append(storyCard(s)));
    if (!inCol.length) list.append(el("div", { class: "muted", style: "padding:8px;font-size:12px;text-align:center", text: "—" }));

    grid.append(el("section", { class: "kcol", "data-status": col.id }, [
      el("div", { class: "kcol-head" }, [
        el("h3", {}, [el("span", { class: "kcol-dot" }), col.label]),
        el("span", { class: "kcount", text: String(inCol.length) }),
      ]),
      list,
    ]));
  });

  initSortable();
}

function storyCard(s) {
  const ep = epicOfStory(s);
  const accent = ep ? ep.color : "#6366f1";
  const card = el("article", {
    class: "card", "data-id": s.id, "data-status": s.status, tabindex: "0",
    role: "button", "aria-label": `Story ${s.title}. Open details.`,
    style: `border-left-color:${accent}`,
  });
  card.append(
    el("div", { class: "card-head" }, [
      el("span", { class: "card-id", text: s.id }),
      el("button", {
        class: "btn btn-danger card-del", "aria-label": "Delete story " + s.title, title: "Delete",
        html: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>',
        onclick: (e) => { e.stopPropagation(); deleteStory(s); },
      }),
    ]),
    el("div", { class: "card-title", text: s.title }),
  );

  const meta = el("div", { class: "card-meta" });
  // Epic chip only. Epic/Feature cost ROLLUPS live in the story modal (labeled), not as
  // unlabeled chips on every card (that read as the card's own price).
  if (ep) meta.append(el("span", { class: "chip chip-epic", style: `color:${ep.color}`, text: ep.title }));
  if (s.points) meta.append(el("span", { class: "chip chip-points", text: s.points + " pts" }));
  if (s.assignee) meta.append(el("span", { class: "chip" }, [
    el("span", { class: "avatar", style: `background:${colorFor(s.assignee)}`, text: initials(s.assignee) }),
    s.assignee,
  ]));
  card.append(meta);

  const wl = s.work_log || [];
  if (wl.length) {
    const tok = wl.reduce((a, w) => a + (w.input_tokens || 0) + (w.output_tokens || 0), 0);
    const cost = wl.reduce((a, w) => a + (w.cost_usd || 0), 0);
    card.append(el("div", { class: "card-worklog" }, [
      el("span", { class: "muted", text: "US cost" }),
      el("span", { class: "cost", style: "color:var(--good)", text: fmtUsd4(cost) }),
      el("span", { class: "muted", text: `· ${fmtTok(tok)} tok` }),
    ]));
  }

  const open = () => openStoryDetail(s);
  card.addEventListener("click", open);
  card.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); open(); } });
  return card;
}

let sortables = [];
function initSortable() {
  sortables.forEach((s) => s.destroy());
  sortables = [];
  if (typeof Sortable === "undefined") return;
  $$(".klist").forEach((list) => {
    sortables.push(new Sortable(list, {
      group: "stories", animation: 150, ghostClass: "sortable-ghost", dragClass: "sortable-drag",
      onStart: () => $$(".klist").forEach((l) => l.classList.add("drop-active")),
      onEnd: async (evt) => {
        $$(".klist").forEach((l) => l.classList.remove("drop-active"));
        const newStatus = evt.to.getAttribute("data-status");
        const oldStatus = evt.from.getAttribute("data-status");
        const id = evt.item.getAttribute("data-id");
        if (newStatus === oldStatus) return;
        try {
          await apiPatch(`/api/story/${id}/status` + projParam(), { status: newStatus });
          const st = board.stories.find((x) => x.id === id);
          if (st) st.status = newStatus;
          toast(`Moved to ${COLUMNS.find((c) => c.id === newStatus).label}`, "ok");
          renderKanban();
        } catch (e) {
          toast("Update failed: " + e.message, "err");
          renderKanban();
        }
      },
    }));
  });
}

async function deleteStory(s) {
  if (!confirm(`Delete story “${s.title}”? This cannot be undone.`)) return;
  try {
    await apiDel(`/api/story/${s.id}` + projParam());
    board.stories = board.stories.filter((x) => x.id !== s.id);
    toast("Story deleted", "ok");
    populateFilters();
    renderKanban();
    refreshCosts();
  } catch (e) {
    toast("Delete failed: " + e.message, "err");
  }
}

/* ------------------------------------------------------------------ MODAL */
let lastFocus = null;
function openModal(title, contentNode) {
  lastFocus = document.activeElement;
  $("#modal-title").textContent = title;
  const bodyEl = $("#modal-body");
  bodyEl.innerHTML = "";
  bodyEl.append(contentNode);
  $("#modal-backdrop").hidden = false;
  const focusable = $("#modal").querySelector("input,select,textarea,button");
  if (focusable) focusable.focus();
}
function closeModal() {
  $("#modal-backdrop").hidden = true;
  $("#modal-body").innerHTML = "";
  if (lastFocus) lastFocus.focus();
}
$("#modal-close").addEventListener("click", closeModal);
$("#modal-backdrop").addEventListener("click", (e) => { if (e.target.id === "modal-backdrop") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal-backdrop").hidden) closeModal(); });
// focus trap
$("#modal").addEventListener("keydown", (e) => {
  if (e.key !== "Tab") return;
  const items = $$('#modal a,#modal button,#modal input,#modal select,#modal textarea').filter((n) => !n.disabled && n.offsetParent !== null);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

/* --- story detail --- */
function openStoryDetail(s) {
  const ep = epicOfStory(s);
  const feat = featureById(s.feature_id);
  const wrap = el("div");

  if (s.as_a || s.i_want || s.so_that) {
    wrap.append(el("div", { class: "detail-section" }, [
      el("h4", { text: "User story" }),
      el("div", { class: "story-statement", html:
        `<b>As a</b> ${esc(s.as_a) || "…"} <b>I want</b> ${esc(s.i_want) || "…"} <b>so that</b> ${esc(s.so_that) || "…"}` }),
    ]));
  }

  const metaRows = el("div", { class: "detail-section" }, [
    el("h4", { text: "Details" }),
    el("div", { class: "story-statement", html:
      `<div>Epic: <b style="color:${ep ? ep.color : "#888"}">${esc(ep ? ep.title : "—")}</b></div>` +
      `<div>Feature: ${esc(feat ? feat.title : "—")}</div>` +
      `<div>Status: ${esc(s.status)} · Points: ${s.points || 0}</div>` },
    ),
  ]);
  wrap.append(metaRows);

  // assignee editor
  const asgInput = el("input", { type: "text", value: s.assignee || "", placeholder: "agent name", id: "asg-input" });
  wrap.append(el("div", { class: "detail-section" }, [
    el("h4", { text: "Assignee" }),
    el("div", { style: "display:flex;gap:8px" }, [
      asgInput,
      el("button", { class: "btn btn-sm", text: "Save", onclick: async () => {
        try {
          await apiPatch(`/api/story/${s.id}/assign` + projParam(), { assignee: asgInput.value.trim() });
          s.assignee = asgInput.value.trim();
          toast("Assignee updated", "ok"); populateFilters(); renderKanban();
        } catch (e) { toast("Failed: " + e.message, "err"); }
      } }),
    ]),
  ]));

  if ((s.acceptance_criteria || []).length) {
    wrap.append(el("div", { class: "detail-section" }, [
      el("h4", { text: "Acceptance criteria" }),
      el("ul", { class: "ac-list" }, s.acceptance_criteria.map((c) => el("li", { text: c }))),
    ]));
  }

  // tasks under story
  const tasks = board.tasks.filter((t) => t.story_id === s.id);
  const taskSec = el("div", { class: "detail-section" }, [el("h4", { text: `Tasks (${tasks.length})` })]);
  tasks.forEach((t) => taskSec.append(el("div", { class: "story-statement", style: "margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;align-items:center" }, [
    el("span", { text: `${t.title} · ${t.status}${t.assignee ? " · " + t.assignee : ""}` }),
    el("button", { class: "btn btn-danger btn-sm", text: "✕", "aria-label": "Delete task", onclick: async () => {
      try { await apiDel(`/api/task/${t.id}` + projParam()); board.tasks = board.tasks.filter((x) => x.id !== t.id); costs = null; toast("Task deleted", "ok"); openStoryDetail(s); }
      catch (e) { toast("Failed: " + e.message, "err"); }
    } }),
  ])));
  const taskInput = el("input", { type: "text", placeholder: "New task title", "aria-label": "New task title" });
  taskSec.append(el("div", { style: "display:flex;gap:8px;margin-top:8px" }, [
    taskInput,
    el("button", { class: "btn btn-sm", text: "+ Task", onclick: async () => {
      if (!taskInput.value.trim()) return;
      try {
        const t = await apiPost("/api/tasks" + projParam(), { story_id: s.id, title: taskInput.value.trim(), assignee: "" });
        board.tasks.push(t); costs = null; toast("Task added", "ok"); openStoryDetail(s);
      } catch (e) { toast("Failed: " + e.message, "err"); }
    } }),
  ]));
  wrap.append(taskSec);

  // per-US cost (board-derived; fetched once and cached, refreshed after mutations)
  const costSec = el("div", { class: "detail-section" }, [el("h4", { text: "Cost" })]);
  const costBody = el("div");
  costBody.append(el("div", { class: "cost-empty", text: "Loading cost…" }));
  costSec.append(costBody);
  wrap.append(costSec);
  ensureCosts()
    .then((c) => {
      renderStoryCost(costBody, c && c.stories ? c.stories[s.id] : null);
      // labeled Epic/Feature rollups (what the old card badges hinted at, now explicit)
      const ep = epicOfStory(s), feat = featureById(s.feature_id);
      const fc = feat && c && c.features && c.features[feat.id];
      const ec = ep && c && c.epics && c.epics[ep.id];
      const roll = el("div", { class: "cost-rollup" });
      const row = (label, r) => el("div", { class: "rollup-row" }, [
        el("span", { class: "muted", text: label }),
        el("span", { class: "cost", text: fmtUsd(r.cost_usd) }),
      ]);
      if (fc && fc.cost_usd) roll.append(row(`Feature · ${feat.title}`, fc));
      if (ec && ec.cost_usd) roll.append(row(`Epic · ${ep.title}`, ec));
      if (roll.children.length) costBody.append(roll);
    })
    .catch(() => { costBody.innerHTML = ""; costBody.append(el("div", { class: "cost-empty", text: "Cost unavailable" })); });

  // work log
  const wl = s.work_log || [];
  if (wl.length) {
    const table = el("table", { class: "wl-table" }, [
      el("thead", {}, el("tr", {}, [
        el("th", { text: "Agent" }), el("th", { class: "num", text: "In" }),
        el("th", { class: "num", text: "Out" }), el("th", { class: "num", text: "Cost" }),
      ])),
      el("tbody", {}, wl.map((w) => el("tr", {}, [
        el("td", { text: w.agent || "—" }),
        el("td", { class: "num", text: fmtTok(w.input_tokens) }),
        el("td", { class: "num", text: fmtTok(w.output_tokens) }),
        el("td", { class: "num", text: fmtUsd4(w.cost_usd) }),
      ]))),
    ]);
    wrap.append(el("div", { class: "detail-section" }, [el("h4", { text: "Work log" }), table]));
  }

  // delete
  wrap.append(el("div", { class: "form-actions" }, [
    el("button", { class: "btn btn-danger", text: "Delete story", onclick: () => { closeModal(); deleteStory(s); } }),
    el("button", { class: "btn btn-primary", text: "Close", onclick: closeModal }),
  ]));

  openModal(`${s.id} · ${s.title}`, wrap);
}

// render a story's cost rollup (total + per-agent breakdown) into a container
function renderStoryCost(target, r) {
  target.innerHTML = "";
  if (!r || !r.cost_usd) {
    target.append(el("div", { class: "cost-empty", text: "No cost recorded for this story yet." }));
    return;
  }
  target.append(el("div", { class: "cost-total" }, [
    el("span", { class: "big", text: fmtUsd(r.cost_usd) }),
    el("span", { class: "sub", text: `${fmtTok(r.input_tokens)} in · ${fmtTok(r.output_tokens)} out` }),
  ]));
  if ((r.by_agent || []).length) {
    target.append(el("table", { class: "wl-table" }, [
      el("thead", {}, el("tr", {}, [
        el("th", { text: "Agent" }), el("th", { class: "num", text: "In" }),
        el("th", { class: "num", text: "Out" }), el("th", { class: "num", text: "Cost" }),
      ])),
      el("tbody", {}, r.by_agent.map((a) => el("tr", {}, [
        el("td", { text: a.agent || "—" }),
        el("td", { class: "num", text: fmtTok(a.input_tokens) }),
        el("td", { class: "num", text: fmtTok(a.output_tokens) }),
        el("td", { class: "num", text: fmtUsd4(a.cost_usd) }),
      ]))),
    ]));
  }
}

/* ------------------------------------------------------------------ COST TRACE */
function populateTraceFilter() {
  const sel = $("#trace-us");
  if (!sel || !board) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">All stories</option>';
  board.stories.forEach((s) => sel.append(el("option", { value: s.id, text: `${s.id} · ${s.title}` })));
  // keep the prior selection if the story still exists
  sel.value = board.stories.some((s) => s.id === prev) ? prev : "";
  traceUs = sel.value;
}

async function loadTrace() {
  const tbody = $("#tbl-trace tbody");
  const tfoot = $("#tbl-trace tfoot");
  tbody.innerHTML = "";
  tfoot.innerHTML = "";
  tbody.append(el("tr", {}, el("td", { colspan: "7", class: "muted", style: "text-align:center;padding:24px", text: "Loading…" })));
  try {
    const parts = [];
    if (traceUs) parts.push("us=" + encodeURIComponent(traceUs));
    const pq = projParam();          // "?project=<sel>" or ""
    if (pq) parts.push(pq.slice(1));
    const rows = await apiGet("/api/trace" + (parts.length ? "?" + parts.join("&") : ""));
    renderTrace(rows);
  } catch (e) {
    tbody.innerHTML = "";
    stateMsg($("#trace-body"), { icon: ICON_ERR, title: "Couldn’t load cost trace", msg: e.message, error: true });
  }
}

function renderTrace(rows) {
  const tbody = $("#tbl-trace tbody");
  const tfoot = $("#tbl-trace tfoot");
  tbody.innerHTML = "";
  tfoot.innerHTML = "";
  if (!rows.length) {
    tbody.append(el("tr", {}, el("td", { colspan: "7", class: "muted", style: "text-align:center;padding:24px", text: "No work-log entries yet." })));
    return;
  }
  let tin = 0, tout = 0, tcost = 0;
  rows.forEach((r) => {
    tin += r.input_tokens || 0;
    tout += r.output_tokens || 0;
    tcost += r.cost_usd || 0;
    const agent = r.subagent_type || r.agent || "—";
    tbody.append(el("tr", { title: r.note || "" }, [
      el("td", {}, el("span", { class: "when", text: fmtWhen(r.at) })),
      el("td", {}, [
        el("span", { class: "k", style: "color:var(--txt-3)", text: r.us_id + " " }),
        el("span", { text: r.title || "" }),
      ]),
      el("td", { class: "k", text: agent }),
      el("td", { class: "num", text: fmtTok(r.input_tokens) }),
      el("td", { class: "num", text: fmtTok(r.output_tokens) }),
      el("td", { class: "num cost", text: fmtUsd4(r.cost_usd) }),
      el("td", { text: r.source || (r.kind === "task" ? "task" : "story") }),
    ]));
  });
  tfoot.append(el("tr", {}, [
    el("td", { text: `${rows.length} ${rows.length === 1 ? "entry" : "entries"}` }),
    el("td", { text: "" }),
    el("td", { text: "Total" }),
    el("td", { class: "num", text: fmtTok(tin) }),
    el("td", { class: "num", text: fmtTok(tout) }),
    el("td", { class: "num cost", text: fmtUsd4(tcost) }),
    el("td", { text: "" }),
  ]));
}

/* --- add forms --- */
function formRow(labelText, field) {
  const id = "f-" + Math.random().toString(36).slice(2, 8);
  field.id = id;
  return el("div", { class: "form-row" }, [el("label", { for: id, text: labelText }), field]);
}

function openAddEpic() {
  const title = el("input", { type: "text", required: "true", placeholder: "Epic title" });
  const desc = el("textarea", { placeholder: "Description (optional)" });
  const color = el("input", { type: "color", value: "#6366f1", style: "height:38px;padding:3px" });
  const form = el("form", {}, [
    formRow("Title", title),
    formRow("Description", desc),
    formRow("Color", color),
    el("div", { class: "form-actions" }, [
      el("button", { type: "button", class: "btn", text: "Cancel", onclick: closeModal }),
      el("button", { type: "submit", class: "btn btn-primary", text: "Create epic" }),
    ]),
  ]);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!title.value.trim()) return;
    try {
      await apiPost("/api/epics" + projParam(), { title: title.value.trim(), description: desc.value.trim(), color: color.value });
      toast("Epic created", "ok"); closeModal(); await loadBoard();
    } catch (err) { toast("Failed: " + err.message, "err"); }
  });
  openModal("Add epic", form);
}

function openAddFeature() {
  if (!board.epics.length) { toast("Create an epic first", "err"); return; }
  const epic = el("select", {}, board.epics.map((ep) => el("option", { value: ep.id, text: ep.title })));
  const title = el("input", { type: "text", required: "true", placeholder: "Feature title" });
  const desc = el("textarea", { placeholder: "Description (optional)" });
  const form = el("form", {}, [
    formRow("Epic", epic),
    formRow("Title", title),
    formRow("Description", desc),
    el("div", { class: "form-actions" }, [
      el("button", { type: "button", class: "btn", text: "Cancel", onclick: closeModal }),
      el("button", { type: "submit", class: "btn btn-primary", text: "Create feature" }),
    ]),
  ]);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!title.value.trim()) return;
    try {
      await apiPost("/api/features" + projParam(), { epic_id: epic.value, title: title.value.trim(), description: desc.value.trim() });
      toast("Feature created", "ok"); closeModal(); await loadBoard();
    } catch (err) { toast("Failed: " + err.message, "err"); }
  });
  openModal("Add feature", form);
}

function openAddStory() {
  if (!board.features.length) { toast("Create a feature first", "err"); return; }
  const feature = el("select", {}, board.features.map((f) => {
    const ep = epicById(f.epic_id);
    return el("option", { value: f.id, text: (ep ? ep.title + " / " : "") + f.title });
  }));
  const title = el("input", { type: "text", required: "true", placeholder: "Story title" });
  const assignee = el("input", { type: "text", placeholder: "agent name" });
  const points = el("input", { type: "number", min: "0", value: "0" });
  const asA = el("input", { type: "text", placeholder: "a developer" });
  const iWant = el("input", { type: "text", placeholder: "to …" });
  const soThat = el("input", { type: "text", placeholder: "so that …" });
  const ac = el("textarea", { placeholder: "One acceptance criterion per line" });
  const form = el("form", {}, [
    formRow("Feature", feature),
    formRow("Title", title),
    el("div", { class: "form-grid" }, [formRow("Assignee", assignee), formRow("Points", points)]),
    el("div", { class: "form-grid" }, [formRow("As a", asA), formRow("I want", iWant)]),
    formRow("So that", soThat),
    formRow("Acceptance criteria", ac),
    el("div", { class: "form-actions" }, [
      el("button", { type: "button", class: "btn", text: "Cancel", onclick: closeModal }),
      el("button", { type: "submit", class: "btn btn-primary", text: "Create story" }),
    ]),
  ]);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!title.value.trim()) return;
    try {
      await apiPost("/api/stories" + projParam(), {
        feature_id: feature.value, title: title.value.trim(),
        assignee: assignee.value.trim(), points: parseInt(points.value || "0", 10) || 0,
        as_a: asA.value.trim(), i_want: iWant.value.trim(), so_that: soThat.value.trim(),
        acceptance_criteria: ac.value.split("\n").map((l) => l.trim()).filter(Boolean),
      });
      toast("Story created", "ok"); closeModal(); await loadBoard();
    } catch (err) { toast("Failed: " + err.message, "err"); }
  });
  openModal("Add story", form);
}

/* ------------------------------------------------------------------ wiring */
function initControls() {
  $("#refresh-btn").addEventListener("click", () => { loadAll(); toast("Refreshed", "ok"); });

  $$('.seg-btn[data-metric]').forEach((b) => b.addEventListener("click", () => {
    $$('.seg-btn[data-metric]').forEach((x) => x.classList.toggle("is-active", x === b));
    bydayMetric = b.dataset.metric;
    if (telemetry) renderByDay(telemetry.byday);
  }));

  $("#project-select").addEventListener("change", onProjectChange);

  $("#filter-epic").addEventListener("change", (e) => { filters.epic = e.target.value; renderKanban(); });
  $("#filter-assignee").addEventListener("change", (e) => { filters.assignee = e.target.value; renderKanban(); });

  $("#subagent-sort").addEventListener("click", (e) => {
    subagentSortByCost = !subagentSortByCost;
    e.target.textContent = subagentSortByCost ? "Cost ↓" : "Recent ↓";
    e.target.setAttribute("aria-pressed", subagentSortByCost ? "true" : "false");
    renderSubagentRuns();
  });

  $("#trace-us").addEventListener("change", (e) => { traceUs = e.target.value; loadTrace(); });

  $("#add-epic-btn").addEventListener("click", openAddEpic);
  $("#add-feature-btn").addEventListener("click", openAddFeature);
  $("#add-story-btn").addEventListener("click", openAddStory);
}

async function loadAll() {
  // resolve the active project first so telemetry fetches use the right scope;
  // the board is project-independent and can load alongside.
  await Promise.all([loadProjects(), loadBoard()]);
  await Promise.all([loadOverview(), loadAgents()]);
}

function boot() {
  if (typeof Chart !== "undefined") { applyChartDefaults(); }
  initNav();
  initControls();
  loadAll();
}

// defer scripts: DOM is parsed, but CDN libs load via defer too — wait for window load
window.addEventListener("load", boot);
