#!/usr/bin/env python3
"""Redis quota monitor — 80% Telegram warning for the Upstash account chain (#1522 / Q1).

বাংলা মন্তব্য: Upstash free-tier চেইনের যেকোনো account মাসিক কোটার 80% ছুঁলে
Telegram-এ একটি সতর্কতা যাবে (95% হলে CRITICAL)। উদ্দেশ্য — 500k সিলিং ভাঙার
*আগেই* মানুষ/অ্যাডমিন জানবে, কারণ tower-এর 96% preemptive rotation (#646)
কেবল ট্রাফিক অন্য account-এ সরায়, কিন্তু "কোটা শেষ হচ্ছে" সংবাদটি কাউকে দেয় না।

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
  0 = ok / skipped / no alert   1 = warning sent   2 = critical sent   3 = strict-mode fetch failure
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


def compose_message(alerts, active_primary=None, next_reset=None):
    """One Telegram message describing every crossed threshold (empty → None)."""
    if not alerts:
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
    return "\n".join(lines)


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
    active = [a for a in alerts if should_alert(state, a["label"], a["tier"], window_key)]

    now_iso = datetime.now(timezone.utc).isoformat()
    message = compose_message(active, report.get("activePrimary"), report.get("nextGlobalResetAt"))

    print("window=%s accounts=%d alerts=%d pending=%d" % (window_key, len(chain), len(alerts), len(active)))
    already = {(a["label"], a["tier"]) for a in active}
    for a in alerts:
        suffix = "" if (a["label"], a["tier"]) in already else " (already alerted this window)"
        print(
            "  %-12s %6.2f%% (%s/%s) tier=%s%s"
            % (a["label"], a["pct"], a["used"], a["limit"], a["tier"], suffix)
        )

    if not active:
        print("REDIS_QUOTA_MONITOR=no_alert")
        return 0

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
        for a in active:
            record_alert(state, a["label"], a["tier"], window_key, now_iso)
        save_state(args.state_file, state)
        print("telegram message_id=%s" % message_id)

    highest = "crit" if any(a["tier"] == "crit" for a in active) else "warn"
    print("REDIS_QUOTA_MONITOR=%s_sent" % highest)
    return 2 if highest == "crit" else 1


if __name__ == "__main__":
    sys.exit(main())
