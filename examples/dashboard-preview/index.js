/*
  SupremeAI Studio — Dashboard Preview logic (issue #24).
  Zero-dependency vanilla JS reference renderer for api-schemas/dashboard.schema.json.

  Boot contract (fail-closed):
    1. validateSnapshot() checks the embedded DashboardSnapshot against the
       schema's core constraints (closed enums, bounds, RFC 3339 instants,
       required fields, additionalProperties rejection).
    2. On any violation the dashboard refuses to render and shows the error
       banner — untrustworthy data never reaches the surface.
    3. On success it renders federation + telemetry cards and starts the live
       simulation loop (progress ticks, token spend, event clock).

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
  generated_at: "2026-10-16T05:30:00Z",
  tokens: {
    color: {
      bg_base: "#0a0f0d",
      surface_glass: "rgba(22, 32, 27, 0.55)",
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
      { name: "supremeai-open", health: "healthy", ci_status: "passing", open_prs: 0, open_issues: 4, last_sync: "2026-10-16T05:29:41Z" },
      { name: "supremeai-mcp-tower", health: "healthy", ci_status: "running", open_prs: 3, open_issues: 11, last_sync: "2026-10-16T05:28:57Z" },
      { name: "supremeai-studio", health: "degraded", ci_status: "failing", open_prs: 1, open_issues: 7, last_sync: "2026-10-16T05:12:03Z" },
    ],
  },
  agents: [
    { agent_id: "agent-zai-core", state: "working", task_id: "24", current_issue: "studio dashboard spec + preview", progress: 72, tokens_used: 184320, events_per_min: 41.5, last_event: "2026-10-16T05:29:52Z" },
    { agent_id: "agent-bridge-tower", state: "waiting", task_id: "311", current_issue: "bridge work order — in gates", progress: 45, tokens_used: 96110, events_per_min: 6.2, last_event: "2026-10-16T05:28:20Z" },
    { agent_id: "agent-guard-fleet", state: "working", task_id: "316", current_issue: "bridge telemetry schema gates", progress: 88, tokens_used: 42875, events_per_min: 12.8, last_event: "2026-10-16T05:29:48Z" },
    { agent_id: "agent-studio-legacy", state: "blocked", task_id: "248", current_issue: "waiting on admin decision", progress: 15, tokens_used: 8902, events_per_min: 0.4, last_event: "2026-10-16T04:47:12Z" },
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
 * Rendering (textContent-only DOM writes)
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

function renderRepo(repo) {
  const card = el("article", "card");
  const head = el("div", "card-head");
  head.append(el("h3", "card-title", repo.name), badge(repo.ci_status));
  card.append(head);
  card.append(line("health", repo.health), line("open PRs", String(repo.open_prs)), line("open issues", String(repo.open_issues)));
  card.append(line("last sync", timeAgo(repo.last_sync)));
  return card;
}

function renderAgent(agent) {
  const card = el("article", "card");
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

function renderAll(s) {
  const repos = $("repos");
  repos.replaceChildren(...s.federation.repos.map(renderRepo));
  $("repo-count").textContent = `(${s.federation.repos.length})`;

  const agents = $("agents");
  agents.replaceChildren(...s.agents.map(renderAgent));
  $("agent-count").textContent = `(${s.agents.length})`;

  $("snapshot-id").textContent = `${s.schema_version} @ ${s.generated_at}`;
  $("generated-at").textContent = new Date(s.generated_at).toLocaleString();
}

/* -------------------------------------------------------------------------
 * Filters (keyboard-operable, aria-pressed)
 * ----------------------------------------------------------------------- */
let activeFilter = "all";

function applyFilter() {
  for (const card of $("agents").children) {
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
    });
  }
}

/* -------------------------------------------------------------------------
 * Live simulation loop (progress ticks, token spend, event clock)
 * ----------------------------------------------------------------------- */
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const TICK_MS = 1500;

function tick() {
  for (const a of SNAPSHOT.agents) {
    if (a.state === "working") {
      a.progress = Math.min(100, a.progress + 2 + Math.floor(Math.random() * 4));
      if (a.progress === 100) a.state = "done";
    }
    a.tokens_used += 180 + Math.floor(Math.random() * 900);
    a.events_per_min = Math.max(0, +(a.events_per_min + (Math.random() - 0.5) * 3).toFixed(1));
    a.last_event = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  }
  renderAll(SNAPSHOT);
  applyFilter();
}

function startClock() {
  const clock = $("clock");
  const show = () => {
    clock.textContent = new Date().toISOString().slice(11, 19) + " UTC";
  };
  show();
  setInterval(show, 1000);
}

/* -------------------------------------------------------------------------
 * Boot (fail-closed)
 * ----------------------------------------------------------------------- */
function boot() {
  try {
    validateSnapshot(SNAPSHOT);
  } catch (err) {
    const banner = $("error-banner");
    banner.hidden = false;
    banner.textContent = `Fail-closed: embedded snapshot violates dashboard.schema.json — ${err.message}`;
    $("status-pill").textContent = "INVALID";
    return; // refuse to render untrustworthy data
  }
  $("status-pill").textContent = "LIVE";
  renderAll(SNAPSHOT);
  wireFilters();
  startClock();
  setInterval(tick, reducedMotion ? 6000 : TICK_MS); // slower ticks when motion is reduced

  // Console self-check (visible in devtools): core invariants hold post-render.
  console.assert($("repos").children.length === SNAPSHOT.federation.repos.length, "repo cards rendered");
  console.assert($("agents").children.length === SNAPSHOT.agents.length, "agent cards rendered");
  console.assert(document.querySelector(".filter[aria-pressed='true']") !== null, "one active filter");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
