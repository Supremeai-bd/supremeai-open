#!/usr/bin/env python3
"""Redis quota monitor — 80% Telegram warning for the Upstash account chain (#1522 / Q1).

বাংলা মন্তব্য: Upstash free-tier চেইনের যেকোনো account মাসিক কোটার 80% ছুঁলে
Telegram-এ একটি সতর্কতা যাবে (95% হলে CRITICAL)। উদ্দেশ্য — 500k সিলিং ভাঙার
*আগেই* মানুষ/অ্যাডমিন জানবে, কারণ tower-এর 96% preemptive rotation (#646)
কেবল ট্রাফিক অন্য account-এ সরায়, কিন্তু "কোটা শেষ হচ্ছে" সংবাদটি কাউকে দেয় না।

#1698 D1 addition — burn-rate projection + chain-depth alert:
  The 2026-10-27 incident showed WHY per-account pct is not enough: primary+secondary
  hit the wall while the ACTIVE tertiary sat at 0% (silent under any pct threshold).
  Two additions, both pure functions, both honest-None:
    1. [BURN]  per-window usage snapshots in the state file → commands/hour for the
       ACTIVE account → projected usage at the window reset; fires when the projection
       crosses the soft threshold (usage.softThreshold, else limit*warn%) BEFORE reset.
       First run after deploy = baseline only (insufficient history is printed, never
       fabricated — U2).
    2. [DEPTH] failover-chain capacity: fires when the active link is the ONLY
       non-quota-blocked link (one_deep, warn) or when NO link is available (crit).
       Never touches rotation itself (D4: failover behavior is load-bearing).

Data honesty (U2 tiering):
  1. PRIMARY source: the running tower's own `redis_rotation_status` MCP tool —
     the same in-memory usage estimates (noteRedisCommands lower bound + quota
     error-body corrections) that drive live rotation. No fabricated numbers:
     if the tower is unreachable the monitor SKIPS (exit 0, honest skip) instead
     of inventing usage. Set REDIS_QUOTA_STRICT=1 to turn tower-unreachable
     into exit 3 for cron alerting on monitor failures.
  2. The estimates are a LOWER bound (other services may share the account);
     the message reports the tower's own view, not a fabricated total.

Deduplication: one alert per (account, tier) per quota window, persisted in a
small JSON state file — repeated cron runs never spam Telegram.

Stdlib-only, zero dependencies, cron-friendly exit codes:
  0 = ok / skipped / no alert   1 = warning sent (threshold warn, [BURN] or [DEPTH])
  2 = critical sent (threshold crit or zero-available chain)   3 = strict-mode fetch failure
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone

DEFAULT_TOWER_URL = "https://supremeai-mcp-tower.onrender.com/mcp"
DEFAULT_WARN_PCT = 80.0
DEFAULT_CRIT_PCT = 95.0

STATE_ENV = "REDIS_QUOTA_STATE_FILE"

# D1 burn projection: ignore snapshot deltas closer than this (noisy micro-windows).
BURN_MIN_DT_SECONDS = 600


# ── pure logic (unit-testable, no network) ────────────────────────────────────


def compute_pct(used, limit):
    """Usage percent as float, or None when the limit is unknown/invalid."""
    try:
        limit_f = float(limit)
        used_f = float(used)
    except (TypeError, ValueError):
        return None
    if limit_f <= 0:
        return None
    return round(used_f * 100.0 / limit_f, 2)


def tier_for(pct, warn_pct=DEFAULT_WARN_PCT, crit_pct=DEFAULT_CRIT_PCT):
    """None (quiet) / 'warn' (>= warn_pct) / 'crit' (>= crit_pct)."""
    if pct is None:
        return None
    if pct >= crit_pct:
        return "crit"
    if pct >= warn_pct:
        return "warn"
    return None


def evaluate_accounts(accounts, warn_pct=DEFAULT_WARN_PCT, crit_pct=DEFAULT_CRIT_PCT):
    """Return the alert list for a quotaChainStatus-shaped chain array."""
    alerts = []
    for account in accounts or []:
        usage = account.get("usage") or {}
        used = usage.get("estimatedCommands", 0)
        limit = usage.get("limit")
        pct = compute_pct(used, limit)
        tier = tier_for(pct, warn_pct, crit_pct)
        if tier:
            alerts.append(
                {
                    "label": account.get("label", "unknown"),
                    "pct": pct,
                    "tier": tier,
                    "used": used,
                    "limit": limit,
                    "cooldownUntil": account.get("cooldownUntil"),
                }
            )
    return alerts


def compose_message(alerts, active_primary=None, next_reset=None, extra_lines=None):
    """One Telegram message describing every crossed threshold (+ D1 extras). Empty → None."""
    if not alerts and not extra_lines:
        return None
    lines = []
    for a in alerts:
        tag = "[CRITICAL]" if a["tier"] == "crit" else "[WARN]"
        lines.append(
            "%s Upstash Redis account '%s' at %.2f%% of quota (%s / %s commands)."
            % (tag, a["label"], a["pct"], a["used"], a["limit"])
        )
    if active_primary:
        lines.append("Active rotation primary: %s." % active_primary)
    if next_reset:
        lines.append("Quota window resets: %s." % next_reset)
    lines.append(
        "Auto-rotation (#646) protects traffic at 96%, but capacity is running out "
        "across the chain — top up, downgrade burn, or add an account."
    )
    for extra in extra_lines or []:
        lines.append(extra)
    return "\n".join(lines)


# ── D1 (#1698): burn-rate projection + chain-depth capacity (pure, honest-None) ──


def parse_iso_ts(ts):
    """ISO-8601 → aware datetime, or None when unparseable (never raises)."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def snapshot_key(label):
    return "usage:%s" % label


def prior_usage_snapshot(state, label, window_key):
    """Prior {used, ts} for this label, only when recorded in the SAME quota window."""
    entry = state.get(snapshot_key(label))
    if not isinstance(entry, dict):
        return None
    if entry.get("window") != window_key:
        return None
    used, ts = entry.get("used"), entry.get("ts")
    if not isinstance(used, (int, float)) or parse_iso_ts(ts) is None:
        return None
    return {"used": used, "ts": ts}


def record_usage_snapshot(state, label, window_key, used, ts_iso):
    state[snapshot_key(label)] = {"window": window_key, "used": used, "ts": ts_iso}


def project_burn(prior, current, limit, soft_used, reset_iso, warn_pct=DEFAULT_WARN_PCT):
    """Project the active account's usage at the window reset from two snapshots.

    Returns None (honest skip, reason in "skip") when the delta is unusable:
    missing/foreign-window history (caller responsibility), dt < BURN_MIN_DT_SECONDS,
    negative delta (counter reset), or unparseable/invalid limit.
    Otherwise: {burn_per_hour, projected_used_at_reset, projected_pct, soft_used,
                soft_crossed_at (iso|None), skip: None}.
    """
    now_used = current.get("used")
    now_dt = parse_iso_ts(current.get("ts"))
    prior_dt = parse_iso_ts((prior or {}).get("ts"))
    if prior is None or now_dt is None or prior_dt is None:
        return {"skip": "insufficient history"}
    dt = (now_dt - prior_dt).total_seconds()
    if dt < BURN_MIN_DT_SECONDS:
        return {"skip": "snapshots too close (%ds < %ds)" % (dt, BURN_MIN_DT_SECONDS)}
    try:
        limit_f = float(limit)
        delta = float(now_used) - float(prior.get("used"))
    except (TypeError, ValueError):
        return {"skip": "invalid usage or limit"}
    if limit_f <= 0:
        return {"skip": "invalid limit"}
    if delta < 0:
        return {"skip": "usage counter decreased (window/counter reset)"}
    burn_per_hour = delta * 3600.0 / dt
    if soft_used is None:
        try:
            soft_used = limit_f * float(warn_pct) / 100.0
        except (TypeError, ValueError):
            soft_used = None
    reset_dt = parse_iso_ts(reset_iso)
    projected_used = projected_pct = soft_crossed_at = None
    if reset_dt is not None and reset_dt > now_dt:
        hours_left = (reset_dt - now_dt).total_seconds() / 3600.0
        projected_used = now_used + burn_per_hour * hours_left
        projected_pct = compute_pct(projected_used, limit_f)
    try:
        soft_f = float(soft_used) if soft_used is not None else None
    except (TypeError, ValueError):
        soft_f = None
    if soft_f is not None and burn_per_hour > 0 and now_used < soft_f:
        hours_to_soft = (soft_f - float(now_used)) / burn_per_hour
        soft_crossed_at = (
            datetime.fromtimestamp(now_dt.timestamp() + hours_to_soft * 3600, tz=timezone.utc)
            .isoformat().replace("+00:00", "Z")
        )
    return {
        "skip": None,
        "burn_per_hour": int(round(burn_per_hour)),
        "projected_used_at_reset": projected_used,
        "projected_pct": projected_pct,
        "soft_used": soft_f,
        "soft_crossed_at": soft_crossed_at,
    }


def chain_capacity(chain, active_primary, now_dt=None):
    """Classify failover links: how many are usable besides the active one.

    A link is blocked when its cooldownUntil is in the future OR its usage is at/over
    100%. Returns {active, available, blocked, one_deep, none_available} — the #1698
    incident class ('chain one account deep') is one_deep=True.
    """
    now = now_dt or datetime.now(timezone.utc)
    blocked, available = [], []
    active_usable = 0
    for account in chain or []:
        label = account.get("label", "unknown")
        usage = account.get("usage") or {}
        pct = compute_pct(usage.get("estimatedCommands"), usage.get("limit"))
        cd = parse_iso_ts(account.get("cooldownUntil"))
        is_blocked = (cd is not None and cd > now) or (pct is not None and pct >= 100.0)
        if label == active_primary:
            # the active link counts as usable ONLY if it is not itself quota-blocked
            active_usable = 0 if is_blocked else 1
            continue
        (blocked if is_blocked else available).append(label)
    active_exists = active_primary is not None
    usable = len(available) + active_usable
    return {
        "active": active_primary,
        "available": available,
        "blocked": blocked,
        "one_deep": bool(active_exists and len(chain or []) >= 2 and usable == 1),
        "none_available": (bool(chain or []) and usable == 0) or not (chain or []),
    }


def compose_burn_line(projection, label, next_reset):
    """[BURN] line when the projection crosses the soft threshold before reset."""
    if not projection or projection.get("skip") or projection.get("projected_pct") is None:
        return None
    soft = projection.get("soft_used")
    if soft is None or projection["projected_used_at_reset"] < soft:
        return None
    return (
        "[BURN] Active account '%s' burn ≈ %s commands/h; projected %s at window reset%s. "
        "Soft threshold (%s cmds) crossed at ~%s — act before the hard wall (#1698 D1)."
        % (
            label,
            projection["burn_per_hour"],
            "%d cmds (%.1f%%)" % (projection["projected_used_at_reset"], projection["projected_pct"]),
            " (%s)" % next_reset if next_reset else "",
            "%d" % soft,
            projection.get("soft_crossed_at") or "before reset",
        )
    )


def compose_depth_line(capacity):
    """[DEPTH] line when the chain is one account deep, [DEPTH-CRITICAL] when empty."""
    if not capacity or (not capacity.get("one_deep") and not capacity.get("none_available")):
        return None
    if capacity.get("none_available"):
        return (
            "[DEPTH-CRITICAL] Redis failover chain has NO available link left — "
            "control-plane + backend Redis calls will fail hard (#1698)."
        )
    blocked = ", ".join(capacity.get("blocked") or []) or "none"
    return (
        "[DEPTH] Redis failover chain is ONE account deep: '%s' is the only "
        "non-quota-blocked link of %d (blocked: %s). A spike or shared burn on the "
        "active link before quota reset leaves no fourth link (#1698)."
        % (capacity.get("active"), 1 + len(capacity.get("blocked") or []), blocked)
    )


def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        return True
    except OSError:
        return False


def should_alert(state, label, tier, window_key):
    """True iff this (label, tier) has not already alerted in THIS window."""
    entry = state.get("%s:%s" % (label, tier))
    if not isinstance(entry, dict):
        return True
    return entry.get("window") != window_key


def record_alert(state, label, tier, window_key, sent_at_iso):
    state["%s:%s" % (label, tier)] = {"window": window_key, "sentAt": sent_at_iso}


# ── tower MCP client (self-contained, no SDK) ─────────────────────────────────


def parse_tool_response_text(body):
    """Extract the first text content from an MCP SSE/JSON tools/call response."""
    for line in body.split("\n"):
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if "error" in payload:
                raise RuntimeError("MCP error: %s" % json.dumps(payload["error"])[:300])
            content = (payload.get("result") or {}).get("content") or []
            for chunk in content:
                if chunk.get("type") == "text":
                    return chunk["text"]
            return ""
    # plain JSON response (no SSE framing)
    payload = json.loads(body)
    if "error" in payload:
        raise RuntimeError("MCP error: %s" % json.dumps(payload["error"])[:300])
    content = (payload.get("result") or {}).get("content") or []
    for chunk in content:
        if chunk.get("type") == "text":
            return chunk["text"]
    return ""


def _mcp_post(url, payload, session_id=None, timeout=90):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return resp.read().decode("utf-8"), resp.headers.get("mcp-session-id")


def fetch_chain_status(tower_url=DEFAULT_TOWER_URL):
    """Fresh MCP session → tools/call redis_rotation_status → parsed dict."""
    init_body, session_id = _mcp_post(
        tower_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "redis-quota-monitor", "version": "1.0"},
            },
        },
    )
    if not session_id:
        raise RuntimeError("tower did not return an mcp-session-id")
    try:
        _mcp_post(
            tower_url,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session_id,
            timeout=30,
        )
    except urllib.error.HTTPError:
        pass  # notification response is best-effort
    call_body, _ = _mcp_post(
        tower_url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "redis_rotation_status", "arguments": {}},
        },
        session_id,
    )
    text = parse_tool_response_text(call_body)
    return json.loads(text)


def send_telegram(message, token, chat_id, timeout=15):
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    payload = json.dumps(
        {"chat_id": chat_id, "text": message[:4096], "disable_web_page_preview": True}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("telegram send failed: %s" % json.dumps(data)[:200])
    return data.get("result", {}).get("message_id")


# ── self-test battery (offline, fake transport) ───────────────────────────────


def run_self_test():
    failures = []

    def check(name, condition):
        if condition:
            print("PASS %s" % name)
        else:
            print("FAIL %s" % name)
            failures.append(name)

    # compute_pct
    check("pct basic", compute_pct(400000, 500000) == 80.0)
    check("pct rounding", compute_pct(1, 3) == 33.33)
    check("pct zero limit", compute_pct(10, 0) is None)
    check("pct none limit", compute_pct(10, None) is None)
    check("pct garbage", compute_pct("x", "y") is None)

    # tier_for boundaries
    check("tier below warn", tier_for(79.99) is None)
    check("tier warn boundary", tier_for(80.0) == "warn")
    check("tier mid", tier_for(94.9) == "warn")
    check("tier crit boundary", tier_for(95.0) == "crit")
    check("tier unknown pct", tier_for(None) is None)

    # evaluate_accounts on a quotaChainStatus-shaped fake
    fake_chain = [
        {"label": "primary", "usage": {"estimatedCommands": 412500, "limit": 500000}},
        {"label": "secondary", "usage": {"estimatedCommands": 480001, "limit": 500000}},
        {"label": "tertiary", "usage": {"estimatedCommands": 50000, "limit": 500000}},
        {"label": "broken", "usage": None},
    ]
    alerts = evaluate_accounts(fake_chain)
    check("evaluate two alerts", [a["label"] for a in alerts] == ["primary", "secondary"])
    check("evaluate tiers", alerts[0]["tier"] == "warn" and alerts[1]["tier"] == "crit")
    check("evaluate honest pct", abs(alerts[0]["pct"] - 82.5) < 1e-9)

    # dedup state machine
    state = {}
    check("dedup first", should_alert(state, "primary", "warn", "W1") is True)
    record_alert(state, "primary", "warn", "W1", "2026-10-27T19:00:00Z")
    check("dedup same window suppressed", should_alert(state, "primary", "warn", "W1") is False)
    check("dedup other tier independent", should_alert(state, "primary", "crit", "W1") is True)
    check("dedup new window fires", should_alert(state, "primary", "warn", "W2") is True)

    # state persistence round-trip
    tmp = os.path.join(tempfile.gettempdir(), "rqm_selftest_state.json")
    save_state(tmp, state)
    check("state roundtrip", load_state(tmp) == state)
    os.unlink(tmp)

    # message composition
    msg = compose_message(alerts, active_primary="secondary", next_reset="2026-11-01T00:00:00Z")
    check("message mentions label", "primary" in msg and "secondary" in msg)
    check("message has tags", "[WARN]" in msg and "[CRITICAL]" in msg)
    check("message has reset", "2026-11-01T00:00:00Z" in msg)
    check("message empty when quiet", compose_message([]) is None)

    # D1 (#1698): parse_iso_ts
    check("iso parse Z", parse_iso_ts("2026-11-01T00:01:00Z") is not None)
    check("iso parse garbage", parse_iso_ts("not-a-date") is None)
    check("iso parse none", parse_iso_ts(None) is None)

    # D1: usage snapshot round-trip (same window only)
    state2 = {}
    check("snapshot absent", prior_usage_snapshot(state2, "tertiary", "W1") is None)
    record_usage_snapshot(state2, "tertiary", "W1", 55000, "2026-10-28T00:00:00Z")
    snap = prior_usage_snapshot(state2, "tertiary", "W1")
    check("snapshot same window", snap is not None and snap["used"] == 55000)
    check("snapshot foreign window", prior_usage_snapshot(state2, "tertiary", "W2") is None)

    # D1: project_burn — honest skips first
    prior = {"used": 50000, "ts": "2026-10-28T00:00:00Z"}
    cur = {"used": 98000, "ts": "2026-10-28T01:00:00Z"}  # 48000 cmds/h
    check("burn no prior", project_burn(None, cur, 500000, None, "2026-11-01T00:01:00Z")["skip"] is not None)
    fresh = {"used": 98001, "ts": "2026-10-28T01:00:10Z"}
    check("burn too-fresh dt", project_burn(cur, fresh, 500000, None, "2026-11-01T00:01:00Z")["skip"] is not None)
    check("burn negative delta", project_burn(cur, {"used": 10, "ts": "2026-10-28T03:00:00Z"}, 500000, None, "2026-11-01T00:01:00Z")["skip"] is not None)
    check("burn bad limit", project_burn(prior, cur, 0, None, "2026-11-01T00:01:00Z")["skip"] is not None)
    # 48000 cmds/h from 01:00Z; reset 2026-11-01T00:01:00Z is 95.0167h later →
    # projected = 98000 + 48000*95.0167 = 4,658,800 cmds = 931.76% → BURN fires
    proj = project_burn(prior, cur, 500000, 480000, "2026-11-01T00:01:00Z")
    check("burn rate math", proj["skip"] is None and proj["burn_per_hour"] == 48000)
    check("burn projection pct", abs(proj["projected_pct"] - 931.76) < 0.01)
    check("burn soft crossing", proj["soft_crossed_at"] is not None)
    line = compose_burn_line(proj, "tertiary", "2026-11-01T00:01:00Z")
    check("burn line fires", line is not None and "[BURN]" in line and "tertiary" in line)
    # under-soft projection stays quiet: 2000 cmds/h over 95.0167h → 98000 + 190033 = 57.6% < 96%
    calm = project_burn({"used": 96000, "ts": "2026-10-28T00:00:00Z"}, cur, 500000, 480000, "2026-11-01T00:01:00Z")
    check("burn calm no line", compose_burn_line(calm, "tertiary", "2026-11-01T00:01:00Z") is None)

    # D1: chain_capacity — the #1698 incident shape
    incident_chain = [
        {"label": "primary", "usage": {"estimatedCommands": 480000, "limit": 500000}, "cooldownUntil": "2026-11-01T00:01:00Z"},
        {"label": "secondary", "usage": {"estimatedCommands": 500001, "limit": 500000}, "cooldownUntil": "2026-11-01T00:01:00Z"},
        {"label": "tertiary", "usage": {"estimatedCommands": 55, "limit": 500000}, "cooldownUntil": None},
    ]
    cap = chain_capacity(incident_chain, "tertiary", now_dt=parse_iso_ts("2026-10-28T02:00:00Z"))
    check("depth one-deep", cap["one_deep"] is True and cap["available"] == [] and cap["blocked"] == ["primary", "secondary"])
    check("depth line fires", "[DEPTH]" in (compose_depth_line(cap) or ""))
    healthy_chain = [
        {"label": "primary", "usage": {"estimatedCommands": 100, "limit": 500000}, "cooldownUntil": None},
        {"label": "tertiary", "usage": {"estimatedCommands": 55, "limit": 500000}, "cooldownUntil": None},
    ]
    cap2 = chain_capacity(healthy_chain, "tertiary", now_dt=parse_iso_ts("2026-10-28T02:00:00Z"))
    check("depth healthy quiet", cap2["one_deep"] is False and compose_depth_line(cap2) is None)
    dead_chain = [
        {"label": "primary", "usage": {"estimatedCommands": 500001, "limit": 500000}, "cooldownUntil": None},
    ]
    cap3 = chain_capacity(dead_chain, "primary", now_dt=parse_iso_ts("2026-10-28T02:00:00Z"))
    check("depth crit", cap3["none_available"] is True and "[DEPTH-CRITICAL]" in (compose_depth_line(cap3) or ""))
    check("depth pct-100 blocked without cooldown", cap3["blocked"] == [] and cap3["available"] == [])

    # SSE parser on a canned MCP response
    canned = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{\\"autoRotateEnabled\\": true, \\"chain\\": []}"}]}}\n'
    )
    text = parse_tool_response_text(canned)
    check("sse parse", json.loads(text)["autoRotateEnabled"] is True)

    print("REDIS_QUOTA_MONITOR_SELFTEST=%s" % ("PASS" if not failures else "FAIL"))
    return 0 if not failures else 1


# ── main ──────────────────────────────────────────────────────────────────────


def main(argv=None):
    parser = argparse.ArgumentParser(description="Upstash chain quota → Telegram 80% warning (#1522)")
    parser.add_argument("--self-test", action="store_true", help="offline self-test battery, no network")
    parser.add_argument("--dry-run", action="store_true", help="evaluate + print report, send nothing")
    parser.add_argument("--tower-url", default=os.environ.get("SUPREMEAI_TOWER_URL", DEFAULT_TOWER_URL))
    parser.add_argument("--warn-pct", type=float, default=float(os.environ.get("REDIS_QUOTA_WARN_PCT", DEFAULT_WARN_PCT)))
    parser.add_argument("--crit-pct", type=float, default=float(os.environ.get("REDIS_QUOTA_CRIT_PCT", DEFAULT_CRIT_PCT)))
    parser.add_argument(
        "--state-file",
        default=os.environ.get(STATE_ENV, os.path.join(tempfile.gettempdir(), "redis_quota_alert_state.json")),
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    try:
        report = fetch_chain_status(args.tower_url)
    except Exception as exc:  # honest skip — never fabricate usage (U2)
        if os.environ.get("REDIS_QUOTA_STRICT"):
            print("ERROR: tower unreachable and REDIS_QUOTA_STRICT=1: %s" % exc)
            return 3
        print("SKIPPED: tower unreachable (%s) — no fabricated data sent (U2)." % exc)
        return 0

    chain = report.get("chain") or []
    window_key = report.get("nextGlobalResetAt") or "unknown-window"
    alerts = evaluate_accounts(chain, args.warn_pct, args.crit_pct)
    state = load_state(args.state_file)
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── D1 (#1698): burn projection for the ACTIVE account + chain-depth capacity ──
    active_label = report.get("activePrimary")
    extra_lines, extra_tiers = [], []  # (label, tier) pairs for dedup + exit mapping
    active_account = next((a for a in chain if a.get("label") == active_label), None)
    if active_account and isinstance(active_account.get("usage"), dict):
        usage = active_account["usage"]
        prior = prior_usage_snapshot(state, active_label, window_key)
        current = {"used": usage.get("estimatedCommands", 0), "ts": now_iso}
        projection = project_burn(
            prior, current, usage.get("limit"), usage.get("softThreshold"),
            report.get("nextGlobalResetAt"), args.warn_pct,
        )
        if projection.get("skip"):
            print("burn projection skipped: %s (U2 honest)" % projection["skip"])
        else:
            print(
                "burn: active=%s ≈ %s cmds/h, projected %.1f%% at reset%s"
                % (
                    active_label, projection["burn_per_hour"],
                    projection["projected_pct"] if projection["projected_pct"] is not None else -1.0,
                    " (soft cross ~%s)" % projection["soft_crossed_at"] if projection["soft_crossed_at"] else "",
                )
            )
            burn_line = compose_burn_line(projection, active_label, report.get("nextGlobalResetAt"))
            if burn_line and should_alert(state, active_label, "burn", window_key):
                extra_lines.append(burn_line)
                extra_tiers.append((active_label, "burn"))
    # record the usage snapshot for EVERY link so rotation moves keep history continuous
    for account in chain:
        usage = account.get("usage") or {}
        if isinstance(usage.get("estimatedCommands"), (int, float)):
            record_usage_snapshot(state, account.get("label", "unknown"), window_key,
                                  usage["estimatedCommands"], now_iso)
    capacity = chain_capacity(chain, active_label)
    depth_tier = "depth_crit" if capacity.get("none_available") else "depth"
    depth_line = compose_depth_line(capacity)
    if depth_line and should_alert(state, "__chain__", depth_tier, window_key):
        extra_lines.append(depth_line)
        extra_tiers.append(("__chain__", depth_tier))

    pending = [a for a in alerts if should_alert(state, a["label"], a["tier"], window_key)]

    if not pending and not extra_tiers:
        for a in alerts:
            print(
                "  %-12s %6.2f%% (%s/%s) tier=%s (already alerted this window)"
                % (a["label"], a["pct"], a["used"], a["limit"], a["tier"])
            )
        save_state(args.state_file, state)  # usage snapshots still advanced
        print("REDIS_QUOTA_MONITOR=no_alert")
        return 0

    message = compose_message(pending, report.get("activePrimary"), report.get("nextGlobalResetAt"), extra_lines)

    print("window=%s accounts=%d alerts=%d pending=%d extras=%d" % (
        window_key, len(chain), len(alerts), len(pending), len(extra_tiers)))
    already = {(a["label"], a["tier"]) for a in pending}
    for a in alerts:
        suffix = "" if (a["label"], a["tier"]) in already else " (already alerted this window)"
        print(
            "  %-12s %6.2f%% (%s/%s) tier=%s%s"
            % (a["label"], a["pct"], a["used"], a["limit"], a["tier"], suffix)
        )

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if args.dry_run:
        print("--- dry run, would send ---")
        print(message)
        print("--- end would-send ---")
    elif not token or not chat_id:
        print("SKIPPED: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not configured — nothing sent (U2 honest skip).")
        print(message)
        print("REDIS_QUOTA_MONITOR=unconfigured")
        return 0
    else:
        message_id = send_telegram(message, token, chat_id)
        for a in pending:
            record_alert(state, a["label"], a["tier"], window_key, now_iso)
        for label, tier in extra_tiers:
            record_alert(state, label, tier, window_key, now_iso)
        save_state(args.state_file, state)
        print("telegram message_id=%s" % message_id)

    sent_tiers = {a["tier"] for a in pending} | {tier for _, tier in extra_tiers}
    if "crit" in sent_tiers or "depth_crit" in sent_tiers:
        print("REDIS_QUOTA_MONITOR=crit_sent")
        return 2
    print("REDIS_QUOTA_MONITOR=warn_sent")
    return 1


if __name__ == "__main__":
    sys.exit(main())
