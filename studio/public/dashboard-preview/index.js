/*
  SupremeAI Studio — Dashboard Preview logic (issue #337).
  Zero-dependency vanilla JS reference renderer for api-schemas/dashboard.schema.json.

  Boot contract (fail-closed):
    1. validateSnapshot() checks the embedded DashboardSnapshot against the
       schema's core constraints (closed enums, bounds, RFC 3339 instants,
       required fields, additionalProperties rejection).
    2. On any violation the dashboard refuses to render and shows the error
       banner — untrustworthy data never reaches the surface.
    3. On success it renders federation + telemetry cards, wires the live
       SSE/Simulation engine, and manages dark/light theme switching.

  DOM writes are textContent-only by construction (no innerHTML), so card
  content cannot inject markup.
*/
"use strict";

/* -------------------------------------------------------------------------
 * Embedded DashboardSnapshot — conforms to api-schemas/dashboard.schema.json
 * (validated by scripts/validate_schemas.py in CI; re-checked at boot below).
 * ----------------------------------------------------------------------- */
const SNAPSHOT = {
  schema_version: "1.0",
  generated_at: "2026-10-16T08:00:00Z",
  tokens: {
    color: {
      bg_base: "#0a0f0d",
      surface_glass: "rgba(22, 32, 27, 0.58)",
      surface_border: "rgba(148, 233, 194, 0.14)",
      text_primary: "#eef7f2",
      text_secondary: "#9db8ab",
      accent: "#10b981",
      accent_soft: "#2dd4bf",
      success: "#34d399",
      warning: "#f59e0b",
      danger: "#f87171",
    },
    typography: {
      font_sans: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
      font_mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      scale: [
        { token: "display", size: "2.2rem" },
        { token: "title", size: "1.3rem" },
        { token: "body", size: "0.95rem" },
        { token: "caption", size: "0.78rem" },
      ],
    },
    radius: { sm: "8px", md: "14px", lg: "22px" },
    motion: { duration_fast: "140ms", duration_base: "320ms", easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
  },
  federation: {
    repos: [
      { name: "supremeai-open", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 14, last_sync: "2026-10-16T07:58:00Z" },
      { name: "supremeai", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 16, last_sync: "2026-10-16T07:13:16Z" },
      { name: "supremeai-core", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 5, last_sync: "2026-10-16T07:00:00Z" },
      { name: "supremeai-mcp-control-plane", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 4, last_sync: "2026-10-16T07:10:00Z" },
      { name: "supremeai-command", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 2, last_sync: "2026-10-16T06:45:00Z" },
      { name: "supremeai-skills", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 3, last_sync: "2026-10-16T06:50:00Z" },
      { name: "supremeai-vscode", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 2, last_sync: "2026-10-16T06:55:00Z" },
      { name: "supremeai-agents", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 3, last_sync: "2026-10-16T07:05:00Z" },
      { name: "supremeai-browser", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 2, last_sync: "2026-10-16T07:02:00Z" },
      { name: "supremeai-api", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 6, last_sync: "2026-10-16T07:12:00Z" },
      { name: "supremeai-studio", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 2, last_sync: "2026-10-16T07:55:00Z" },
      { name: "supremeai-sdk", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 3, last_sync: "2026-10-16T07:15:00Z" },
    ],
  },
  agents: [
    { agent_id: "agent-antigravity", state: "working", task_id: "337", current_issue: "studio glassmorphism dashboard + SSE", progress: 85, tokens_used: 124350, events_per_min: 44.2, last_event: "2026-10-16T07:59:45Z" },
    { agent_id: "agent-monorepo-core", state: "working", task_id: "329", current_issue: "smart context selector L1-8 assembly", progress: 40, tokens_used: 82100, events_per_min: 28.5, last_event: "2026-10-16T07:58:30Z" },
    { agent_id: "agent-router-engine", state: "working", task_id: "330", current_issue: "dynamic task router fallback cascade", progress: 30, tokens_used: 61400, events_per_min: 22.0, last_event: "2026-10-16T07:57:12Z" },
    { agent_id: "agent-mcp-guard", state: "waiting", task_id: "340", current_issue: "persistent emergency kill switch r3", progress: 95, tokens_used: 48900, events_per_min: 8.4, last_event: "2026-10-16T07:56:50Z" },
    { agent_id: "agent-gateway-stream", state: "waiting", task_id: "336", current_issue: "live SSE and HTTP streaming handlers", progress: 20, tokens_used: 31200, events_per_min: 15.6, last_event: "2026-10-16T07:55:20Z" },
    { agent_id: "agent-vscode-dev", state: "done", task_id: "303", current_issue: "federation topology documentation", progress: 100, tokens_used: 18450, events_per_min: 0.0, last_event: "2026-10-16T07:24:19Z" },
  ],
};

/* -------------------------------------------------------------------------
 * Fail-closed runtime validation (mirror of the schema's core constraints)
 * ----------------------------------------------------------------------- */
const RFC3339 = /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/;
const HEX = /^#[0-9a-fA-F]{6}$/;
const RGBA = /^rgba\((?:\d{1,3}, ){2}\d{1,3}, (?:0\.\d{1,3}|[01])\)$/;
const STATES = new Set(["working", "waiting", "blocked", "done", "error"]);
const HEALTH = new Set(["healthy", "degraded", "down", "unknown"]);
const CI = new Set(["passing", "failing", "running", "unknown"]);

class SchemaViolation extends Error {}

function assert(cond, msg) {
  if (!cond) throw new SchemaViolation(msg);
}
function isObj(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
function intIn(v, lo, hi, name) {
  assert(Number.isInteger(v) && v >= lo && v <= hi, `${name} out of bounds: ${v}`);
}
function exactKeys(obj, keys, name) {
  assert(isObj(obj), `${name} must be an object`);
  const extra = Object.keys(obj).filter((k) => !keys.includes(k));
  assert(extra.length === 0, `${name}: unknown fields [${extra}] (additionalProperties false)`);
  for (const k of keys) assert(k in obj, `${name}: missing required field '${k}'`);
}

function validateSnapshot(s) {
  exactKeys(s, ["schema_version", "generated_at", "tokens", "federation", "agents"], "snapshot");
  assert(/^\d+\.\d+$/.test(s.schema_version), "bad schema_version");
  assert(RFC3339.test(s.generated_at), "generated_at not RFC3339");

  const t = s.tokens;
  exactKeys(t, ["color", "typography", "radius", "motion"], "tokens");
  const c = t.color;
  exactKeys(c, ["bg_base", "surface_glass", "surface_border", "text_primary", "text_secondary", "accent", "accent_soft", "success", "warning", "danger"], "tokens.color");
  for (const k of ["bg_base", "text_primary", "text_secondary", "accent", "accent_soft", "success", "warning", "danger"]) {
    assert(HEX.test(c[k]), `tokens.color.${k} not hex`);
  }
  for (const k of ["surface_glass", "surface_border"]) assert(RGBA.test(c[k]), `tokens.color.${k} not rgba`);

  exactKeys(t.typography, ["font_sans", "font_mono", "scale"], "tokens.typography");
  assert(t.typography.scale.length >= 3, "type scale too small");
  for (const e of t.typography.scale) {
    exactKeys(e, ["token", "size"], "scale entry");
    assert(/^[a-z][a-z0-9-]{1,31}$/.test(e.token) && /^\d+(\.\d+)?(px|rem)$/.test(e.size), "bad scale entry");
  }

  exactKeys(t.radius, ["sm", "md", "lg"], "tokens.radius");
  for (const k of ["sm", "md", "lg"]) assert(/^\d+(px|rem)$/.test(t.radius[k]), `radius.${k}`);

  exactKeys(t.motion, ["duration_fast", "duration_base", "easing"], "tokens.motion");
  assert(/^\d+ms$/.test(t.motion.duration_fast) && /^\d+ms$/.test(t.motion.duration_base), "bad motion duration");
  assert(/^(ease|ease-in|ease-out|ease-in-out|linear|cubic-bezier\([0-9.]+, [0-9.]+, [0-9.]+, [0-9.]+\))$/.test(t.motion.easing), "bad easing");

  exactKeys(s.federation, ["repos"], "federation");
  assert(Array.isArray(s.federation.repos) && s.federation.repos.length >= 1, "federation.repos empty");
  for (const r of s.federation.repos) {
    exactKeys(r, ["name", "health", "ci_status", "open_prs", "open_issues", "last_sync"], `repo ${r.name}`);
    assert(/^[A-Za-z0-9_.-]{1,100}$/.test(r.name), "bad repo name");
    assert(HEALTH.has(r.health) && CI.has(r.ci_status), "bad repo enum");
    intIn(r.open_prs, 0, 10000, "open_prs");
    intIn(r.open_issues, 0, 10000, "open_issues");
    assert(RFC3339.test(r.last_sync), "repo last_sync not RFC3339");
  }

  assert(Array.isArray(s.agents) && s.agents.length <= 64, "agents array bad");
  for (const a of s.agents) {
    exactKeys(a, ["agent_id", "state", "progress", "tokens_used", "last_event", "task_id", "current_issue", "events_per_min"], `agent ${a.agent_id}`);
    assert(/^agent-[a-zA-Z0-9_-]{1,64}$/.test(a.agent_id), "bad agent_id");
    assert(STATES.has(a.state), "bad agent state");
    intIn(a.progress, 0, 100, "progress");
    intIn(a.tokens_used, 0, 100000000, "tokens_used");
    assert(RFC3339.test(a.last_event), "agent last_event not RFC3339");
    if ("events_per_min" in a) {
      assert(typeof a.events_per_min === "number" && a.events_per_min >= 0 && a.events_per_min <= 10000, "events_per_min bounds");
    }
  }
}

/* -------------------------------------------------------------------------
 * DOM Utilities (textContent-only DOM writes)
 * ----------------------------------------------------------------------- */
const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function badge(value) {
  return el("span", `badge ${value}`, value);
}

function line(label, value) {
  const row = el("div", "card-line");
  const lab = el("span", null, label);
  const val = el("span", "mono", value);
  row.append(lab, val);
  return row;
}

function formatTokens(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(2)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function timeAgo(rfc3339) {
  const then = new Date(rfc3339).getTime();
  if (Number.isNaN(then)) return rfc3339;
  const s = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

/* -------------------------------------------------------------------------
 * Renderers
 * ----------------------------------------------------------------------- */
function renderRepo(repo) {
  const card = el("article", "card repo-card");
  const head = el("div", "card-head");
  head.append(el("h3", "card-title", repo.name), badge(repo.ci_status));
  card.append(head);
  card.append(line("health", repo.health), line("open PRs", String(repo.open_prs)), line("open issues", String(repo.open_issues)));
  card.append(line("last sync", timeAgo(repo.last_sync)));
  return card;
}

function renderAgent(agent) {
  const card = el("article", "card agent-card");
  card.dataset.state = agent.state;
  const head = el("div", "card-head");
  head.append(el("h3", "card-title", agent.agent_id), badge(agent.state));
  card.append(head);
  if (agent.current_issue) card.append(line("objective", agent.current_issue));
  if (agent.task_id) card.append(line("task", `#${agent.task_id}`));
  card.append(line("tokens", formatTokens(agent.tokens_used)));
  if (typeof agent.events_per_min === "number") {
    card.append(line("events/min", agent.events_per_min.toFixed(1)));
  }
  card.append(line("last event", timeAgo(agent.last_event)));

  const track = el("div", "progress");
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", `${agent.agent_id} progress`);
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", "100");
  track.setAttribute("aria-valuenow", String(agent.progress));
  const bar = el("div", "progress-bar");
  bar.style.width = `${agent.progress}%`;
  track.append(bar);
  card.append(track);
  return card;
}

function updateMeters(s) {
  const activeCount = s.agents.filter((a) => a.state === "working").length;
  const totalTokens = s.agents.reduce((sum, a) => sum + (a.tokens_used || 0), 0);
  const totalEvents = s.agents.reduce((sum, a) => sum + (a.events_per_min || 0), 0);

  const activeEl = $("metric-active-agents");
  if (activeEl) activeEl.textContent = String(activeCount);

  const tokensEl = $("metric-total-tokens");
  if (tokensEl) tokensEl.textContent = formatTokens(totalTokens);

  const eventsEl = $("metric-events-min");
  if (eventsEl) eventsEl.textContent = totalEvents.toFixed(1);
}

function renderAll(s) {
  const repos = $("repos");
  if (repos) {
    repos.replaceChildren(...s.federation.repos.map(renderRepo));
    $("repo-count").textContent = `(${s.federation.repos.length})`;
  }

  const agents = $("agents");
  if (agents) {
    agents.replaceChildren(...s.agents.map(renderAgent));
    $("agent-count").textContent = `(${s.agents.length})`;
  }

  updateMeters(s);

  const snapEl = $("snapshot-id");
  if (snapEl) snapEl.textContent = `${s.schema_version} @ ${s.generated_at}`;

  const genEl = $("generated-at");
  if (genEl) genEl.textContent = new Date(s.generated_at).toLocaleTimeString();
}

/* -------------------------------------------------------------------------
 * Event Terminal Feed
 * ----------------------------------------------------------------------- */
const MAX_FEED_EVENTS = 50;
let eventCounter = 0;

function appendFeedEvent(tag, message) {
  const feed = $("event-feed");
  if (!feed) return;

  eventCounter++;
  const time = new Date().toISOString().slice(11, 19);

  const row = el("div", "event-line");
  row.append(
    el("span", "event-time", `[${time}]`),
    el("span", "event-tag", `[${tag}]`),
    el("span", "event-msg", message)
  );

  feed.prepend(row);

  while (feed.children.length > MAX_FEED_EVENTS) {
    feed.lastElementChild.remove();
  }

  const countEl = $("event-count");
  if (countEl) countEl.textContent = `(${eventCounter} events)`;
}

/* -------------------------------------------------------------------------
 * Theme Management (Dark / Light Mode)
 * ----------------------------------------------------------------------- */
const THEME_KEY = "supremeai-studio-theme";

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = saved || (prefersDark ? "dark" : "light");
  setTheme(initialTheme);

  const toggleBtn = $("theme-toggle-btn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const current = document.documentElement.dataset.theme;
      const next = current === "dark" ? "light" : "dark";
      setTheme(next);
      appendFeedEvent("THEME", `Theme toggled to ${next.toUpperCase()}`);
    });
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
  const icon = $("theme-icon");
  if (icon) {
    icon.textContent = theme === "dark" ? "☀️" : "🌙";
  }
}

/* -------------------------------------------------------------------------
 * Filters (keyboard-operable, aria-pressed)
 * ----------------------------------------------------------------------- */
let activeFilter = "all";

function applyFilter() {
  const agentsContainer = $("agents");
  if (!agentsContainer) return;
  for (const card of agentsContainer.children) {
    const show = activeFilter === "all" || card.dataset.state === activeFilter;
    card.hidden = !show;
  }
}

function wireFilters() {
  const buttons = document.querySelectorAll(".filter");
  for (const btn of buttons) {
    btn.addEventListener("click", () => {
      activeFilter = btn.dataset.filter;
      for (const b of buttons) {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", String(on));
      }
      applyFilter();
      appendFeedEvent("FILTER", `Agent filter set to: ${activeFilter.toUpperCase()}`);
    });
  }
}

/* -------------------------------------------------------------------------
 * Live SSE & Simulation Engine
 * ----------------------------------------------------------------------- */
const TOWER_SSE_URL = "https://supremeai-mcp-tower.onrender.com/sse";
let isLiveSSE = false;
let sseConnection = null;
let simInterval = null;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const TICK_MS = 1600;

function tickSimulation() {
  for (const a of SNAPSHOT.agents) {
    if (a.state === "working") {
      a.progress = Math.min(100, a.progress + 1 + Math.floor(Math.random() * 3));
      if (a.progress === 100) {
        a.state = "done";
        appendFeedEvent("TASK_DONE", `${a.agent_id} completed task #${a.task_id}`);
      }
    } else if (a.state === "done" && Math.random() < 0.15) {
      a.state = "working";
      a.progress = 5;
      appendFeedEvent("TASK_ASSIGN", `${a.agent_id} assigned new execution unit`);
    }
    a.tokens_used += 120 + Math.floor(Math.random() * 450);
    a.events_per_min = Math.max(0, +(a.events_per_min + (Math.random() - 0.5) * 2.5).toFixed(1));
    a.last_event = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  SNAPSHOT.generated_at = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  renderAll(SNAPSHOT);
  applyFilter();
}

function startSimulation() {
  if (simInterval) clearInterval(simInterval);
  simInterval = setInterval(tickSimulation, reducedMotion ? 6000 : TICK_MS);
  const pill = $("status-pill");
  if (pill) {
    pill.textContent = "SIMULATION";
    pill.className = "pill";
  }
  const sourceLabel = $("stream-source-label");
  if (sourceLabel) sourceLabel.textContent = "Source: Local High-Fidelity Simulation";
  appendFeedEvent("ENGINE", "Simulation loop running (1.6s cycle)");
}

function stopSimulation() {
  if (simInterval) {
    clearInterval(simInterval);
    simInterval = null;
  }
}

function connectLiveSSE() {
  stopSimulation();
  const pill = $("status-pill");
  const sourceLabel = $("stream-source-label");

  if (pill) {
    pill.textContent = "CONNECTING";
    pill.className = "pill warning";
  }
  if (sourceLabel) sourceLabel.textContent = `Connecting to ${TOWER_SSE_URL}...`;
  appendFeedEvent("SSE_CONN", `Opening stream to ${TOWER_SSE_URL}`);

  try {
    sseConnection = new EventSource(TOWER_SSE_URL);

    sseConnection.onopen = () => {
      isLiveSSE = true;
      if (pill) {
        pill.textContent = "LIVE SSE";
        pill.className = "pill healthy";
      }
      if (sourceLabel) sourceLabel.textContent = "Source: Live Remote MCP Tower SSE Stream";
      appendFeedEvent("SSE_OPEN", "Connected to SupremeAI MCP Tower event stream");
    };

    sseConnection.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        appendFeedEvent("SSE_DATA", `Telemetry frame: ${JSON.stringify(data).slice(0, 60)}...`);
        // If snapshot payload is received, re-validate and render
        if (data && data.agents && data.federation) {
          validateSnapshot(data);
          renderAll(data);
        }
      } catch {
        appendFeedEvent("SSE_FRAME", `Stream ping: ${event.data.slice(0, 40)}`);
      }
    };

    sseConnection.onerror = () => {
      appendFeedEvent("SSE_WARN", "Remote SSE unavailable (CORS/offline); failing over to simulation");
      disconnectSSE();
      startSimulation();
    };
  } catch (err) {
    appendFeedEvent("SSE_ERR", `EventSource failed: ${err.message}`);
    disconnectSSE();
    startSimulation();
  }
}

function disconnectSSE() {
  if (sseConnection) {
    sseConnection.close();
    sseConnection = null;
  }
  isLiveSSE = false;
}

function wireSSEControls() {
  const toggleBtn = $("sse-toggle-btn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      if (isLiveSSE) {
        disconnectSSE();
        startSimulation();
      } else {
        connectLiveSSE();
      }
    });
  }

  const clearBtn = $("clear-events-btn");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const feed = $("event-feed");
      if (feed) feed.replaceChildren();
      eventCounter = 0;
      const countEl = $("event-count");
      if (countEl) countEl.textContent = "(0 events)";
    });
  }
}

function startClock() {
  const clock = $("clock");
  if (!clock) return;
  const show = () => {
    clock.textContent = new Date().toISOString().slice(11, 19) + " UTC";
  };
  show();
  setInterval(show, 1000);
}

/* -------------------------------------------------------------------------
 * Boot Lifecycle (Fail-closed)
 * ----------------------------------------------------------------------- */
function boot() {
  try {
    validateSnapshot(SNAPSHOT);
  } catch (err) {
    const banner = $("error-banner");
    if (banner) {
      banner.hidden = false;
      banner.textContent = `Fail-closed: embedded snapshot violates dashboard.schema.json — ${err.message}`;
    }
    const pill = $("status-pill");
    if (pill) pill.textContent = "INVALID";
    return; // Refuse to render untrustworthy data
  }

  initTheme();
  renderAll(SNAPSHOT);
  wireFilters();
  wireSSEControls();
  startClock();
  startSimulation();

  appendFeedEvent("BOOT", "Dashboard initialized successfully (100% schema conformant)");

  // Assertions for verification
  console.assert($("repos").children.length === SNAPSHOT.federation.repos.length, "All repos rendered");
  console.assert($("agents").children.length === SNAPSHOT.agents.length, "All agents rendered");
  console.assert(document.querySelector(".filter[aria-pressed='true']") !== null, "Filter active");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
