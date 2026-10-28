#!/usr/bin/env python3
"""Standing queue-plane consistency probe (#2100 / #2115 / #2123 arc, bridge fleet).

বাংলা: tower-এর dispatch প্লেন (bridge_work_queue) আর feedback প্লেন
(bridge_read_feedback) এখন তিনটি ফাইল্ড ডিফেক্টের মতো একে অপরের সাথে দ্বিমত করে:
#2100 verdict-stamp blackout, #2115 count-truncation, #2123 age-cutoff। এই প্রোব
এক anonymous snapshot-এ দুই প্লেন পাশাপাশি পড়ে চার শ্রেণির অসঙ্গতি ধরে:

  R1 MIRROR-STALE : সারি কিউতে আছে, কিন্তু feedback বলছে state == closed
                    (landed mirror residue — পিক-পৃষ্ঠ দূষণের কিউ-স্তর)
  R2 CLAIM-LAG    : feedback-এ fresh live claim (≤ TTL) আছে, কিন্তু কিউ-সারিতে
                    status:claimed লেবেল নেই (live 2026-10-28: #2111, ≥19 মিনিট)
  R3 VERDICT-LAG  : feedback-এ verdict ইতিহাস আছে, কিন্তু সারি এখনও bridge:queued
                    / bridge:pr-opened (verdict↔label স্ট্যাম্প পাইপলাইন ল্যাগ)
  R4 UNRESOLVED   : feedback কল ব্যর্থ (ট্রানজিয়েন্ট) — violation নয়, সৎ গণনা;
                    ৫০%-এর বেশি unresolved হলে পুরো স্ন্যাপশট অবিশ্বস্ত → fail-close

চুক্তি (tower_discovery_probe.py-এর মতোই):
  exit 0 "pass"/"clean" : কোনো R1/R2/R3 অসঙ্গতি নেই
  exit 1                : যেকোনো অসঙ্গতি (fail-close — নীরব পাস নেই)
  exit 0 "skip"         : tower অনুপলব্ধ বা প্রয়োজনীয় bridge tool বিজ্ঞাপিত নয়
                          (honest-skip, #1760 মতবাদ)

নিরাপত্তা: এই প্রোব hard allowlist (bridge_work_queue + bridge_read_feedback) ছাড়া
কোনো বিজ্ঞাপিত tool চালাতেই পারে না — কল-র্যাপারে fail-close assert; secret/
destructive-class execution কাঠামোগতভাবে অসম্ভব। দুটোই read-only dispatch surface।

ব্যবহার:
  python scripts/queue_consistency_probe.py --json [--out FILE] [--limit 50]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

FEEDBACK_POLITENESS_SEC = 0.2  # burst limit observed: 16/36 first-shot calls unresolved
FEEDBACK_RETRIES = 1

DEFAULT_URL = "https://supremeai-mcp-tower.onrender.com/mcp"

# fail-close allowlist — the ONLY advertised tools this probe may execute
TOOLS_ALLOWED = ("bridge_work_queue", "bridge_read_feedback")

IN_FLIGHT_BRIDGE_LABELS = ("bridge:queued", "bridge:pr-opened")
CLAIM_FRESH_DEFAULT_MIN = 30.0  # S0.1 atomic-claim lease (#57 SSOT)


def post(url: str, payload: dict, session_id: str | None, timeout: float):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, resp.headers.get("Mcp-Session-Id"), body
    except urllib.error.HTTPError as exc:
        return exc.code, None, exc.read().decode()
    except Exception as exc:  # noqa: BLE001 — honest-skip path needs the string
        return -1, None, str(exc)


def parse_sse(body: str) -> dict | None:
    if not body:
        return None
    if body.lstrip().startswith("{"):
        try:
            return json.loads(body)
        except Exception:
            return None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                try:
                    return json.loads(data)
                except Exception:
                    pass
    return None


def open_session(url: str, timeout: float):
    """returns (tools, session_id, error) — tools None => error path."""
    status, sid, body = post(url, {
        "jsonrpc": "2.0", "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "queue-consistency-probe", "version": "1.0"},
        },
        "id": 1,
    }, None, timeout)
    if status != 200 or not sid:
        return None, None, f"initialize failed: status={status} body={body[:200]}"
    post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, timeout)
    status, _, body = post(
        url, {"jsonrpc": "2.0", "method": "tools/list", "id": 2}, sid, timeout
    )
    if status != 200:
        return None, None, f"tools/list failed: status={status}"
    parsed = parse_sse(body)
    if not parsed or "result" not in parsed:
        return None, None, "tools/list: unparseable envelope"
    return parsed["result"].get("tools", []), sid, None


def call_allowed_tool(url: str, sid: str, timeout: float, next_id: list[int],
                      name: str, arguments: dict):
    """fail-close wrapper: only allowlisted read-only bridge tools may run."""
    if name not in TOOLS_ALLOWED:
        raise SystemExit(
            f"fail-close: tool '{name}' is outside the allowlist {TOOLS_ALLOWED}"
        )
    next_id[0] += 1
    status, _, body = post(url, {
        "jsonrpc": "2.0", "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
        "id": next_id[0],
    }, sid, timeout)
    if status != 200:
        return None, f"tools/call {name}: status={status}"
    parsed = parse_sse(body)
    if not parsed or "result" not in parsed:
        return None, f"tools/call {name}: unparseable envelope"
    content = parsed["result"].get("content") or []
    text = ""
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text += str(item.get("text", ""))
    if not text.strip():
        return None, f"tools/call {name}: empty content"
    try:
        return json.loads(text), None
    except Exception:
        return None, f"tools/call {name}: non-JSON payload"


def row_labels(row: dict) -> set[str]:
    labels = row.get("labels")
    if not isinstance(labels, list):
        return set()
    out = set()
    for lb in labels:
        if isinstance(lb, dict):
            out.add(str(lb.get("name", "")).lower())
        else:
            out.add(str(lb).lower())
    return out


def parse_ts(value) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--out", type=str, default="", help="write receipt JSON here")
    args = parser.parse_args()
    limit = max(1, min(int(args.limit), 50))  # tower 422s above 50

    receipt: dict = {
        "check": "queue_plane_consistency_probe",
        "url": args.url,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "zero_credential": True,
        "tools_allowlist": list(TOOLS_ALLOWED),
    }

    tools, sid, err = open_session(args.url, args.timeout)
    if tools is None:
        receipt.update({"status": "skip", "reason": err})
        print(json.dumps(receipt, indent=2) if args.as_json else f"skip: {err}")
        return 0  # honest-skip (#1760)
    receipt["session_id"] = sid

    advertised = {str(t.get("name", "")) for t in tools if isinstance(t, dict)}
    missing = [n for n in TOOLS_ALLOWED if n not in advertised]
    if missing:
        receipt.update({
            "status": "skip",
            "reason": f"required bridge tools not advertised: {', '.join(missing)}",
        })
        print(json.dumps(receipt, indent=2) if args.as_json else f"skip: {receipt['reason']}")
        return 0

    queue, qerr = call_allowed_tool(
        args.url, sid, args.timeout, [2], "bridge_work_queue", {"limit": limit}
    )
    if queue is None:
        receipt.update({"status": "skip", "reason": f"queue poll: {qerr}"})
        print(json.dumps(receipt, indent=2) if args.as_json else f"skip: {receipt['reason']}")
        return 0

    rows = queue.get("workOrders") if isinstance(queue, dict) else None
    if not isinstance(rows, list):
        receipt.update({"status": "skip", "reason": "queue payload has no workOrders list"})
        print(json.dumps(receipt, indent=2) if args.as_json else f"skip: {receipt['reason']}")
        return 0

    now = time.time()
    next_id = [10]  # session used ids 1 (initialize) + 2 (tools/list) — start clear of both
    inconsistencies: list[dict] = []
    unresolved: list[int] = []
    session_rotations = [0]

    def feedback_with_rotation(number: int):
        """live observation 2026-10-28: an anonymous session stops answering
        tools/call after ~19-20 calls (burst budget) — rotate the session on
        failure instead of losing the tail of the snapshot."""
        nonlocal sid
        fb, ferr = call_allowed_tool(
            args.url, sid, args.timeout, next_id,
            "bridge_read_feedback", {"number": number},
        )
        if fb is not None:
            return fb
        for attempt in range(FEEDBACK_RETRIES + 1):
            time.sleep(FEEDBACK_POLITENESS_SEC * (attempt + 1) * 2)
            new_sid, serr = open_session(args.url, args.timeout)[1:3]
            if new_sid is None:
                continue
            sid = new_sid
            session_rotations[0] += 1
            fb, ferr = call_allowed_tool(
                args.url, sid, args.timeout, next_id,
                "bridge_read_feedback", {"number": number},
            )
            if fb is not None:
                return fb
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        num = row.get("number")
        if num is None:
            continue
        fb = feedback_with_rotation(int(num))
        if fb is None:
            unresolved.append(int(num))
            continue
        time.sleep(FEEDBACK_POLITENESS_SEC)
        labels = row_labels(row)
        fb_state = str(fb.get("state", "")).lower()
        # R1 MIRROR-STALE
        if fb_state == "closed":
            inconsistencies.append({
                "rule": "R1-mirror-stale", "number": int(num),
                "detail": f"row in queue but feedback state=closed; row labels={sorted(labels)}",
            })
            continue
        # R2 CLAIM-LAG
        claim = fb.get("latestClaim") if isinstance(fb.get("latestClaim"), dict) else None
        if claim:
            at = parse_ts(claim.get("at"))
            ttl_min = claim.get("ttlMinutes")
            ttl = float(ttl_min) if isinstance(ttl_min, (int, float)) else CLAIM_FRESH_DEFAULT_MIN
            if at is not None and (now - at) < ttl * 60.0:
                if "status:claimed" not in labels:
                    age_min = (now - at) / 60.0
                    inconsistencies.append({
                        "rule": "R2-claim-lag", "number": int(num),
                        "detail": (
                            f"fresh live claim age={age_min:.0f}min (ttl {ttl:.0f}min) "
                            f"but queue row lacks status:claimed; row labels={sorted(labels)}"
                        ),
                    })
        # R3 VERDICT-LAG
        has_verdict = fb.get("latestVerdict") is not None or bool(fb.get("verdictHistory"))
        if has_verdict and any(lb in labels for lb in IN_FLIGHT_BRIDGE_LABELS):
            inconsistencies.append({
                "rule": "R3-verdict-lag", "number": int(num),
                "detail": f"feedback carries a verdict but row still in-flight-labeled {sorted(labels)}",
            })

    receipt.update({
        "status": None,
        "queue_rows": len(rows),
        "rows_checked": len(rows) - len(unresolved),
        "rows_unresolved": unresolved,
        "session_rotations": session_rotations[0],
        "rule_counts": {
            "R1-mirror-stale": sum(1 for i in inconsistencies if i["rule"].startswith("R1")),
            "R2-claim-lag": sum(1 for i in inconsistencies if i["rule"].startswith("R2")),
            "R3-verdict-lag": sum(1 for i in inconsistencies if i["rule"].startswith("R3")),
        },
        "inconsistencies": inconsistencies,
        "policy": (
            "queue plane and feedback plane must agree on state, fresh-claim and "
            "verdict labels; R4 unresolved>50% fail-closes the whole snapshot"
        ),
    })

    if len(rows) > 0 and len(unresolved) * 2 > len(rows):
        receipt["status"] = "unreliable"
        receipt["reason"] = (
            f"{len(unresolved)}/{len(rows)} rows unresolved — snapshot not trustworthy"
        )
    else:
        receipt["status"] = "violation" if inconsistencies else "clean"

    rendered = json.dumps(receipt, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    if args.as_json:
        print(rendered)
    else:
        print(
            f"{receipt['status']}: {len(rows)} queue rows checked "
            f"({len(unresolved)} unresolved), "
            f"R1={receipt['rule_counts']['R1-mirror-stale']} "
            f"R2={receipt['rule_counts']['R2-claim-lag']} "
            f"R3={receipt['rule_counts']['R3-verdict-lag']}"
        )
        for inc in inconsistencies:
            print(f"  - [{inc['rule']}] #{inc['number']}: {inc['detail']}")
    if receipt["status"] in ("violation", "unreliable"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
