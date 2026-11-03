/* Hillpointe AP — web UI. Plain JS, no build step. Every number shown comes from the engine's run folders and ledger. */
"use strict";

// ------------------------------------------------------------------------------------------- helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (v) => (v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" }));
const enc = encodeURIComponent;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Read-only static build (GitHub Pages, scripts/build_site.py): every GET is a pre-exported file; nothing can be changed.
const STATIC = !!window.AP_STATIC;
const DEMO_MSG = "Read-only demo: processing, imports, deletes and rule changes run in the local app (uv run ap ui).";
const A = (p) => (STATIC ? p.slice(1) : p); // links to files: relative on the static site

function staticUrl(path) {
  const [p, q] = path.replace(/^\//, "").split("?");
  const qs = new URLSearchParams(q || "");
  if (p === "api/diff") return `api/diff/${enc(qs.get("a"))}__${enc(qs.get("b"))}.json`;
  if (p.startsWith("api/source/")) return p + ".json"; // only non-PDF/image sources are fetched as text
  return p + ".json";
}

async function api(path, opts = {}) {
  if (STATIC) {
    if (opts.method && opts.method !== "GET") throw new Error(DEMO_MSG);
    if (path.startsWith("/api/search")) {
      const q = new URLSearchParams(path.split("?")[1]).get("q").toLowerCase().trim();
      S.searchIndex ||= await (await fetch("api/search_index.json")).json();
      return q ? S.searchIndex.filter((h) => h.hay.includes(q)).slice(0, 25) : [];
    }
    const r = await fetch(staticUrl(path));
    if (!r.ok) throw new Error(r.status === 404 ? "Not available in the read-only demo." : r.statusText);
    return r.json();
  }
  const r = await fetch(path, { headers: opts.body instanceof FormData ? {} : { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* not json */ }
    throw new Error(msg);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}
const post = (p, b) => api(p, { method: "POST", body: JSON.stringify(b || {}) });
const put = (p, b) => api(p, { method: "PUT", body: JSON.stringify(b || {}) });

function toast(msg, err = false) {
  const t = $("#toast");
  t.innerHTML = `<div class="toast ${err ? "err" : ""}">${esc(msg)}</div>`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.innerHTML = ""), err ? 6000 : 3200);
}

const store = {
  get(k, d) { try { const v = localStorage.getItem("hpap." + k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem("hpap." + k, JSON.stringify(v)); } catch (_) { /* private mode */ } },
};

// ------------------------------------------------------------------------------------------- icons
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h5v-6h4v6h5V9.5"/>',
  alert: '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  db: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  book: '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  upload: '<path d="M7 17a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 18 8.5a4 4 0 0 1 0 8.5"/><path d="M12 12v9"/><path d="m8.5 15.5 3.5-3.5 3.5 3.5"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  chevdown: '<path d="m6 9 6 6 6-6"/>',
  left: '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
  download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  checkbox: '<rect x="3.5" y="3.5" width="17" height="17" rx="3.5"/><path d="m8 12 3 3 5-6"/>',
  list: '<rect x="3.5" y="4" width="6" height="6" rx="1.2"/><rect x="3.5" y="14" width="6" height="6" rx="1.2"/><path d="M13 6h8M13 9h5M13 16h8M13 19h5"/>',
  sparkle: '<path d="M12 3.5 13.9 8l4.6 1.9-4.6 1.9L12 16.4l-1.9-4.6L5.5 9.9 10.1 8z"/><path d="M18.5 15.5l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z"/>',
  compare: '<path d="M7 4v16"/><path d="M17 4v16"/><path d="m3 8 4-4 4 4"/><path d="m13 16 4 4 4-4"/>',
  shield: '<path d="M12 3 4.5 6v6c0 4.6 3.2 7.8 7.5 9 4.3-1.2 7.5-4.4 7.5-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.4-5.7L20 8.5"/><path d="M20 3.5v5h-5"/>',
  file: '<path d="M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8z"/><path d="M14 3v5h5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>',
  external: '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  receipt: '<path d="M5 3h14v18l-2.5-1.7L14 21l-2-1.7L10 21l-2.5-1.7L5 21z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  steps: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.2"/><circle cx="4.5" cy="12" r="1.2"/><circle cx="4.5" cy="18" r="1.2"/>',
  undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
};
const icon = (n, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;

// ------------------------------------------------------------------------------------------- vocabulary
const DECISION = {
  ENTERED: "Entered · Intacct", ENTRATA_HANDOFF: "Entrata handoff", HELD: "Held",
  ALREADY_PROCESSED: "Already processed", NOT_A_BILL: "Not a bill",
};
const pill = (d) => `<span class="pill ${esc(d)}">${esc(DECISION[d] || d)}</span>`;
const codeChips = (codes) => (codes || []).map((c) => `<span class="code">${esc(c)}</span>`).join("");
// Confidence is only shown when it is not High: a single "Check reading" flag where the AI was unsure.
const conf = (c, why = "") => (!c || c === "High" ? "" : `<span class="check-flag" title="${esc(why || "The AI was not fully sure of this reading. Spot-check it against the document.")}">${icon("alert", "sm")}Check reading</span>`);

function prettyBatch(name) {
  return String(name || "")
    .replace(/^\d{8}-\d{4}_/, "").replace(/^\d{2}_/, "").replace(/_/g, " ")
    .replace(/\bholdout\b/i, "Unseen test set")
    // Hillpointe's folder "07_Invoice_Batch_02_Rerun" is Batch 02 (a second inbox pull), not a rerun of anything.
    // A real rerun is marked by the "Rerun" tag (documents already processed), not by the name.
    .replace(/^(Invoice Batch \d+) Rerun$/i, "$1");
}
function initials(name) {
  const p = prettyBatch(name);
  const m = p.match(/Batch (\d+)/i);
  if (m) return "B" + Number(m[1]);
  const w = p.split(/\s+/).filter(Boolean);
  return ((w[0] || "?")[0] + (w[w.length - 1] || "")[0]).toUpperCase();
}
const AVATAR_COLORS = ["#c2412d", "#1f5cf0", "#0f7b54", "#6b4fd8", "#a8560a", "#0e7490"];
const avatarColor = (s) => AVATAR_COLORS[[...String(s)].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_COLORS.length];
function sourceLabel(src) {
  const s = String(src || "");
  const model = s.includes("opus") ? "Claude Opus 5.5" : s.includes("sonnet") ? "Claude Sonnet 5.5" : "";
  if (s.startsWith("cache:")) return `${model} (saved reading)`;
  if (s.startsWith("label")) return "Hand-labelled answers";
  if (s.startsWith("unavailable") || s === "none") return "Not read";
  return model || s;
}
function majority(obj) { return Object.entries(obj || {}).sort((a, b) => b[1] - a[1])[0]?.[0]; }
function dayLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const s = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return sameDay ? `Today, ${s}` : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}
const timeLabel = (iso) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

function runSentence(sum) {
  const b = sum.by_decision || {};
  const n = (k) => b[k]?.count || 0;
  const parts = [];
  if (n("ENTERED")) parts.push(`${n("ENTERED")} bill${n("ENTERED") > 1 ? "s" : ""} ready for Sage Intacct (${money(b.ENTERED.amount)})`);
  if (n("ENTRATA_HANDOFF")) parts.push(`${n("ENTRATA_HANDOFF")} handed to Property Accounting for Entrata (${money(b.ENTRATA_HANDOFF.amount)})`);
  if (n("HELD")) {
    const codes = Object.entries(sum.codes || {}).map(([c, k]) => (k > 1 ? `${k}× ${c}` : c)).join(", ");
    parts.push(`${n("HELD")} held for a person${codes ? ` (${codes})` : ""}`);
  }
  if (n("NOT_A_BILL")) parts.push(`${n("NOT_A_BILL")} not a bill`);
  let s = parts.length ? parts.join("; ") + "." : "";
  if (n("ALREADY_PROCESSED")) {
    s = `${n("ALREADY_PROCESSED")} document${n("ALREADY_PROCESSED") > 1 ? "s were" : " was"} already processed, so nothing was entered twice. ` + s;
  }
  const c = sum.confidence || {};
  const unsure = (c.Medium || 0) + (c.Low || 0);
  if (unsure) s += ` ${unsure} reading${unsure > 1 ? "s" : ""} to spot-check.`;
  return s.trim();
}

// ------------------------------------------------------------------------------------------- state
const S = { runs: [], inboxes: [], exc: [], usage: null, status: null, policy: null, runCache: {}, sideOpen: store.get("side", { routes: true, batches: false }) };

async function loadAll() {
  const [runs, inboxes, exc, usage, policy] = await Promise.all([
    api("/api/runs"), api("/api/inboxes"), api("/api/exceptions"), api("/api/usage"), api("/api/policy"),
  ]);
  Object.assign(S, { runs, inboxes, exc, usage, policy });
  S.runCache = {};
  renderChrome();
  api("/api/status").then((st) => { S.status = st; renderSidebar(); }).catch(() => {});
}

const routeOf = (code) => S.policy?.codes?.[code]?.route || "AP Manager";

// ------------------------------------------------------------------------------------------- chrome
function renderChrome() { renderSidebar(); renderTopbar(); renderTour(); }

function renderSidebar() {
  const h = location.hash || "#/";
  const active = (p) => (p === "#/" ? h === "#/" || h === "" || h.startsWith("#/run") || h.startsWith("#/doc") : h.startsWith(p)) ? "active" : "";
  const routes = {};
  for (const c of Object.values(S.policy?.codes || {})) routes[c.route] = 0;
  for (const e of S.exc) routes[e.route || "AP Manager"] = (routes[e.route || "AP Manager"] || 0) + 1;
  const u = S.usage;
  const cachedShare = u && u.input + u.cache_read ? Math.round((100 * u.cache_read) / (u.input + u.cache_read + u.cache_write)) : 0;
  const latestRun = (name) => S.runs.find((r) => r.inbox_name === name && !r.what_if);

  $("#sidebar").innerHTML = `
    <div class="brand">
      <a class="logo" href="#/"><span class="logo-mark"><svg viewBox="0 0 24 24"><path d="M7 5v14M17 5v14M7 12h10"/></svg></span>Hillpointe AP</a>
      <button class="icon-btn" title="Open exceptions" onclick="location.hash='#/exceptions'">${icon("bell")}</button>
    </div>
    <div class="team-card">
      <div class="team-row">
        <div class="avatar">AP</div>
        <div style="min-width:0"><div class="team-name">AP Team</div><div class="team-sub">Hillpointe · Accounts Payable</div></div>
      </div>
    </div>
    <nav class="nav">
      <a href="#/" class="${active("#/")}">${icon("home")}Home</a>
      <a href="#/exceptions" class="${active("#/exceptions")}">${icon("alert")}Exceptions ${S.exc.length ? `<span class="badge">${S.exc.length}</span>` : ""}</a>
      <a href="#/ledger" class="${active("#/ledger")}">${icon("db")}Ledger &amp; reruns</a>
      <a href="#/rules" class="${active("#/rules")}">${icon("sliders")}Rules</a>
      <a href="#/how" class="${active("#/how")}">${icon("book")}How it works</a>
    </nav>
    <div class="side-section">
      <button class="side-head ${S.sideOpen.routes ? "" : "closed"}" onclick="toggleSide('routes')">${icon("chevdown")}Routes</button>
      ${S.sideOpen.routes ? Object.entries(routes).map(([r, n]) => `
        <a class="side-item" href="#/exceptions?route=${enc(r)}" title="${esc(r)}"><span class="hash">#</span><span class="label">${esc(r)}</span>${n ? `<span class="count">${n}</span>` : ""}</a>`).join("") : ""}
    </div>
    <div class="side-section">
      <button class="side-head ${S.sideOpen.batches ? "" : "closed"}" onclick="toggleSide('batches')">${icon("chevdown")}Batches</button>
      ${S.sideOpen.batches ? S.inboxes.map((b) => {
        const lr = latestRun(b.name);
        const href = lr ? `#/run/${enc(lr.run_id)}` : "";
        return `<a class="side-item" ${href ? `href="${href}"` : `href="javascript:void(0)" onclick="openRunModal('${esc(b.path)}')"`} title="${esc(b.path)}">
          ${icon("folder", "sm")}<span class="label">${esc(prettyBatch(b.name))}</span><span class="count">${b.docs}</span></a>`;
      }).join("") : ""}
    </div>
    <div class="spacer"></div>
    <div class="side-card">
      <h4>Process new invoices</h4>
      <p>Drop in PDFs, scans or Word files. Claude reads them; the AP policy decides.</p>
      <button class="link" onclick="openImport()">Import →</button>
    </div>
    ${u ? `<div class="side-card">
      <div class="row" style="gap:10px"><b style="font-size:15px">AI reading</b><div class="usage-bar"><span style="width:${cachedShare}%"></span></div></div>
      <p style="margin:6px 0 0"><b style="color:var(--text)">${money(u.cost)}</b> for ${u.reads} reads · ${cachedShare}% of input served from prompt cache. Every file is read once; reruns are free.</p>
    </div>` : ""}`;
}
function toggleSide(k) { S.sideOpen[k] = !S.sideOpen[k]; store.set("side", S.sideOpen); renderSidebar(); }

function renderTopbar() {
  if (STATIC && !$("#demoBar")) {
    $(".main").insertAdjacentHTML("afterbegin", `<div id="demoBar" class="demo-bar">${icon("sparkle", "sm")}<span><b>Read-only demo</b> of the Hillpointe AP system, showing the submitted runs (Batch 01, its rerun, Batch 02). Processing new invoices and changing rules happen in the local app.</span></div>`);
  }
  $("#topbar").innerHTML = `
    <div class="search" onclick="openPalette()">${icon("search")}<span>Search invoices, vendors, codes</span><kbd>⌘K</kbd></div>
    <div class="grow"></div>
    <button class="icon-btn" title="System check" onclick="openStatus()" style="background:var(--bg-soft);width:44px;height:44px">${icon("shield")}</button>
    <button class="btn" onclick="openImport()">${icon("upload")}<span>Import</span></button>
    <button class="btn primary" onclick="openRunModal()">${icon("play")}<span>Run batch</span></button>`;
}

// ------------------------------------------------------------------------------------------- router
const VIEW = () => $("#view");
async function route() {
  const h = location.hash || "#/";
  const [path, qs] = h.slice(1).split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const q = new URLSearchParams(qs || "");
  renderSidebar();
  VIEW().scrollTop = 0;
  try {
    if (parts[0] === "run") await viewRun(parts[1], q.get("tab") || "docs");
    else if (parts[0] === "doc") await viewDoc(parts[1], parts.slice(2).join("/"));
    else if (parts[0] === "exceptions") viewExceptions(q.get("route"), q.get("code"));
    else if (parts[0] === "ledger") await viewLedger(q.get("tab") || "entered");
    else if (parts[0] === "rules") await viewRules();
    else if (parts[0] === "how") viewHow();
    else viewHome(q.get("show") || store.get("feedFilter", "all"));
  } catch (e) {
    VIEW().innerHTML = `<div class="page"><div class="empty"><h3>Couldn't load this page</h3><p>${esc(e.message)}</p><a href="#/">Back to Home</a></div></div>`;
  }
  renderTour();
}
window.addEventListener("hashchange", route);

// ------------------------------------------------------------------------------------------- home
function viewHome(filter) {
  store.set("feedFilter", filter);
  const runs = S.runs.filter((r) => filter === "all" || (filter === "previews" ? r.what_if : !r.what_if));
  const groups = [];
  for (const r of runs) {
    const label = dayLabel(r.started_at);
    if (!groups.length || groups[groups.length - 1].label !== label) groups.push({ label, runs: [] });
    groups[groups.length - 1].runs.push(r);
  }
  const card = (r) => {
    const s = r.summary;
    const b = s.by_decision;
    const done = (b.ENTERED?.count || 0) + (b.ENTRATA_HANDOFF?.count || 0);
    const held = (b.HELD?.count || 0) + (b.NOT_A_BILL?.count || 0);
    const again = b.ALREADY_PROCESSED?.count || 0;
    const mini = s.peek.map((p) => `
      <div class="mini"><div class="t"><span>${esc(p.file_name.replace(/\.[^.]+$/, ""))}</span><span>${p.amount ? esc(money(p.amount)) : ""}</span></div>
        <div class="n"><span>${esc(p.decision === "ALREADY_PROCESSED" ? "Already processed" : p.vendor_name || "Unknown vendor")}</span>
          <span class="toggle ${p.decision === "ENTERED" || p.decision === "ENTRATA_HANDOFF" ? "on" : p.decision === "HELD" ? "held" : ""}"></span></div>
        ${p.codes.length ? `<div class="t" style="margin-top:3px"><span style="color:var(--bad);font-weight:600">${esc(p.codes.join(" · "))}</span></div>` : ""}
      </div>`).join("");
    return `
      <div class="run">
        <div class="avatar" style="background:${avatarColor(r.inbox_name)}">${esc(initials(r.inbox_name))}</div>
        <div class="card run-card" onclick="location.hash='#/run/${enc(r.run_id)}'">
          <div style="min-width:0">
            <h3>${esc(prettyBatch(r.inbox_name))}${r.what_if ? ' <span class="pill NOT_A_BILL" style="vertical-align:middle">Preview</span>' : again ? ' <span class="pill NOT_A_BILL" style="vertical-align:middle">Rerun</span>' : ""}</h3>
            <div class="meta"><span>${esc(timeLabel(r.started_at))}</span><span class="sep"></span><span>${s.docs} documents</span><span class="sep"></span>
              <span>${esc(sourceLabel(majority(s.sources)))}</span><span class="sep"></span><span>${r.what_if ? "Not recorded" : "Recorded in ledger"}</span></div>
            <div class="summary clamp">${esc(r.note ? r.note + ". " : "")}${esc(runSentence(s))}</div>
            <button class="more" onclick="event.stopPropagation(); const el=this.previousElementSibling; el.classList.toggle('clamp'); this.textContent = el.classList.contains('clamp') ? 'Show more' : 'Show less'">Show more</button>
          </div>
          <div class="thumb"><div class="thumb-inner">${mini}</div></div>
          <div class="run-foot">
            <span class="chip" title="Entered or handed to Entrata">${icon("checkbox", "sm")}${done}</span>
            <span class="chip" title="Held for a person">${icon("alert", "sm")}${held}</span>
            ${again ? `<span class="chip" title="Already processed, skipped">${icon("refresh", "sm")}${again}</span>` : ""}
            ${STATIC ? "" : `<button class="chip chip-btn" title="Delete this run" onclick="event.stopPropagation(); openDeleteRun('${esc(r.run_id)}')">${icon("trash", "sm")}</button>`}
          </div>
        </div>
      </div>`;
  };
  VIEW().innerHTML = `
    <div class="page">
      <div class="feed-head">
        <span class="dropdown">${esc(groups[0]?.label || dayLabel(new Date().toISOString()))}</span>
        <label class="dropdown">${{ all: "All runs", recorded: "Recorded runs", previews: "Previews" }[filter]} ${icon("chevdown", "sm")}
          <select onchange="location.hash='#/?show='+this.value">
            <option value="all" ${filter === "all" ? "selected" : ""}>All runs</option>
            <option value="recorded" ${filter === "recorded" ? "selected" : ""}>Recorded runs</option>
            <option value="previews" ${filter === "previews" ? "selected" : ""}>Previews</option>
          </select></label>
      </div>
      ${groups.length ? groups.map((g, i) => `${i ? `<div class="day">${esc(g.label)}</div>` : ""}${g.runs.map(card).join("")}`).join("") : `
        <div class="empty"><h3>No runs yet</h3><p>Process Batch 01 to see the Intacct import, the Entrata handoff and the exception log.</p>
        <button class="btn primary" onclick="openRunModal('01_Invoice_Batch_01')">${icon("play")}Run Batch 01</button></div>`}
    </div>`;
}

// ------------------------------------------------------------------------------------------- run page
async function getRun(id) {
  if (!S.runCache[id]) S.runCache[id] = await api(`/api/runs/${enc(id)}`);
  return S.runCache[id];
}

async function viewRun(id, tab) {
  const r = await getRun(id);
  const s = r.summary;
  const b = s.by_decision;
  const recs = r.records;
  const entered = recs.filter((x) => x.decision === "ENTERED");
  const entrata = recs.filter((x) => x.decision === "ENTRATA_HANDOFF");
  const held = recs.filter((x) => x.decision === "HELD" || x.decision === "NOT_A_BILL");
  const appr = recs.filter((x) => x.approvers?.length);
  const xlsx = r.files.find((f) => f.startsWith("AP_Bill_Import_"));
  const dl = (f, label) => (r.files.includes(f) ? `<a class="btn outline sm" href="${A(`/api/runs/${enc(id)}/file/${enc(f)}`)}">${icon("download", "sm")}${label}</a>` : "");
  const intacctLines = entered.flatMap((x) => x.bill_lines.map((l, i) => ({ ...l, rec: x, line: i + 1 })));
  const intacctTotal = intacctLines.reduce((a, l) => a + Number(l.amount), 0);
  const tabs = [["docs", "Documents", recs.length], ["intacct", "Intacct import", intacctLines.length], ["entrata", "Entrata handoff", entrata.length],
    ["exceptions", "Exceptions", held.length], ["approvals", "Approvals", appr.length]];
  const tabBtn = ([k, label, n]) => `<button class="tab ${tab === k ? "active" : ""}" onclick="location.hash='#/run/${enc(id)}?tab=${k}'">${label}<span class="n">${n}</span></button>`;
  const docRow = (x, i) => `
    <tr class="click" onclick="location.hash='#/doc/${enc(id)}/${enc(x.file_name)}'">
      <td class="muted">${i + 1}</td>
      <td><b>${esc(x.file_name)}</b><div class="sub">${esc(x.doc_kind || "")}</div></td>
      <td>${esc(x.vendor_name || "—")}<div class="sub">${esc(x.vendor_id || "")}</div></td>
      <td class="mono">${esc(x.bill_no || "—")}</td>
      <td class="num">${money(x.amount)}</td>
      <td>${pill(x.decision)} ${conf(x.confidence, x.confidence_reason)}</td>
      <td>${codeChips(x.hold_codes)}</td>
    </tr>`;
  let body = "";
  if (tab === "docs") {
    body = `<div class="table-wrap"><table><thead><tr><th>#</th><th>Document</th><th>Vendor</th><th>Invoice</th><th class="num">Amount</th><th>Decision</th><th>Codes</th></tr></thead>
      <tbody>${recs.map(docRow).join("")}</tbody></table></div>
      <p class="muted small">Processing order: credits first, then by bill date, so a credit is applied before a later invoice is checked against the PO.</p>`;
  } else if (tab === "intacct") {
    body = intacctLines.length ? `<div class="table-wrap"><table><thead><tr><th>Bill</th><th>Line</th><th>Account</th><th>Location</th><th>Dept</th><th>Project</th><th>Task</th><th>Type</th><th>Memo</th><th class="num">Amount</th></tr></thead>
      <tbody>${intacctLines.map((l) => `<tr class="click" onclick="location.hash='#/doc/${enc(id)}/${enc(l.rec.file_name)}'">
        <td class="mono">${esc(l.rec.bill_no)}<div class="sub">${esc(l.rec.vendor_id)}</div></td><td>${l.line}</td><td class="mono">${esc(l.acct)}</td><td>${esc(l.loc)}</td><td>${esc(l.dept)}</td>
        <td>${esc(l.project)}</td><td>${esc(l.task)}</td><td>${esc(l.cost_type)}</td><td>${esc(l.memo)}</td><td class="num">${money(l.amount)}</td></tr>`).join("")}</tbody>
      <tfoot><tr><td colspan="9">Control total · ${entered.length} bills, ${intacctLines.length} lines</td><td class="num">${money(intacctTotal)}</td></tr></tfoot></table></div>
      <p class="muted small">Written onto Hillpointe's AP_Bill_Import_Template and checked against its Field Guide row by row. Intacct rejects a whole file for one bad row, so a bill that fails is held instead.</p>`
      : `<div class="empty"><h3>No new bills for Intacct</h3><p>${b.ALREADY_PROCESSED?.count ? "Everything in this batch was already processed. Nothing is entered twice." : "Nothing in this run was entered."}</p></div>`;
  } else if (tab === "entrata") {
    body = entrata.length ? `<div class="table-wrap"><table><thead><tr><th>Document</th><th>Vendor</th><th>Invoice</th><th>Entrata GL</th><th>Description</th><th class="num">Amount</th></tr></thead>
      <tbody>${entrata.flatMap((x) => x.entrata_rows.map((e) => `<tr class="click" onclick="location.hash='#/doc/${enc(id)}/${enc(x.file_name)}'">
        <td>${esc(x.file_name)}</td><td>${esc(x.vendor_name)}</td><td class="mono">${esc(x.bill_no)}</td><td class="mono">${esc(e.gl)}</td><td>${esc(e.description)}</td><td class="num">${money(e.amount)}</td></tr>`)).join("")}</tbody></table></div>
      <p class="muted small">Stabilized communities are entered in Entrata by Property Accounting, so they're listed here instead of in the Intacct file.</p>`
      : `<div class="empty"><h3>No Entrata handoffs in this run</h3></div>`;
  } else if (tab === "exceptions") {
    body = held.length ? held.map((x) => excCard({ ...x, run_id: id, codes: x.hold_codes, findings: x.findings.filter((f) => f.hold), route: routeOf(x.hold_codes[0]), bill_no_raw: x.bill_no, total: x.amount })).join("")
      : `<div class="empty"><h3>No exceptions</h3></div>`;
  } else if (tab === "approvals") {
    body = appr.length ? `<div class="table-wrap"><table><thead><tr><th>Document</th><th>Vendor</th><th>Invoice</th><th class="num">Amount</th><th>Required approvers</th></tr></thead>
      <tbody>${appr.map((x) => `<tr class="click" onclick="location.hash='#/doc/${enc(id)}/${enc(x.file_name)}'"><td>${esc(x.file_name)}</td><td>${esc(x.vendor_name)}</td>
        <td class="mono">${esc(x.bill_no)}</td><td class="num">${money(x.amount)}</td><td>${x.approvers.map(esc).join("<br>")}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="empty"><h3>No approvals needed</h3><p>Approvers are listed for every bill entered in this run.</p></div>`;
  }
  const others = S.runs.filter((x) => x.run_id !== id);
  VIEW().innerHTML = `
    <div class="page wide">
      <a class="crumb" href="#/">${icon("left", "sm")}Home</a>
      <div class="page-head">
        <div>
          <h1>${esc(prettyBatch(r.inbox_name))}${r.what_if ? ' <span class="pill NOT_A_BILL" style="vertical-align:middle">Preview</span>' : b.ALREADY_PROCESSED?.count ? ' <span class="pill NOT_A_BILL" style="vertical-align:middle">Rerun</span>' : ""}</h1>
          <div class="meta" style="margin-top:6px"><span>${esc(dayLabel(r.started_at))}, ${esc(timeLabel(r.started_at))}</span><span class="sep"></span>
            <span>${s.docs} documents</span><span class="sep"></span><span>${esc(sourceLabel(majority(s.sources)))}</span><span class="sep"></span><span class="mono">${esc(r.run_id)}</span></div>
        </div>
        <div class="row" style="justify-content:flex-end">
          ${others.length ? `<button class="btn outline sm" onclick="openCompare('${esc(id)}')">${icon("compare", "sm")}Compare</button>` : ""}
          ${r.inbox ? `<button class="btn outline sm" onclick="openRunModal('${esc(r.inbox_name)}')">${icon("refresh", "sm")}Run again</button>` : ""}
          ${STATIC ? "" : `<button class="btn danger sm" onclick="openDeleteRun('${esc(id)}')">${icon("trash", "sm")}Delete</button>`}
        </div>
      </div>
      ${r.what_if ? `<div class="banner">${icon("sparkle")}<div><b>Preview — nothing was recorded.</b> ${esc(r.note || "This what-if run wrote its files but didn't touch the ledger.")}</div></div>` : ""}
      ${b.ALREADY_PROCESSED?.count ? `<div class="banner ok">${icon("shield")}<div><b>${b.ALREADY_PROCESSED.count} already processed — nothing entered twice.</b> These files were entered in an earlier run, so they produce no new import rows. Held documents are re-checked every time, in case they were fixed.</div></div>` : ""}
      <div class="tiles">
        <div class="tile"><div class="k">${icon("checkbox", "sm")}Entered · Intacct</div><div class="v">${b.ENTERED?.count || 0}</div><div class="s">${money(b.ENTERED?.amount || 0)}</div></div>
        <div class="tile"><div class="k">${icon("external", "sm")}Entrata handoff</div><div class="v">${b.ENTRATA_HANDOFF?.count || 0}</div><div class="s">${money(b.ENTRATA_HANDOFF?.amount || 0)}</div></div>
        <div class="tile"><div class="k">${icon("alert", "sm")}Held for a person</div><div class="v">${(b.HELD?.count || 0) + (b.NOT_A_BILL?.count || 0)}</div><div class="s">${money((b.HELD?.amount || 0) + (b.NOT_A_BILL?.amount || 0))}</div></div>
        <div class="tile"><div class="k">${icon("refresh", "sm")}Already processed</div><div class="v">${b.ALREADY_PROCESSED?.count || 0}</div><div class="s">skipped, no new rows</div></div>
      </div>
      <div class="row" style="margin-bottom:18px">
        ${xlsx ? dl(xlsx, "Excel (Intacct template)") : ""}${dl("intacct_bill_import.csv", "Intacct CSV")}${dl("entrata_handoff.csv", "Entrata handoff")}
        ${dl("exception_log.csv", "Exception log")}${dl("approvals.csv", "Approvals")}
        ${r.files.includes("run_report.html") ? `<a class="btn outline sm" target="_blank" href="${A(`/api/runs/${enc(id)}/file/run_report.html`)}">${icon("external", "sm")}Run report</a>` : ""}
      </div>
      <div class="tabs">${tabs.map(tabBtn).join("")}</div>
      ${body}
    </div>`;
}

// ------------------------------------------------------------------------------------------- document page
function kvRows(pairs) {
  return pairs.filter(([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${Array.isArray(v) ? v.map(esc).join("<br>") : esc(v)}</dd>`).join("");
}

async function viewDoc(id, file) {
  const r = await getRun(id);
  const x = r.records.find((d) => d.file_name === file);
  if (!x) throw new Error(`${file} is not in run ${id}`);
  if (x.decision === "HELD") { const t = store.get("tour", {}); t.exception = true; store.set("tour", t); }
  const ex = x.extraction || {};
  const holds = x.findings.filter((f) => f.hold);
  const notes = x.findings.filter((f) => !f.hold);
  const ext = file.split(".").pop().toLowerCase();
  const src = A(`/api/source/${enc(id)}/${enc(file)}`);
  const viewer = ["pdf"].includes(ext) ? `<iframe src="${src}#view=FitH" title="${esc(file)}"></iframe>`
    : ["png", "jpg", "jpeg"].includes(ext) ? `<img src="${src}" alt="${esc(file)}">` : `<pre id="srcText">Loading…</pre>`;
  const lines = x.bill_lines || [];
  const pa = ex.pay_application;
  VIEW().innerHTML = `
    <div class="page wide has-rail">
      <a class="crumb" href="#/run/${enc(id)}">${icon("left", "sm")}${esc(prettyBatch(r.inbox_name))}</a>
      <div class="doc-grid">
        <div class="viewer">
          <div class="vhead"><span>${icon("file", "sm")} ${esc(file)}</span><a href="${src}" target="_blank">Open ${icon("external", "sm")}</a></div>
          <div class="vbody">${viewer}</div>
        </div>
        <div>
          <div class="doc-title"><h1>${esc(x.vendor_name || file)}</h1>${pill(x.decision)}</div>
          <div class="meta" style="margin-top:4px">${x.vendor_id ? `<span>${esc(x.vendor_id)}</span><span class="sep"></span>` : ""}
            <span>${esc((x.doc_kind || "").replace(/_/g, " "))} <span class="mono">${esc(x.bill_no || "")}</span></span>
            ${x.project_id ? `<span class="sep"></span><span>Project ${esc(x.project_id)}</span>` : ""}
            ${x.reference_no ? `<span class="sep"></span><span>${esc(x.reference_no)}</span>` : ""}</div>
          <div class="amount-big">${money(x.amount)}</div>
          ${x.confidence && x.confidence !== "High" ? `<div class="row" style="margin-bottom:16px;flex-wrap:nowrap;align-items:flex-start">${conf(x.confidence, x.confidence_reason)}<span class="muted small clamp2" title="${esc(x.confidence_reason)}">${esc(x.confidence_reason)}</span></div>` : ""}

          <div class="section" id="why">
            <h3>${icon("checkbox")}${holds.length ? "Why it's held" : "Decision"}<span class="hint">every rule runs on every document</span></h3>
            ${holds.length ? holds.map((f) => `
              <div class="finding"><span class="code">${esc(f.code)}</span><div class="msg">${esc(f.message)}</div>
                <div class="route"><span>Route: <b>${esc(routeOf(f.code))}</b></span>${f.policy_ref ? `<span>Policy ${esc(f.policy_ref)}</span>` : ""}</div></div>`).join("")
              : `<p style="margin:0">${x.decision === "ENTERED" ? "Every check passed. The bill is in the Intacct import file." : x.decision === "ENTRATA_HANDOFF" ? "Every check passed. Stabilized community, so it goes to Property Accounting for Entrata." : x.decision === "ALREADY_PROCESSED" ? "This exact file was entered in an earlier run, so it is skipped. Nothing is entered twice." : "No holds."}</p>`}
            ${notes.length ? `<div style="margin-top:12px">${notes.map((f) => `<div class="finding"><span class="code ${f.code === "WARN" ? "warn" : "info"}">${esc(f.code)}</span><div class="msg">${esc(f.message)}</div>${f.policy_ref ? `<div class="route"><span>Policy ${esc(f.policy_ref)}</span></div>` : ""}</div>`).join("")}</div>` : ""}
          </div>

          ${lines.length || x.entrata_rows.length || x.approvers.length ? `
          <div class="section" id="coding">
            <h3>${icon("receipt")}How it's coded<span class="hint">${lines.length ? "Sage Intacct lines" : x.entrata_rows.length ? "Entrata rows" : ""}</span></h3>
            ${lines.length ? `<div class="table-wrap"><table><thead><tr><th>Account</th><th>Loc / Dept</th><th>Project · Task · Type</th><th>Memo</th><th class="num">Amount</th></tr></thead><tbody>
              ${lines.map((l) => `<tr><td class="mono">${esc(l.acct)}</td><td>${esc(l.loc)} / ${esc(l.dept)}</td><td>${esc([l.project, l.task, l.cost_type].filter(Boolean).join(" · ") || "—")}</td><td>${esc(l.memo)}</td><td class="num">${money(l.amount)}</td></tr>`).join("")}
              </tbody><tfoot><tr><td colspan="4">Bill total</td><td class="num">${money(lines.reduce((a, l) => a + Number(l.amount), 0))}</td></tr></tfoot></table></div>` : ""}
            ${x.entrata_rows.length ? `<div class="table-wrap"><table><thead><tr><th>Entrata GL</th><th>Description</th><th class="num">Amount</th></tr></thead><tbody>
              ${x.entrata_rows.map((e) => `<tr><td class="mono">${esc(e.gl)}</td><td>${esc(e.description)}</td><td class="num">${money(e.amount)}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${x.approvers.length ? `<div style="margin-top:14px"><b class="small">Approvers</b><ul style="margin:6px 0 0;padding-left:20px">${x.approvers.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}
          </div>` : ""}

          <div class="section" id="ai">
            <h3>${icon("sparkle")}What the AI read<span class="hint">${esc(sourceLabel(x.extraction_source))}</span></h3>
            ${ex.doc_kind ? `<dl class="kv">${kvRows([
              ["Document type", (ex.doc_kind || "").replace(/_/g, " ")], ["Vendor (as printed)", ex.vendor_name], ["Remit to", ex.remit_to],
              ["Phone / email", [ex.vendor_phone, ex.vendor_email].filter(Boolean).join(" · ")], ["Bank details printed", ex.bank_details_printed],
              ["Payment change requested", ex.payment_instruction_change_requested ? (ex.payment_change_quote || "Yes") : ""],
              ["Bill to", ex.bill_to_name], ["Invoice number", ex.document_number], ["Invoice date", ex.document_date], ["Terms printed", ex.printed_terms],
              ["References", ex.references], ["Service period", ex.service_period_start ? `${ex.service_period_start} → ${ex.service_period_end || ""}` : ""],
              ["Markings", ex.markings], ["Replaces invoice", ex.replaces_document_number], ["Credit applies to", ex.credit_applies_to_invoice],
              ["Line items", (ex.line_items || []).map((l) => `${l.description}: ${money(l.amount)}`)],
              ["Tax", (ex.tax_lines || []).map((t) => `${t.label}: ${money(t.amount)}`)], ["Total", ex.total !== null ? money(ex.total) : ""],
              ["Pay application", pa ? `App ${pa.application_no || "?"} · completed to date ${money(pa.total_completed_to_date)} · retainage ${money(pa.retainage_to_date)} · previous certificates ${money(pa.previous_certificates)} · due ${money(pa.current_payment_due)}` : ""],
              ["Lien waiver", ex.lien_waiver ? `${ex.lien_waiver.present_in_document ? "Attached" : "Not attached"}${ex.lien_waiver.waiver_type ? `, ${ex.lien_waiver.waiver_type}` : ""}${ex.lien_waiver.amount ? `, ${money(ex.lien_waiver.amount)}` : ""}` : ""],
              ["Text aimed at automation", ex.embedded_instructions], ["Unsure about", ex.extraction_warnings], ["Reviewer notes", ex.observations],
            ])}</dl>
            <p class="muted small" style="margin:12px 0 0">The AI only reads facts into a fixed form. The invoice number and total must appear in the document's own text and the numbers must add up, or the document is held. It never picks a GL account, entity, approver or hold.</p>`
            : `<p class="muted" style="margin:0">${esc(x.extraction_source || "This file could not be read.")}</p>`}
          </div>

          <div class="section" id="trace">
            <h3>${icon("steps")}Step by step<span class="hint">the audit trail</span></h3>
            <ol class="trace">${x.trace.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>
            <p class="muted small" style="margin:10px 0 0">SHA-256 <span class="mono">${esc(x.sha256.slice(0, 16))}…</span> · duplicate key <span class="mono">${esc(x.dup_key)}</span></p>
          </div>
        </div>
      </div>
    </div>
    <div class="rail">
      <button class="ai" data-tip="What the AI read" onclick="$('#ai').scrollIntoView({behavior:'smooth'})">${icon("sparkle")}</button>
      ${lines.length || x.entrata_rows.length ? `<button data-tip="How it's coded" onclick="$('#coding').scrollIntoView({behavior:'smooth'})">${icon("list")}</button>` : ""}
      <button data-tip="Why" onclick="$('#why').scrollIntoView({behavior:'smooth'})">${icon("checkbox")}</button>
      <button data-tip="Step by step" onclick="$('#trace').scrollIntoView({behavior:'smooth'})">${icon("steps")}</button>
    </div>`;
  if (!["pdf", "png", "jpg", "jpeg"].includes(ext)) {
    api(STATIC ? "/" + src : src).then((d) => { const el = $("#srcText"); if (el) el.textContent = d.text; }).catch((e) => { const el = $("#srcText"); if (el) el.textContent = e.message; });
  }
}

// ------------------------------------------------------------------------------------------- exceptions
function excCard(e) {
  const f = e.findings || [];
  return `
    <div class="exc" onclick="location.hash='#/doc/${enc(e.run_id)}/${enc(e.file_name)}'">
      <div class="top">${pill(e.decision)}${codeChips(e.codes)}${conf(e.confidence, e.confidence_reason)}</div>
      <div class="amt">${money(e.total ?? e.amount)}</div>
      <div class="who">${esc(e.vendor_name || "Unknown vendor")} <span class="muted" style="font-weight:400">· <span class="mono">${esc(e.bill_no_raw || "")}</span> · ${esc(e.file_name)}</span></div>
      <div></div>
      <div class="msg">${esc(f[0]?.message || "")}${f.length > 1 ? ` <span class="muted">+${f.length - 1} more reason${f.length > 2 ? "s" : ""}</span>` : ""}</div>
    </div>`;
}

function viewExceptions(routeF, codeF) {
  const items = S.exc.filter((e) => (!routeF || (e.route || "AP Manager") === routeF) && (!codeF || e.codes.includes(codeF)));
  const routes = {};
  const codes = {};
  for (const e of S.exc) {
    routes[e.route || "AP Manager"] = (routes[e.route || "AP Manager"] || 0) + 1;
    for (const c of e.codes) codes[c] = (codes[c] || 0) + 1;
  }
  const link = (r, c) => `#/exceptions?${new URLSearchParams(Object.fromEntries([["route", r], ["code", c]].filter(([, v]) => v))).toString()}`;
  const groups = {};
  for (const e of items) (groups[e.route || "AP Manager"] ||= []).push(e);
  VIEW().innerHTML = `
    <div class="page">
      <div class="page-head"><div><h1>Exceptions</h1>
        <p>Documents waiting for a person, grouped by who needs to act. Each one gives the reason in plain English and the policy section behind it. This is the live state of the ledger: when a held document comes back corrected, it is re-checked and drops off this list.</p></div></div>
      <div class="filters">
        <a class="fchip ${!routeF ? "on" : ""}" href="${link(null, codeF)}">All routes <span class="n">${S.exc.length}</span></a>
        ${Object.entries(routes).map(([r, n]) => `<a class="fchip ${routeF === r ? "on" : ""}" href="${link(r, codeF)}">${esc(r)} <span class="n">${n}</span></a>`).join("")}
      </div>
      <div class="filters">
        ${Object.entries(codes).map(([c, n]) => `<a class="fchip ${codeF === c ? "on" : ""}" href="${link(routeF, codeF === c ? null : c)}" title="${esc(S.policy?.codes?.[c]?.meaning || "")}"><span class="mono">${esc(c)}</span> <span class="n">${n}</span></a>`).join("")}
      </div>
      ${items.length ? Object.entries(groups).map(([r, list]) => `
        <div class="route-group"><h3><span class="hash">#</span>${esc(r)} <span class="muted" style="font-weight:400">· ${list.length}</span></h3>
        ${list.map(excCard).join("")}</div>`).join("")
      : `<div class="empty"><h3>Nothing waiting</h3><p>${S.exc.length ? "No exceptions match these filters." : "No open exceptions in the ledger. Run a batch to see holds here."}</p></div>`}
    </div>`;
}

// ------------------------------------------------------------------------------------------- ledger
async function viewLedger(tab) {
  const L = await api("/api/ledger");
  const tabs = [["entered", "Entered bills", L.entered.length], ["register", "Every decision", L.documents.length], ["runs", "Runs", L.runs.length], ["snapshots", "Snapshots", L.snapshots.length]];
  let body = "";
  if (tab === "entered") {
    body = L.entered.length ? `<div class="table-wrap"><table><thead><tr><th>Vendor</th><th>Invoice (as printed)</th><th>Duplicate key</th><th>System</th><th>Type</th><th>Bill date</th><th class="num">Amount</th><th>Document</th></tr></thead><tbody>
      ${L.entered.map((e) => `<tr class="click" onclick="location.hash='#/doc/${enc(e.run_id)}/${enc(e.file_name)}'"><td>${esc(e.vendor_id)}</td><td class="mono">${esc(e.bill_no_raw)}</td>
        <td class="mono">${esc(e.vendor_id)}|${esc(e.bill_no_norm)}</td><td>${esc(e.system)}</td><td>${esc(e.doc_type)}</td><td>${esc(e.bill_date)}</td><td class="num">${money(e.amount)}</td><td>${esc(e.file_name)}</td></tr>`).join("")}
      </tbody></table></div>` : `<div class="empty"><h3>Nothing entered yet</h3></div>`;
  } else if (tab === "register") {
    body = `<div class="row" style="margin-bottom:12px"><a class="btn outline sm" href="${A("/api/ledger/register.csv")}">${icon("download", "sm")}processed_register.csv</a></div>
      <div class="table-wrap"><table><thead><tr><th>Run</th><th>Document</th><th>Vendor</th><th>Invoice</th><th class="num">Amount</th><th>Decision</th><th>Code</th></tr></thead><tbody>
      ${L.documents.slice().reverse().map((d) => `<tr class="click" onclick="location.hash='#/doc/${enc(d.run_id)}/${enc(d.file_name)}'"><td class="mono small">${esc(d.run_id)}</td>
        <td>${esc(d.file_name)}${d.superseded ? ' <span class="pill NOT_A_BILL">superseded</span>' : ""}</td><td>${esc(d.vendor_name || "")}</td><td class="mono">${esc(d.bill_no_raw || "")}</td>
        <td class="num">${money(d.total)}</td><td>${pill(d.decision)} ${conf(d.confidence, d.confidence_reason)}</td><td>${codeChips([d.primary_code].filter(Boolean))}</td></tr>`).join("")}
      </tbody></table></div>`;
  } else if (tab === "runs") {
    body = `<div class="table-wrap"><table><thead><tr><th>Run</th><th>Batch</th><th class="num">Docs</th><th class="num">Entered</th><th class="num">Entrata</th><th class="num">Held</th><th class="num">Already processed</th><th>Policy</th><th>Model</th></tr></thead><tbody>
      ${L.runs.slice().reverse().map((x) => `<tr class="click" onclick="location.hash='#/run/${enc(x.run_id)}'"><td class="mono small">${esc(x.run_id)}</td><td>${esc(prettyBatch(x.inbox.split("/").pop()))}</td>
        <td class="num">${x.docs}</td><td class="num">${x.entered}</td><td class="num">${x.entrata}</td><td class="num">${x.held}</td><td class="num">${x.already_processed}</td>
        <td class="mono small">${esc(x.policy_hash)}</td><td class="small">${esc(x.model || "")}</td></tr>`).join("")}</tbody></table></div>
      <p class="muted small">Each run records the policy version (hash), model and prompt version it used, so any past decision can be traced to the exact rules in force.</p>`;
  } else {
    body = `<div class="row" style="margin-bottom:12px"><button class="btn outline sm" onclick="saveSnapshot()">${icon("download", "sm")}Save a snapshot now</button></div>
      <div class="table-wrap"><table><thead><tr><th>Snapshot</th><th class="num">Runs</th><th class="num">Entered bills</th><th>Saved</th><th></th></tr></thead><tbody>
      ${L.snapshots.map((s) => `<tr><td><b>${esc(s.name)}</b><div class="sub">${s.name.startsWith("pre-") ? `Ledger before ${esc(prettyBatch(s.name.slice(4)))} was first processed (saved automatically)` : s.name === "submitted" ? "State after Batch 01 → rerun → Batch 02 (the submitted evidence)" : ""}</div></td>
        <td class="num">${s.runs}</td><td class="num">${s.entered}</td><td class="small">${esc(s.saved_at.replace("T", " "))}</td>
        <td class="num"><button class="btn sm" onclick="confirmRestore('${esc(s.name)}')">${icon("undo", "sm")}Restore</button></td></tr>`).join("")}</tbody></table></div>`;
  }
  VIEW().innerHTML = `
    <div class="page wide">
      <div class="page-head"><div><h1>Ledger &amp; reruns</h1>
        <p>The record of every document ever processed, in <span class="mono">${esc(L.path)}</span>. Every run checks it together with the ERP history, so the same invoice is never entered twice, even if it comes back as a reprint, a resend or a "past due" copy.</p></div></div>
      <div class="banner">${icon("shield")}<div><b>How duplicates are caught.</b> Same vendor + same invoice number (ignoring case, spaces, dashes, "INV" prefixes and leading zeros) → DUP.
        Same vendor + same digits + same amount → DUP. Same amount in the same service period, or within 7 days → flagged for a person.
        A revised invoice replaces its original only if the original was never entered. The database itself refuses a second entry with the same vendor + number.</div></div>
      <div class="tiles">
        <div class="tile"><div class="k">Entered bills</div><div class="v">${L.entered.length}</div><div class="s">unique vendor + invoice number</div></div>
        <div class="tile"><div class="k">Decisions recorded</div><div class="v">${L.documents.length}</div><div class="s">every document, every run</div></div>
        <div class="tile"><div class="k">Runs</div><div class="v">${L.runs.length}</div><div class="s">recorded (previews excluded)</div></div>
        <div class="tile"><div class="k">Snapshots</div><div class="v">${L.snapshots.length}</div><div class="s">restore points</div></div>
      </div>
      <div class="tabs">${tabs.map(([k, l, n]) => `<button class="tab ${tab === k ? "active" : ""}" onclick="location.hash='#/ledger?tab=${k}'">${l}<span class="n">${n}</span></button>`).join("")}</div>
      ${body}
    </div>`;
}

function confirmRestore(name) {
  modal(`
    <div class="modal-head"><h2>Restore “${esc(name)}”?</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
    <div class="modal-body"><p>The ledger goes back to this snapshot. Decisions recorded after it are removed from the ledger. Their run folders stay in <span class="mono">output/</span>, so nothing is lost from the audit trail.</p>
      <p class="muted small">Use this to re-decide a batch under a new rule, or to return to the submitted state (“submitted”).</p></div>
    <div class="modal-foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="doRestore">Restore</button></div>`);
  $("#doRestore").onclick = async () => {
    try { await post(`/api/snapshots/${enc(name)}/restore`); closeModal(); toast(`Ledger restored to “${name}”`); await loadAll(); route(); }
    catch (e) { toast(e.message, true); }
  };
}
async function saveSnapshot() {
  const name = prompt("Snapshot name", `manual-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}`);
  if (!name) return;
  try { await post("/api/snapshots", { name }); toast("Snapshot saved"); route(); } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------------------------------- rules
const R = { orig: "", draft: "", changes: {}, yaml: false, manual: false, valid: { ok: true }, inbox: "01_Invoice_Batch_01", preview: null };

async function viewRules() {
  const p = await api("/api/policy");
  S.policy = p;
  if (!R.draft || (!Object.keys(R.changes).length && !R.manual)) { R.orig = p.text; R.draft = p.text; }
  R.orig = p.text;
  renderRules();
}

function knobControl(k) {
  const v = k.path in R.changes ? R.changes[k.path] : k.value;
  const id = "k_" + k.path.replace(/\./g, "_");
  if (k.type === "choice" || k.type === "bool") {
    const opts = k.type === "bool" ? [[true, "Yes"], [false, "No"]] : k.options.map((o) => [o, o]);
    return `<div class="seg">${opts.map(([o, l]) => `<button class="${v === o ? "on" : ""}" onclick='setKnob(${JSON.stringify(k.path)}, ${JSON.stringify(o)})'>${esc(l)}</button>`).join("")}</div>`;
  }
  const unit = k.unit ? `<span class="unit">${esc(k.unit)}</span>` : "";
  return `${k.unit === "$" ? unit : ""}<input class="field" id="${id}" type="${k.type === "number" ? "number" : "text"}" step="any" value="${esc(v ?? "")}" placeholder="${esc(k.placeholder || "")}"
    onchange='setKnob(${JSON.stringify(k.path)}, this.value === "" ? null : (${k.type === "number"} ? Number(this.value) : this.value))'>${k.unit && k.unit !== "$" ? unit : ""}`;
}

async function setKnob(path, value) {
  const k = S.policy.knobs.find((x) => x.path === path);
  if (k && (value === k.value || (value === null && (k.value === null || k.value === "")))) delete R.changes[path];
  else R.changes[path] = value;
  R.manual = false;
  await rebuildDraft();
}
async function rebuildDraft() {
  try {
    const d = await post("/api/policy/draft", { text: R.orig, changes: R.changes });
    R.draft = d.text;
    R.valid = { ok: d.ok, error: d.error };
  } catch (e) { R.valid = { ok: false, error: e.message }; }
  R.preview = null;
  renderRules();
}

let yamlTimer;
function onYaml(el) {
  R.draft = el.value;
  R.manual = true;
  clearTimeout(yamlTimer);
  yamlTimer = setTimeout(async () => {
    R.valid = await post("/api/policy/validate", { text: R.draft });
    R.preview = null;
    const st = $("#yamlStatus");
    if (st) st.innerHTML = R.valid.ok ? `<span style="color:var(--ok)">✓ Valid</span>` : `<span style="color:var(--bad)">${esc(R.valid.error)}</span>`;
    renderRulePanel();
  }, 400);
}

function renderRules() {
  const p = S.policy;
  const groups = {};
  for (const k of p.knobs) (groups[k.section] ||= []).push(k);
  const fmt = (v) => (v === null || v === "" ? "not set" : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v));
  VIEW().innerHTML = `
    <div class="page wide">
      <div class="page-head"><div><h1>Rules</h1>
        <p>Every business-rule value lives in one file, <span class="mono">config/policy.yaml</span>. Change a value, preview exactly which documents would change, then save. Vendors, projects, GL accounts, allocation % and open periods come live from the master-data workbook.</p></div></div>
      <div class="rules-grid">
        <div>
          ${Object.entries(groups).map(([sec, ks]) => `<div class="knob-group"><h4>${esc(sec)}</h4>
            ${ks.map((k) => `<div class="knob ${k.path in R.changes ? "changed" : ""}">
              <div class="lbl">${esc(k.label)}</div><div class="ctl">${knobControl(k)}</div><div class="help">${esc(k.help)}</div>
              ${k.path in R.changes ? `<div class="was">Changed from ${esc(fmt(k.value))} → ${esc(fmt(R.changes[k.path]))}</div>` : ""}</div>`).join("")}</div>`).join("")}
          <div class="knob-group"><h4>Edit the policy file directly</h4>
            <div class="section"><div class="row" style="justify-content:space-between;margin-bottom:10px">
              <span class="muted small">For anything not above (vendor overrides, keywords, routes). Checked as you type.</span>
              <button class="btn sm" onclick="R.yaml=!R.yaml; renderRules()">${R.yaml ? "Hide" : "Show"} policy.yaml</button></div>
              ${R.yaml ? `<textarea class="yaml" spellcheck="false" oninput="onYaml(this)">${esc(R.draft)}</textarea><div id="yamlStatus" class="small" style="margin-top:6px"></div>` : ""}
            </div></div>
          <div class="knob-group"><h4>Checks that run on every document (in order)</h4>
            <div class="section"><ol class="trace" style="columns:2">${p.rules.map((r) => `<li>${esc(r.replace(/_/g, " "))}</li>`).join("")}</ol></div></div>
          <div class="knob-group"><h4>Exception codes and routes</h4>
            <div class="table-wrap"><table><thead><tr><th>Code</th><th>Meaning</th><th>Route</th></tr></thead><tbody>
            ${Object.entries(p.codes).map(([c, v]) => `<tr><td><span class="code">${esc(c)}</span></td><td>${esc(v.meaning)}</td><td>${esc(v.route)}</td></tr>`).join("")}</tbody></table></div></div>
        </div>
        <div class="panel" id="rulePanel"></div>
      </div>
    </div>`;
  renderRulePanel();
}

function renderRulePanel() {
  const el = $("#rulePanel");
  if (!el) return;
  const dirty = R.draft !== R.orig;
  const processed = S.inboxes.filter((b) => b.runs > 0);
  const options = (processed.length ? processed : S.inboxes).map((b) => `<option value="${esc(b.path)}" ${b.path === R.inbox ? "selected" : ""}>${esc(prettyBatch(b.name))}</option>`).join("");
  const pv = R.preview;
  el.innerHTML = `
    <div class="section">
      <h3>${icon("sparkle")}Test the change</h3>
      <p class="muted small" style="margin-top:0">Re-decides a batch in a sandbox copy of the ledger, starting from before that batch was processed. Nothing is recorded. Saved AI readings are reused, so this costs nothing for documents already read.</p>
      <div class="stack">
        <select class="field" onchange="R.inbox=this.value; R.preview=null; renderRulePanel()">${options}</select>
        <button class="btn primary" ${R.valid.ok ? "" : "disabled"} onclick="previewRule()">${icon("play", "sm")}Preview impact${dirty ? "" : " (current rules)"}</button>
      </div>
      ${!R.valid.ok ? `<p class="small" style="color:var(--bad)">${esc(R.valid.error)}</p>` : ""}
      ${pv ? `<div style="margin-top:14px">
        <div class="banner ${pv.changes.length ? "" : "ok"}" style="margin-bottom:10px"><div><b>${pv.changes.length} document${pv.changes.length === 1 ? "" : "s"} would change</b>, ${pv.docs - pv.changes.length} unchanged${pv.baseline ? `, compared with the recorded run` : ""}.</div></div>
        ${pv.changes.map((c) => `<div class="change-row"><b>${esc(c.file_name)}</b><div>${pill(c.before.split(" ")[0])}${codeChips(c.before.split(" ").slice(1).join(" ").split(",").filter(Boolean))}<span class="arrow">→</span>${pill(c.after.split(" ")[0])}${codeChips(c.after.split(" ").slice(1).join(" ").split(",").filter(Boolean))}</div>
          <div class="muted small">${c.why.map(esc).join("<br>")}</div></div>`).join("")}
        <a class="small" href="#/run/${enc(pv.run_id)}">Open the preview run →</a></div>` : ""}
    </div>
    <div class="section">
      <h3>${icon("check")}Save</h3>
      ${dirty ? `<p class="small" style="margin-top:0">${Object.keys(R.changes).length ? `${Object.keys(R.changes).length} value${Object.keys(R.changes).length > 1 ? "s" : ""} changed.` : "policy.yaml edited."} The previous version is kept so you can undo.</p>
        <div class="stack"><button class="btn primary" ${R.valid.ok ? "" : "disabled"} onclick="saveRule(false)">Save rule</button>
        <button class="btn outline" ${R.valid.ok ? "" : "disabled"} onclick="saveRule(true)">Save and re-decide ${esc(prettyBatch(R.inbox.split("/").pop()))}</button>
        <button class="btn" onclick="R.changes={}; R.manual=false; R.draft=R.orig; R.preview=null; renderRules()">Discard changes</button></div>`
      : `<p class="muted small" style="margin:0">No unsaved changes. Policy version <span class="mono">${esc(S.policy.hash)}</span>.</p>`}
    </div>
    ${S.policy.history.length ? `<div class="section"><h3>${icon("undo")}Earlier versions</h3>
      ${S.policy.history.slice(0, 6).map((h) => `<div class="row" style="justify-content:space-between;padding:6px 0;border-top:1px solid var(--line)"><span class="small">Before save at ${esc(h.saved_at.replace("T", " "))}</span>
        <button class="btn sm" onclick="revertRule('${esc(h.name)}')">Restore</button></div>`).join("")}</div>` : ""}`;
}

async function previewRule() {
  try {
    const job = await post("/api/preview", { inbox: R.inbox, policy_text: R.draft !== R.orig ? R.draft : null });
    const res = await watchJob(job, "Previewing the rule change", "Re-deciding the batch in a sandbox. Nothing is recorded.");
    R.preview = res;
    const t = store.get("tour", {}); t.rule = true; store.set("tour", t);
    S.runs = await api("/api/runs");
    renderRulePanel(); renderTour();
  } catch (e) { toast(e.message, true); }
}

async function saveRule(apply) {
  const batch = prettyBatch(R.inbox.split("/").pop());
  if (apply) {
    const ok = await confirmBox(`Save and re-decide ${batch}?`,
      `This saves the rule, puts the ledger back to before ${batch} was first processed, and runs it again for real. Anything recorded after that point (for example a later batch) is removed from the ledger and would need to be run again. Run folders in output/ are kept.`, "Save and re-decide");
    if (!ok) return;
  }
  try {
    await put("/api/policy", { text: R.draft });
    R.changes = {}; R.manual = false; R.preview = null;
    toast("Rule saved");
    if (apply) {
      const job = await post("/api/apply", { inbox: R.inbox });
      const res = await watchJob(job, `Re-deciding ${batch}`, "Restoring the ledger to before this batch, then running it under the new rule.");
      await loadAll();
      location.hash = `#/run/${enc(res.run_id)}`;
      toast(`${res.changes.length} document${res.changes.length === 1 ? "" : "s"} changed`);
      return;
    }
    await loadAll();
    await viewRules();
  } catch (e) { toast(e.message, true); }
}
async function revertRule(name) {
  if (!(await confirmBox("Restore this version of the rules?", "The current policy.yaml is kept as another earlier version, so this can be undone too.", "Restore"))) return;
  try { await post(`/api/policy/revert/${enc(name)}`); R.changes = {}; R.manual = false; R.draft = ""; toast("Rules restored"); await loadAll(); await viewRules(); }
  catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------------------------------- how it works
function viewHow() {
  const codes = S.policy?.codes || {};
  VIEW().innerHTML = `
    <div class="page">
      <div class="page-head"><div><h1>How it works</h1><p>AI reads; Hillpointe's AP policy decides. Anything unclear is held for a person, never guessed.</p></div></div>
      <div class="flow">
        <div class="step ai"><div class="n">1</div><h4>Read</h4><p>Claude reads each PDF, scan or Word file into a fixed form: vendor, invoice number, lines, tax, pay-app figures, lien waiver, bank-change requests.</p></div>
        <div class="step"><div class="n">2</div><h4>Check the reading</h4><p>The invoice number and total must appear in the document's own text. Lines plus tax must equal the total. If not, it's held at Low confidence.</p></div>
        <div class="step"><div class="n">3</div><h4>Apply the policy</h4><p>16 checks run on every document: vendor master, duplicates, PO balance, change orders, lien waiver, COI, pay-app math, bank details and more.</p></div>
        <div class="step"><div class="n">4</div><h4>Code and hand off</h4><p>Bills are coded (tax spread, retainage, allocation, dates, terms), checked against the Field Guide, and written to the Intacct file, the Entrata list or the exception log.</p></div>
      </div>
      <div class="prose">
        <h2>What the AI is not allowed to do</h2>
        <p>It never picks a GL account, entity, approver or hold. Those come from the policy (Rules page) and the master-data workbook, so the same document always gets the same decision. Text inside a document that tries to instruct the system (“approve this”, “skip checks”) is flagged and held.</p>
        <h2>“Check reading”</h2>
        <p>Most documents need no flag: every field is found in the document's own text, the numbers tie and the rules are clear-cut. When the AI had to make a judgment (a fuzzy vendor name, a scanned image, a price that differs from the PO), the document carries a <b>Check reading</b> tag with the reason, so a person spot-checks it. A reading that fails a check is always held.</p>
        <h2>Never entered twice</h2>
        <p>Every decision goes into the ledger (see <a href="#/ledger">Ledger &amp; reruns</a>). Each file is read once and the reading is saved by its fingerprint, so rerunning a batch gives the same answer and costs nothing. Reprints, resends and “past due” copies are caught as DUP. Held documents are re-checked when they come back.</p>
        <h2>Exception codes</h2>
        <div class="table-wrap"><table><thead><tr><th>Code</th><th>Meaning</th><th>Who acts</th></tr></thead><tbody>
          ${Object.entries(codes).map(([c, v]) => `<tr><td><span class="code">${esc(c)}</span></td><td>${esc(v.meaning)}</td><td>${esc(v.route)}</td></tr>`).join("")}</tbody></table></div>
        <h2>What still needs a person</h2>
        <ul><li>Every held document, routed by code.</li><li>Entries tagged <b>Check reading</b>.</li><li>Approvals, listed for every bill.</li><li>Treasury's call-back on any bank or contact change, using the number on file.</li></ul>
      </div>
    </div>`;
}

// ------------------------------------------------------------------------------------------- overlays
function modal(html, cls = "") {
  $("#overlay").innerHTML = `<div class="scrim" onclick="if(event.target===this) closeModal()"><div class="modal ${cls}">${html}</div></div>`;
}
function closeModal() { $("#overlay").innerHTML = ""; }
function confirmBox(title, text, okLabel) {
  return new Promise((resolve) => {
    modal(`<div class="modal-head"><h2>${esc(title)}</h2></div><div class="modal-body"><p>${esc(text)}</p></div>
      <div class="modal-foot"><button class="btn" id="cbNo">Cancel</button><button class="btn primary" id="cbYes">${esc(okLabel)}</button></div>`);
    $("#cbNo").onclick = () => { closeModal(); resolve(false); };
    $("#cbYes").onclick = () => { closeModal(); resolve(true); };
  });
}

async function openDeleteRun(id) {
  let m;
  try { m = await api(`/api/runs/${enc(id)}/delete-impact`); } catch (e) { return toast(e.message, true); }
  const run = S.runs.find((r) => r.run_id === m.run_id);
  const when = run ? `${dayLabel(run.started_at)}, ${timeLabel(run.started_at)}` : "";
  const what = `<b>${esc(prettyBatch(m.inbox_name))}</b>${when ? ` (processed ${esc(when)})` : ""}<div class="small mono muted" style="margin-top:4px">Run ID: ${esc(m.run_id)}</div>`;
  if (m.blocked) {
    return modal(`
      <div class="modal-head"><h2>This run cannot be deleted</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
      <div class="modal-body"><p style="margin-top:0">${what}</p>
        <div class="banner warn">${icon("alert")}<div>${esc(m.blocked)}</div></div>
        <div class="group-label">Recorded after this run</div>
        <div class="small mono">${m.later_runs.map(esc).join("<br>")}</div></div>
      <div class="modal-foot"><button class="btn" onclick="closeModal()">Close</button></div>`);
  }
  const effects = m.recorded ? [
    `<b>${m.documents}</b> document record${m.documents === 1 ? "" : "s"} will be removed from the processed-invoice ledger.`,
    m.entered ? `<b>${m.entered}</b> bill${m.entered === 1 ? "" : "s"} recorded as entered or handed off (<b>${esc(money(+m.entered_amount))}</b>) will be removed. The duplicate check will no longer recognise ${m.entered === 1 ? "it" : "them"}, and ${m.entered === 1 ? "it" : "they"} can be processed again.` : "",
    "PO balances, lien waivers on file and superseded originals recorded by this run will be reverted.",
    "This action does <b>not</b> change Sage Intacct or Entrata. If the import file from this run was already loaded, reverse those entries in the ERP separately.",
  ] : ["This was a preview. Nothing was recorded in the ledger, so only the output files are affected."];
  modal(`
    <div class="modal-head"><h2>Delete run?</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
    <div class="modal-body">
      <p style="margin-top:0">You are about to delete the results of ${what}</p>
      <div class="banner warn" style="margin-bottom:12px">${icon("alert")}<div><b>Review the impact before continuing.</b></div></div>
      <ul class="impact">${effects.filter(Boolean).map((e) => `<li>${e}</li>`).join("")}</ul>
      <p class="small muted">${m.recorded ? "A ledger snapshot is saved before deletion, the output files are archived rather than erased, and the action is recorded in the audit log." : "The output files are archived rather than erased, and the action is recorded in the audit log."}</p>
      <div class="group-label">To confirm, type <span class="mono">DELETE</span></div>
      <input class="field" id="delConfirm" autocomplete="off" spellcheck="false">
    </div>
    <div class="modal-foot"><button class="btn" onclick="closeModal()">Cancel</button>
      <button class="btn destructive" id="delGo" disabled>${icon("trash", "sm")}Delete run</button></div>`);
  const inp = $("#delConfirm"), go = $("#delGo");
  inp.focus();
  inp.oninput = () => (go.disabled = inp.value.trim() !== "DELETE");
  go.onclick = async () => {
    go.disabled = true;
    try {
      const res = await api(`/api/runs/${enc(m.run_id)}`, { method: "DELETE", body: JSON.stringify({ confirm: "DELETE" }) });
      closeModal();
      await loadAll();
      if (location.hash.startsWith("#/run/")) location.hash = "#/"; else route();
      toast(res.ledger_snapshot ? `Run deleted. Ledger snapshot saved as ${res.ledger_snapshot}.` : "Preview deleted.");
    } catch (e) { toast(e.message, true); go.disabled = false; }
  };
}

async function watchJob(job, title, sub) {
  modal(`<div class="modal-head"><h2>${esc(title)}</h2></div>
    <div class="modal-body"><p class="muted" style="margin:0">${esc(sub || "")}</p>
      <div class="progress indet" id="jobBar"><span></span></div><div class="small muted" id="jobText">Starting…</div></div>`);
  for (;;) {
    await sleep(600);
    const j = await api(`/api/jobs/${job.id}`);
    const bar = $("#jobBar");
    if (bar && j.total) { bar.classList.remove("indet"); bar.firstElementChild.style.width = `${Math.round((100 * j.done) / j.total)}%`; }
    const t = $("#jobText");
    if (t) t.textContent = j.total ? `Read ${j.done} of ${j.total} · ${j.current}` : "Loading POs, contracts and master data…";
    if (j.status === "done") { closeModal(); return j.result; }
    if (j.status === "error") { closeModal(); throw new Error(j.error); }
  }
}

function openRunModal(preselect) {
  let sel = preselect ? (S.inboxes.find((b) => b.path === preselect || b.name === preselect)?.path || preselect) : (S.inboxes.find((b) => !b.runs)?.path || S.inboxes[0]?.path);
  const groups = {};
  for (const b of S.inboxes) (groups[b.group] ||= []).push(b);
  const draw = () => {
    const chosen = S.inboxes.find((b) => b.path === sel);
    modal(`
      <div class="modal-head"><h2>Run a batch</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
      <div class="modal-body">
        ${Object.entries(groups).map(([g, list]) => `<div class="group-label">${esc(g)}</div>${list.map((b) => `
          <div class="choice ${b.path === sel ? "on" : ""}" data-p="${esc(b.path)}">${icon("folder")}
            <div><div class="t">${esc(prettyBatch(b.name))}</div><div class="s">${b.docs} documents · <span class="mono">${esc(b.path)}</span></div></div>
            <div class="s">${b.runs ? `processed ${b.runs}×` : "new"}</div></div>`).join("")}`).join("")}
        <div class="group-label">Options</div>
        <label class="check"><input type="checkbox" id="optWhatIf"><div>Preview only<div class="s">Write the files but don't record anything in the ledger.</div></div></label>
        <label class="check"><input type="checkbox" id="optOffline"><div>Use saved AI readings only<div class="s">No API calls. Documents never read before are held as unavailable.</div></div></label>
        ${chosen?.runs ? `<div class="banner ok" style="margin:10px 0 0">${icon("shield")}<div>Already processed ${chosen.runs}×. Entered documents will show as <b>Already processed</b> and produce no new rows; held ones are re-checked.</div></div>` : ""}
      </div>
      <div class="modal-foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="goRun" ${sel ? "" : "disabled"}>${icon("play", "sm")}Run</button></div>`);
    $$(".choice").forEach((c) => (c.onclick = () => { sel = c.dataset.p; draw(); }));
    $("#goRun").onclick = async () => {
      const what_if = $("#optWhatIf").checked, offline = $("#optOffline").checked;
      try {
        const job = await post("/api/run", { inbox: sel, what_if, offline });
        const res = await watchJob(job, `Processing ${prettyBatch(sel.split("/").pop())}`, offline ? "Using saved readings." : "Claude reads new documents; saved readings are reused.");
        await loadAll();
        location.hash = `#/run/${enc(res.run_id)}`;
      } catch (e) { toast(e.message, true); }
    };
  };
  draw();
}

const READABLE = /\.(pdf|png|jpe?g|docx|zip)$/i;
const isJunk = (rel) => rel.split("/").some((p) => p.startsWith(".") || p === "__MACOSX") || /(^|\/)(thumbs\.db|desktop\.ini)$/i.test(rel);

// A dropped folder arrives as directory entries: walk them so every document inside is picked up.
async function walkEntry(entry, prefix = "") {
  if (entry.isFile) return [{ file: await new Promise((ok, no) => entry.file(ok, no)), rel: prefix + entry.name }];
  const reader = entry.createReader(), out = [];
  for (;;) {
    const batch = await new Promise((ok, no) => reader.readEntries(ok, no));
    if (!batch.length) break;
    for (const e of batch) out.push(...(await walkEntry(e, `${prefix}${entry.name}/`)));
  }
  return out;
}

function openImport() {
  let items = [], name = "";
  const add = (list) => {
    const seen = new Set(items.map((i) => i.rel));
    for (const i of list) if (!isJunk(i.rel) && !seen.has(i.rel)) { items.push(i); seen.add(i.rel); }
    const top = list.find((i) => i.rel.includes("/"))?.rel.split("/")[0];
    if (!name && top) name = top;
    draw();
  };
  const draw = () => {
    name = $("#batchName")?.value ?? name;
    const odd = items.filter((i) => !READABLE.test(i.rel)).length;
    const zips = items.filter((i) => /\.zip$/i.test(i.rel)).length;
    const shown = items.slice(0, 12);
    modal(`
      <div class="modal-head"><h2>Import documents</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
      <div class="modal-body">
        <div class="drop" id="drop">${icon("upload")}<div style="margin-top:8px"><b>Drop a folder, files or a .zip here</b></div>
          <div class="small">PDF, scanned images (PNG/JPG) and Word files. Sub-folders are included.</div>
          <div style="display:flex;gap:8px;justify-content:center;margin-top:12px">
            <button class="btn" id="pickFiles">${icon("upload", "sm")}Choose files</button>
            <button class="btn" id="pickFolder">${icon("folder", "sm")}Choose folder</button></div></div>
        <input type="file" id="fileIn" multiple hidden>
        <input type="file" id="dirIn" webkitdirectory multiple hidden>
        ${items.length ? `<div class="group-label" style="display:flex;justify-content:space-between">${items.length} file${items.length > 1 ? "s" : ""}${zips ? ` (${zips} .zip, unpacked on upload)` : ""}<a href="#" id="clearAll" class="small">Clear</a></div>
          <div class="small mono" style="max-height:160px;overflow:auto">${shown.map((i) => esc(i.rel)).join("<br>")}${items.length > shown.length ? `<br><span class="muted">…and ${items.length - shown.length} more</span>` : ""}</div>
          ${odd ? `<div class="banner warn" style="margin:10px 0 0">${icon("alert")}<div>${odd} file${odd > 1 ? "s are" : " is"} not PDF, image or Word. ${odd > 1 ? "They" : "It"} will be uploaded and held for a person as <b>can't read</b>, never guessed.</div></div>` : ""}` : ""}
        <div class="group-label">Batch name</div><input class="field" id="batchName" placeholder="e.g. november-week-1" value="${esc(name)}">
        <p class="muted small">Saved to <span class="mono">inbox/&lt;date&gt;_&lt;name&gt;/</span>. Nothing is processed until you run it.</p>
      </div>
      <div class="modal-foot"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" id="goUp" ${items.length ? "" : "disabled"}>${icon("upload", "sm")}Upload ${items.length || ""}</button></div>`);
    const drop = $("#drop"), inp = $("#fileIn"), dir = $("#dirIn");
    drop.onclick = () => inp.click();
    $("#pickFiles").onclick = (e) => { e.stopPropagation(); inp.click(); };
    $("#pickFolder").onclick = (e) => { e.stopPropagation(); dir.click(); };
    inp.onchange = () => add([...inp.files].map((f) => ({ file: f, rel: f.name })));
    dir.onchange = () => add([...dir.files].map((f) => ({ file: f, rel: f.webkitRelativePath || f.name })));
    if ($("#clearAll")) $("#clearAll").onclick = (e) => { e.preventDefault(); items = []; name = ""; $("#batchName").value = ""; draw(); };
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = async (e) => {
      e.preventDefault();
      const entries = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
      add(entries.length ? (await Promise.all(entries.map((en) => walkEntry(en)))).flat() : [...e.dataTransfer.files].map((f) => ({ file: f, rel: f.name })));
    };
    $("#goUp").onclick = async () => {
      const fd = new FormData();
      items.forEach((i) => fd.append("files", i.file, i.rel));
      fd.append("name", $("#batchName").value);
      $("#goUp").disabled = true;
      $("#goUp").textContent = `Uploading ${items.length}…`;
      try {
        const res = await api("/api/upload", { method: "POST", body: fd });
        S.inboxes = await api("/api/inboxes");
        renderSidebar();
        toast(`Uploaded ${res.files.length} document${res.files.length > 1 ? "s" : ""}`);
        openRunModal(res.path);
      } catch (e) { toast(e.message, true); draw(); }
    };
  };
  draw();
}

async function openStatus(ping = false) {
  modal(`<div class="modal-head"><h2>System check</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
    <div class="modal-body"><div class="progress indet"><span></span></div><div class="small muted">${ping ? "Calling Claude…" : "Checking…"}</div></div>`);
  try {
    const st = await api(`/api/status?ping=${ping}`);
    S.status = st;
    renderSidebar();
    modal(`<div class="modal-head"><h2>System check</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
      <div class="modal-body">${st.checks.map((c) => `<div class="check-line"><span class="mk ${c.ok ? "ok" : "bad"}">${c.ok ? "✓" : "✕"}</span><div>${esc(c.message)}${!c.ok && c.fix ? `<div class="muted small">→ ${esc(c.fix)}</div>` : ""}</div></div>`).join("")}</div>
      <div class="modal-foot"><span class="muted small" style="margin-right:auto">${st.ok ? "Ready." : "Fix the ✕ items."}</span>
        <button class="btn" onclick="openStatus(true)">${icon("sparkle", "sm")}Test AI connection</button><button class="btn primary" onclick="closeModal()">Done</button></div>`);
  } catch (e) { closeModal(); toast(e.message, true); }
}

async function openCompare(id) {
  const others = S.runs.filter((x) => x.run_id !== id);
  modal(`<div class="modal-head"><h2>Compare with another run</h2><button class="icon-btn" onclick="closeModal()">${icon("x")}</button></div>
    <div class="modal-body"><select class="field" id="cmpSel">${others.map((o) => `<option value="${esc(o.run_id)}">${esc(prettyBatch(o.inbox_name))}${o.what_if ? " (preview)" : ""} · ${esc(dayLabel(o.started_at))} ${esc(timeLabel(o.started_at))}</option>`).join("")}</select>
      <div id="cmpOut" style="margin-top:14px"></div></div>`, "wide");
  const show = async () => {
    const d = await api(`/api/diff?a=${enc($("#cmpSel").value)}&b=${enc(id)}`);
    $("#cmpOut").innerHTML = `<p><b>${d.changes.length} document${d.changes.length === 1 ? "" : "s"} changed</b>, ${d.unchanged} unchanged.</p>
      ${d.changes.length ? `<div class="table-wrap"><table><thead><tr><th>Document</th><th>Before</th><th>After</th><th>What changed</th></tr></thead><tbody>
      ${d.changes.map((c) => `<tr><td>${esc(c.file_name)}</td><td>${esc(c.before)}</td><td>${esc(c.after)}</td><td class="small">${c.why.map(esc).join("<br>")}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
  };
  $("#cmpSel").onchange = show;
  show();
}

// ⌘K search palette
function openPalette() {
  $("#overlay").innerHTML = `<div class="scrim" onclick="if(event.target===this) closeModal()"><div class="palette">
    <input id="palIn" placeholder="Search by invoice number, vendor, file, project or code (e.g. OVERPO)" autocomplete="off">
    <div class="res" id="palRes"></div></div></div>`;
  const inp = $("#palIn");
  let hits = [], sel = 0, timer;
  const shortcuts = [
    { label: "Run a batch", act: () => openRunModal() }, { label: "Open exceptions", act: () => (location.hash = "#/exceptions") },
    { label: "Change a rule", act: () => (location.hash = "#/rules") }, { label: "Ledger & reruns", act: () => (location.hash = "#/ledger") },
  ];
  const draw = () => {
    const list = inp.value.trim() ? hits : shortcuts;
    $("#palRes").innerHTML = list.length ? list.map((h, i) => h.file_name
      ? `<div class="hit ${i === sel ? "sel" : ""}" data-i="${i}"><div><b>${esc(h.vendor_name || h.file_name)}</b> <span class="mono">${esc(h.bill_no || "")}</span></div><div>${pill(h.decision)}</div>
         <div class="s">${esc(h.file_name)} · ${esc(prettyBatch(h.inbox_name))} ${h.codes.length ? "· " + esc(h.codes.join(", ")) : ""}</div><div class="s" style="text-align:right">${money(h.amount)}</div></div>`
      : `<div class="hit ${i === sel ? "sel" : ""}" data-i="${i}"><div>${esc(h.label)}</div></div>`).join("")
      : `<div class="hit"><div class="muted">No matches</div></div>`;
    $$(".hit[data-i]").forEach((el) => (el.onclick = () => go(Number(el.dataset.i))));
  };
  const go = (i) => {
    const list = inp.value.trim() ? hits : shortcuts;
    const h = list[i];
    if (!h) return;
    closeModal();
    if (h.file_name) location.hash = `#/doc/${enc(h.run_id)}/${enc(h.file_name)}`; else h.act();
  };
  inp.oninput = () => { clearTimeout(timer); timer = setTimeout(async () => { hits = await api(`/api/search?q=${enc(inp.value)}`); sel = 0; draw(); }, 140); };
  inp.onkeydown = (e) => {
    const n = (inp.value.trim() ? hits : shortcuts).length;
    if (e.key === "ArrowDown") { sel = Math.min(n - 1, sel + 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); draw(); e.preventDefault(); }
    else if (e.key === "Enter") go(sel);
    else if (e.key === "Escape") closeModal();
  };
  draw();
  inp.focus();
}
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
  else if (e.key === "Escape" && $("#overlay").innerHTML) closeModal();
});

// ------------------------------------------------------------------------------------------- guided tour
function tourSteps() {
  const t = store.get("tour", {});
  const b1 = S.runs.filter((r) => r.inbox_name === "01_Invoice_Batch_01" && !r.what_if);
  return [
    { t: "Run Batch 01", s: "See the Intacct import, Entrata handoff and exceptions.", done: b1.length > 0, act: () => openRunModal("01_Invoice_Batch_01") },
    { t: "Open a held invoice", s: "Read why, in plain English, next to the document.", done: !!t.exception, act: () => (location.hash = "#/exceptions") },
    { t: "Rerun the same batch", s: "Nothing is entered twice.", done: b1.some((r) => r.summary.by_decision.ALREADY_PROCESSED), act: () => openRunModal("01_Invoice_Batch_01") },
    { t: "Preview a rule change", s: "e.g. Over-PO tolerance $500 → $1,500.", done: !!t.rule, act: () => (location.hash = "#/rules") },
  ];
}
function renderTour() {
  let el = $(".tour");
  if (!el) { el = document.createElement("div"); el.className = "tour"; document.body.appendChild(el); }
  const steps = tourSteps();
  const n = steps.filter((x) => x.done).length;
  const open = store.get("tourOpen", false);
  if (store.get("tourHidden", false)) { el.innerHTML = ""; return; }
  el.innerHTML = `
    ${open ? `<div class="tour-card"><div class="row" style="justify-content:space-between"><h4>Get started</h4><button class="icon-btn" title="Hide" onclick="store.set('tourHidden', true); renderTour()">${icon("x", "sm")}</button></div>
      <p class="muted small" style="margin:0 0 8px">Four steps that show what the system does.</p>
      ${steps.map((x, i) => `<div class="tour-step ${x.done ? "done" : ""}" data-i="${i}"><span class="box">${x.done ? icon("check", "sm") : ""}</span><div><div class="tt">${esc(x.t)}</div><div class="s">${esc(x.s)}</div></div></div>`).join("")}</div>` : ""}
    <button class="tour-btn" onclick="store.set('tourOpen', ${!open}); renderTour()"><span class="ring" style="--p:${(100 * n) / steps.length}"><span>${n}/${steps.length}</span></span>Get started</button>`;
  $$(".tour-step", el).forEach((s) => (s.onclick = () => { store.set("tourOpen", false); renderTour(); steps[Number(s.dataset.i)].act(); }));
}

// ------------------------------------------------------------------------------------------- boot
(async () => {
  renderTopbar();
  try { await loadAll(); } catch (e) { toast("Couldn't reach the server: " + e.message, true); }
  route();
})();
