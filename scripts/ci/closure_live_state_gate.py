#!/usr/bin/env python3
"""closure_live_state_gate.py — closure-time live-state cross-check (#2925 Option A).

কেন (Why — Bengali, house style):
    ২০২৬-১০-২৯ ২৩:১৮:১৭Z-এ #2225 দ্বিতীয়বার `completed` হিসেবে বন্ধ হলো —
    boundary-honest টেমপ্লেট ফিক্স (#2886) নামার ৬৫ মিনিট পরে, অথচ #2738-এর
    recovery criterion উভয় সার্ভিসে যান্ত্রিকভাবে **FAILED** ছিল (render-primary/
    worker `update_failed`, ~৫ দিন ১৪ ঘণ্টা frozen `updatedAt`)। প্রমাণ-তল
    (#2855→#2897) ও সাক্ষী-তল (C49 #2916) লঙ্ঘনটি রেকর্ড করেছিল, কিন্তু কোনো
    মেকানিজমই কোনো তলকে **consumed** করত না — বন্ধকারী কোনো গেট ছাড়াই এগিয়ে
    গেল। টেমপ্লেট ফিক্স কেবল *নতুন dispatch pick* বাঁধে; *বন্ধ করার কাজটিকে*
    (closing act) কাঠামোগতভাবে বাঁধতেই পারে না। এই গেট সেই শ্রেণিব্যাপী রোগের
    root-cause ফিক্স: criterion ব্যর্থ হলে closing artifact প্রান্তেই প্রত্যাখ্যান।

Contract (#2925 Option A, `adapt` verdict):
    কোনো platform-audit-labeled সাবজেক্ট ইস্যুর জন্য closing artifact তৈরির
    আগে (merge auto-close, verdict write, closing comment) — ইস্যুর নিজস্ব
    ঘোষিত recovery criterion tower read tools-এর বিরুদ্ধে মূল্যায়ন হবে
    (`resource_status` / `health_full_sweep`, zero-credential)।
    Criterion FAILED ⇒ closing artifact প্রত্যাখ্যাত, run evidence-only-তে
    ডাউনগ্রেড, criterion-এর আউটপুট সংযুক্ত, stderr-এ fail-loud — #2704-এর
    আকৃতি ("a silently under-scanned sweep is worse than a loud failure"),
    বন্ধকাজে প্রয়োগ করা। Scope note: platform-audit লেবেল scoping সাধারণ
    fix-lane closure-কে গেটের বাইরে রাখে (ওরা landing evidence-এ বন্ধ হয়,
    যা রিপো সরাসরি যাচাই করতে পারে)।

Criterion schema (v1, JSON — `--criterion-file` / `--criterion-json`):
    {
      "version": 1,
      "declaredBy": "#2738",
      "services": [
        {"resourceId": "render/render-primary", "allowedStatuses": ["healthy"]},
        {"resourceId": "render/render-worker", "allowedStatuses": ["healthy"]}
      ],
      "sweepProviders": [
        {"provider": "render-primary", "allowedStatuses": ["healthy"],
         "evidenceForbiddenSubstrings": ["update_failed"]}
      ]
    }
    - `services`      : Tower resource_status plane-এর বিরুদ্ধে মূল্যায়ন।
    - `sweepProviders`: health_full_sweep snapshots plane — status ছাড়াও
                        evidence summary-তে নিষিদ্ধ substring (যেমন
                        `update_failed`) থাকলে ব্যর্থ।
    - ঘোষিত কিন্তু live ডেটায় অনুপস্থিত provider/resource → ব্যর্থ (fail-closed);
      যাচাই-অযোগ্য predicate-কে চুপচাপ pass ধরা এই লেনের ফাটলই পুনরাবৃত্তি করবে।

Verdicts (single bookkeeping):
    PASS           সব predicate পাস — closing artifact এগোতে পারে।
    FAIL           অন্তত একটি predicate ব্যর্থ — REFUSED, exit 1, fail-loud।
    NO_CRITERION   সাবজেক্ট গেটের scope-এ, কিন্তু criterion ঘোষিত নয় —
                   যান্ত্রিক মূল্যায়ন অসম্ভব; report-only সতর্কবাণী (exit 0),
                   `--strict`-এ প্রত্যাখ্যান (exit 1)।
    NOT_APPLICABLE সাবজেক্ট platform-audit-labeled নয় — গেট বন্ধ (exit 0)।
    UNREACHABLE    tower read ব্যর্থ/`--offline` — সৎ skip (exit 2); কখনো pass
                   হিসেবে রিপোর্ট নয় (bridge_landing_watchdog-এর ডকট্রিন)।

Modes:
    --self-test   hermetic verdict-matrix proof (fixture snapshot; নেটওয়ার্ক
                  নেই)। run_all_guards.py roster-এ নিবন্ধিত।
    --subject N   গেট মোড: সাবজেক্ট ইস্যুর labels tower থেকে পড়ে scope যাচাই।
Exit codes: 0 = gate passed / not applicable / unchecked, 1 = closing artifact
            REFUSED (criterion FAILED, বা --strict-এ NO_CRITERION),
            2 = tower/inputs unreachable (honest skip — never reported as pass).

Zero credentials, read-only (Tower queries only). No mutation. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

try:
    from tower_name_tolerance import tolerant_tool_call  # flat: scripts/ci on sys.path
except ImportError:  # pragma: no cover — package-style load (tests, CI runner)
    from scripts.ci.tower_name_tolerance import tolerant_tool_call

DEFAULT_TOWER_URL = "https://supremeai-mcp-tower.onrender.com/mcp"
# #2925 scope note: গেট কেবল platform-audit পরিবারের সাবজেক্টে ফায়ার করে
# (#2225/#2557-এর লেবেল-প্লেন পর্যবেক্ষণ থেকে গ্রাউন্ডেড)। --labels দিয়ে
# ওভাররাইডযোগ্য।
DEFAULT_AUDIT_LABELS = ("audit:finding",)


# ---------------------------------------------------------------- tower client


def _post_json(url: str, payload: dict[str, Any], session_id: str | None,
               timeout: float) -> tuple[Any, str | None]:
    """One streamable-HTTP JSON-RPC exchange; returns (data, session_id)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(  # nosec B310 — URL is the operator-supplied tower endpoint
        url, data=json.dumps(payload).encode("utf-8"), headers=headers
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        new_sid = resp.headers.get("mcp-session-id", session_id)
        body = resp.read().decode("utf-8", errors="replace")
    data = None
    for line in body.splitlines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
    if data is None and body.strip():
        data = json.loads(body)
    return data, new_sid


class TowerClient:
    """Minimal zero-credential MCP tower client (initialize → tools/call)."""

    def __init__(self, url: str = DEFAULT_TOWER_URL, timeout: float = 45.0):
        self.url = url
        self.timeout = timeout
        self._sid: str | None = None
        self._initialized = False

    def _handshake(self) -> None:
        # initialize returns the session id — it MUST ride the notifications
        # call, otherwise the tower answers 400 and every gate run crashes
        # before the honest-skip path can fire (live-found 2026-10-30).
        init, sid = _post_json(self.url, {
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "closure-live-state-gate",
                                      "version": "1.0.0"}},
        }, None, self.timeout)
        if isinstance(init, dict) and "error" in init:
            raise TowerUnreachable(f"initialize: {init['error']}")
        _post_json(self.url, {
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }, sid, self.timeout)
        self._sid = sid
        self._initialized = True

    def call(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """Call one tower tool; returns unwrapped result payload.

        Raises TowerUnreachable on any transport/protocol failure — callers
        convert that into the UNREACHABLE verdict (honest skip, exit 2).
        """
        try:
            if not self._initialized:
                self._handshake()
            payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args or {}}}
            data, self._sid = _post_json(self.url, payload, self._sid,
                                         self.timeout)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise TowerUnreachable(f"{name}: {exc}") from exc
        if not isinstance(data, dict):
            raise TowerUnreachable(f"{name}: non-object JSON-RPC envelope")
        if "error" in data:
            raise TowerUnreachable(f"{name}: {data['error']}")
        result = data.get("result", {})
        texts = [c.get("text", "") for c in result.get("content", [])
                 if c.get("type") == "text"]
        raw = "\n".join(texts)
        try:
            return json.loads(raw) if raw else result
        except (json.JSONDecodeError, ValueError):
            return raw

    # -- typed planes ------------------------------------------------------

    def read_subject(self, issue: int) -> dict[str, Any]:
        # নাম-ঢেউ সহনশীল (U6, rename-wave caller debt): bridge_work_order ↔
        # bridge.work_order দোলনে এক-বানান hardcode অন্ধ হয় — যুগ-লেজার ক্রমে
        # চেষ্টা (scripts/ci/tower_name_tolerance.py, shared cure)।
        return tolerant_tool_call(self.call, "bridge.work_order", {"number": issue})

    def resource_inventory(self) -> dict[str, str]:
        """Authoritative resource inventory: {id: status} (resource_list).

        Grounded live 2026-10-30: `resource_status` echoes a pleasant
        `"status": "healthy"` even for a BOGUS resource id — the status
        plane alone cannot distinguish recovered from nonexistent. The
        inventory is the existence SSOT; a criterion resource absent here
        is unregistered, and its echo must never produce a PASS.
        """
        out = self.call("resource_list", {})
        rows = out.get("resources") if isinstance(out, dict) else out
        inv: dict[str, str] = {}
        for row in rows or []:
            if isinstance(row, dict) and row.get("id"):
                inv[str(row["id"])] = str(row.get("status", "unknown")).lower()
        return inv

    def resource_status(self, resource_id: str) -> tuple[str, str]:
        """Returns (status, raw_payload) for one resource id."""
        out = self.call("resource_status", {"resourceId": resource_id})
        if isinstance(out, dict):
            return str(out.get("status", "unknown")).lower(), json.dumps(out)
        return "unknown", str(out)

    def health_sweep(self) -> dict[str, Any]:
        out = self.call("health_full_sweep", {})
        return out if isinstance(out, dict) else {}


class TowerUnreachable(RuntimeError):
    pass


# ------------------------------------------------------------------ verdicts


def parse_criterion(criterion: dict[str, Any]) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate criterion v1; returns (services, sweep_providers)."""
    if criterion.get("version") != 1:
        raise ValueError("criterion must declare version: 1")
    services = criterion.get("services") or []
    sweep = criterion.get("sweepProviders") or []
    if not services and not sweep:
        raise ValueError("criterion declares no services and no sweepProviders")
    for svc in services:
        if not isinstance(svc, dict) or not svc.get("resourceId"):
            raise ValueError("services[] entry needs a resourceId")
    for prov in sweep:
        if not isinstance(prov, dict) or not prov.get("provider"):
            raise ValueError("sweepProviders[] entry needs a provider")
    return list(services), list(sweep)


UNREGISTERED = "unregistered-in-inventory"


def evaluate_resource_predicate(svc: dict[str, Any],
                                snapshot: dict[str, str]) -> dict[str, Any]:
    """Pure: one `services[]` predicate against {resourceId: status}.

    Fail-closed twice over: a declared resource missing from the live
    snapshot is a failure ("cannot verify"), and an unregistered resource
    (absent from the tower inventory) fails even when the status plane
    echoes a pleasant "healthy" — the echo is exactly the false-close
    surface this gate exists to close.
    """
    rid = str(svc["resourceId"])
    allowed = [str(s).lower() for s in svc.get("allowedStatuses") or []]
    forbidden = [str(s).lower() for s in svc.get("forbiddenStatuses") or []]
    if rid not in snapshot:
        return {"predicate": rid, "verdict": "FAIL",
                "reason": "resource absent from live snapshot — cannot verify",
                "status": None}
    status = str(snapshot[rid]).lower()
    if status == UNREGISTERED:
        return {"predicate": rid, "verdict": "FAIL",
                "reason": "resource not in tower resource inventory — "
                          "cannot verify declared criterion resource",
                "status": status}
    if allowed and status not in allowed:
        return {"predicate": rid, "verdict": "FAIL",
                "reason": f"status '{status}' not in allowedStatuses {allowed}",
                "status": status}
    if forbidden and status in forbidden:
        return {"predicate": rid, "verdict": "FAIL",
                "reason": f"status '{status}' is in forbiddenStatuses {forbidden}",
                "status": status}
    return {"predicate": rid, "verdict": "PASS", "reason": "status matches",
            "status": status}


def evaluate_sweep_predicate(prov: dict[str, Any],
                             snapshots: dict[str, Any]) -> dict[str, Any]:
    """Pure: one `sweepProviders[]` predicate against the sweep snapshot map.

    Fail-closed on a declared provider absent from the snapshot; forbidden
    substrings inside the evidence summary also fail (the #2225 signature:
    HTTP 200 while latest deployment `update_failed`).
    """
    name = str(prov["provider"])
    allowed = [str(s).lower() for s in prov.get("allowedStatuses") or []]
    forbidden_subs = [str(s).lower()
                      for s in prov.get("evidenceForbiddenSubstrings") or []]
    entry = snapshots.get(name)
    if not isinstance(entry, dict):
        return {"predicate": f"sweep:{name}", "verdict": "FAIL",
                "reason": "provider absent from health_full_sweep snapshot — "
                          "cannot verify", "status": None, "evidence": None}
    status = str(entry.get("status", "unknown")).lower()
    evidence = entry.get("evidence") or {}
    summary = str(evidence.get("summary", "")) if isinstance(evidence, dict) \
        else str(evidence)
    if allowed and status not in allowed:
        return {"predicate": f"sweep:{name}", "verdict": "FAIL",
                "reason": f"status '{status}' not in allowedStatuses {allowed}",
                "status": status, "evidence": summary}
    if forbidden_subs:
        low = summary.lower()
        hits = [s for s in forbidden_subs if s in low]
        if hits:
            return {"predicate": f"sweep:{name}", "verdict": "FAIL",
                    "reason": f"evidence summary contains forbidden "
                              f"substring(s) {hits}",
                    "status": status, "evidence": summary}
    return {"predicate": f"sweep:{name}", "verdict": "PASS",
            "reason": "status + evidence match", "status": status,
            "evidence": summary}


def evaluate_criterion(criterion: dict[str, Any],
                       resource_snapshot: dict[str, str],
                       sweep_snapshots: dict[str, Any]) -> dict[str, Any]:
    """Pure core: full criterion evaluation. Returns the evidence document."""
    services, sweep = parse_criterion(criterion)
    checks = [evaluate_resource_predicate(s, resource_snapshot)
              for s in services]
    checks += [evaluate_sweep_predicate(p, sweep_snapshots) for p in sweep]
    failed = [c for c in checks if c["verdict"] == "FAIL"]
    return {
        "gate": "closure_live_state_gate",
        "criterionVersion": criterion.get("version"),
        "declaredBy": criterion.get("declaredBy"),
        "verdict": "FAIL" if failed else "PASS",
        "failedCount": len(failed),
        "checks": checks,
    }


def scope_applies(subject_labels: list[str], audit_labels: list[str]) -> bool:
    """Pure: platform-audit label scoping (keeps fix-lane closures un-gated)."""
    lab = {str(x).strip().lower() for x in subject_labels or []}
    return any(str(a).strip().lower() in lab for a in audit_labels or [])


def route_verdict(subject_labels: list[str], audit_labels: list[str],
                  criterion: dict[str, Any] | None, unreachable: bool,
                  strict: bool = False) -> tuple[str, int, str]:
    """Pure verdict routing. Returns (verdict, exit_code, human_note)."""
    if unreachable:
        return ("UNREACHABLE", 2,
                "tower read failed — honest skip; closure NOT verified by "
                "this gate (never reported as pass)")
    if not scope_applies(subject_labels, audit_labels):
        return ("NOT_APPLICABLE", 0,
                "subject carries no platform-audit label — fix-lane closure, "
                "gate off (scope note #2925)")
    if criterion is None:
        if strict:
            return ("NO_CRITERION", 1,
                    "--strict: platform-audit subject without a declared "
                    "recovery criterion — closing artifact refused; declare "
                    "criterion or attach manual live-state evidence")
        return ("NO_CRITERION", 0,
                "no declared criterion — mechanical evaluation impossible; "
                "report-only warning: attach manual live-state evidence to "
                "the closing artifact")
    # criterion present: evaluation happened upstream
    raise ValueError("route_verdict requires criterion=None here")


REFUSAL_BANNER = (
    "CLOSING ARTIFACT REFUSED — recovery criterion FAILED "
    "(closure_live_state_gate, #2925 Option A). "
    "Downgrade this run to evidence-only: attach the criterion output below "
    "instead of closing; the live state must recover before the closing act."
)


def render_surface(evidence: dict[str, Any]) -> None:
    """Human surface — loud by design (#2704 shape): verdict line on stdout;
    refusal banner + full evidence on stderr so closing pipelines cannot
    miss it. Pure-I/O helper, hermetically testable."""
    verdict = evidence["verdict"]
    exit_code = evidence["exitCode"]
    print(f"[closure-live-state-gate] subject={evidence.get('subject')} "
          f"verdict={verdict} exit={exit_code}")
    if verdict == "FAIL":
        print(REFUSAL_BANNER, file=sys.stderr)
        print(json.dumps(evidence, indent=2, ensure_ascii=False),
              file=sys.stderr)
    elif verdict in ("NO_CRITERION", "UNREACHABLE"):
        print(f"NOTE: {evidence.get('note', '')}", file=sys.stderr)
        if verdict == "UNREACHABLE":
            print(json.dumps(evidence, indent=2, ensure_ascii=False),
                  file=sys.stderr)


# ------------------------------------------------------------------ gate mode


def load_criterion(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.criterion_file:
        try:
            data = json.loads(
                (open(args.criterion_file, encoding="utf-8").read()))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"criterion file unreadable: {exc}")
        return data if isinstance(data, dict) else None
    if args.criterion_json:
        data = json.loads(args.criterion_json)
        return data if isinstance(data, dict) else None
    return None


def run_gate(args: argparse.Namespace) -> int:
    subject = args.subject
    audit_labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    criterion = load_criterion(args)
    evidence: dict[str, Any] = {
        "gate": "closure_live_state_gate",
        "subject": subject,
        "auditLabels": audit_labels,
        "strict": args.strict,
        "tower": args.tower_url,
    }

    client = TowerClient(args.tower_url, timeout=args.timeout)
    subject_labels: list[str] = []
    unreachable = False
    resource_snapshot: dict[str, str] = {}
    sweep_snapshots: dict[str, Any] = {}
    evaluation: dict[str, Any] | None = None

    try:
        wo = client.read_subject(subject)
        if isinstance(wo, dict):
            subject_labels = [str(x) for x in wo.get("labels") or []]
        services = (criterion or {}).get("services") or []
        if services:
            # Existence SSOT first (#2925 root-cause rule): the status plane
            # echoes "healthy" even for bogus ids, so an unregistered
            # resource must be resolved from resource_list, never from the
            # echo.
            inventory = client.resource_inventory()
            evidence["inventorySize"] = len(inventory)
            for svc in services:
                rid = str(svc.get("resourceId", ""))
                if not rid:
                    continue
                if rid not in inventory:
                    resource_snapshot[rid] = UNREGISTERED
                    _, raw = client.resource_status(rid)
                    evidence.setdefault("resourceRaw", {})[rid] = (
                        raw + "  # suspect echo — id absent from "
                              "resource_list inventory")
                    continue
                status, raw = client.resource_status(rid)
                evidence.setdefault("resourceRaw", {})[rid] = raw
                inv_status = inventory[rid]
                if status != inv_status:
                    evidence.setdefault("planeDisagreements", {})[rid] = {
                        "resource_status": status, "inventory": inv_status,
                        "resolved": "inventory (existence SSOT)"}
                resource_snapshot[rid] = inv_status
        if (criterion or {}).get("sweepProviders"):
            sweep_snapshots = (client.health_sweep().get("snapshots") or {})
    except TowerUnreachable:
        unreachable = True

    if criterion is not None and not unreachable:
        evaluation = evaluate_criterion(criterion, resource_snapshot,
                                        sweep_snapshots)
        evidence["evaluation"] = evaluation
    evidence["subjectLabels"] = subject_labels
    evidence["unreachable"] = unreachable

    if evaluation is not None:
        verdict = evaluation["verdict"]
        exit_code = 1 if verdict == "FAIL" else 0
        note = ("recovery criterion evaluated against live tower state"
                if verdict == "PASS" else REFUSAL_BANNER)
    else:
        verdict, exit_code, note = route_verdict(
            subject_labels, audit_labels, criterion, unreachable,
            strict=args.strict)

    evidence["verdict"] = verdict
    evidence["exitCode"] = exit_code
    evidence["note"] = note

    if args.emit_evidence:
        with open(args.emit_evidence, "w", encoding="utf-8") as fh:
            json.dump(evidence, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    render_surface(evidence)
    return exit_code


# ----------------------------------------------------------------- self-test


def self_test() -> int:
    """Hermetic verdict-matrix proof. No network. Roster mode.

    Matrix (each case = the exact live shape from the #2925 evidence chain):
      1  PASS     healthy services + clean sweep        -> exit 0
      2  FAIL     resource degraded                     -> exit 1
      3  FAIL     sweep evidence forbidden substring    -> exit 1 (the
                  `update_failed`-behind-HTTP-200 signature)
      4  FAIL     declared resource absent (fail-closed)-> exit 1
      5  FAIL     declared sweep provider absent        -> exit 1
      6  scope    audit:finding applies                 -> gate active
      7  scope    bare fix-lane subject (no label)      -> NOT_APPLICABLE
      8  routing  NO_CRITERION report-only              -> exit 0
      9  routing  NO_CRITERION strict                   -> exit 1
      10 routing   UNREACHABLE                           -> exit 2
      11 parse     malformed criterion rejected          -> ValueError
      12 unreg     bogus-id healthy-echo does NOT rescue -> FAIL
    """
    ok_resource = {"render/render-primary": "healthy",
                   "render/render-worker": "healthy"}
    crit_ok = {
        "version": 1, "declaredBy": "#2738",
        "services": [
            {"resourceId": "render/render-primary",
             "allowedStatuses": ["healthy"]},
            {"resourceId": "render/render-worker",
             "allowedStatuses": ["healthy"]},
        ],
        "sweepProviders": [
            {"provider": "render-primary", "allowedStatuses": ["healthy"],
             "evidenceForbiddenSubstrings": ["update_failed"]},
        ],
    }
    sweep_ok = {"render-primary": {
        "status": "healthy",
        "evidence": {"kind": "provider_response",
                     "summary": "Container running latest build"}}}

    # 1 — the #2897 prototype verdict on a recovered platform
    ev = evaluate_criterion(crit_ok, ok_resource, sweep_ok)
    assert ev["verdict"] == "PASS" and ev["failedCount"] == 0, ev

    # 2 — degraded resource plane
    ev = evaluate_criterion(crit_ok, {**ok_resource,
                                      "render/render-worker": "degraded"},
                            sweep_ok)
    assert ev["verdict"] == "FAIL" and ev["failedCount"] == 1, ev

    # 3 — the exact #2225 signature: healthy-looking status, forbidden
    #     substring inside the live evidence summary
    sweep_bad = {"render-primary": {
        "status": "healthy",
        "evidence": {"kind": "provider_response",
                     "summary": "Container running previous build, but "
                                "latest deployment update_failed"}}}
    ev = evaluate_criterion(crit_ok, ok_resource, sweep_bad)
    assert ev["verdict"] == "FAIL", ev
    assert "update_failed" in json.dumps(ev["checks"]), ev

    # 4 — declared resource missing from snapshot: fail-closed
    ev = evaluate_criterion(crit_ok, {"render/render-primary": "healthy"},
                            sweep_ok)
    assert ev["verdict"] == "FAIL", ev
    assert any("absent from live snapshot" in c["reason"]
               for c in ev["checks"]), ev

    # 4b — unregistered resource: the tower status plane echoes "healthy"
    #      even for bogus ids (live-grounded 2026-10-30), so the gate marks
    #      them UNREGISTERED from the inventory; the echo must NOT rescue
    #      the predicate.
    ev = evaluate_criterion(
        {"version": 1, "services": [
            {"resourceId": "render/definitely-not-a-resource",
             "allowedStatuses": ["healthy"]}]},
        {"render/definitely-not-a-resource": UNREGISTERED}, {})
    assert ev["verdict"] == "FAIL", ev
    assert any("not in tower resource inventory" in c["reason"]
               for c in ev["checks"]), ev

    # 5 — declared sweep provider missing: fail-closed
    ev = evaluate_criterion(crit_ok, ok_resource, {})
    assert ev["verdict"] == "FAIL", ev

    # 6/7 — platform-audit scoping
    assert scope_applies(["audit:finding", "P1-major"],
                         list(DEFAULT_AUDIT_LABELS)) is True
    assert scope_applies(["status:unclaimed"], list(DEFAULT_AUDIT_LABELS)) \
        is False

    # 8/9 — NO_CRITERION routing: report-only vs strict
    verdict, code, _ = route_verdict(["audit:finding"],
                                     list(DEFAULT_AUDIT_LABELS),
                                     None, False, strict=False)
    assert verdict == "NO_CRITERION" and code == 0, (verdict, code)
    verdict, code, _ = route_verdict(["audit:finding"],
                                     list(DEFAULT_AUDIT_LABELS),
                                     None, False, strict=True)
    assert verdict == "NO_CRITERION" and code == 1, (verdict, code)

    # 10 — unreachable is an honest skip, never a pass
    verdict, code, _ = route_verdict([], list(DEFAULT_AUDIT_LABELS),
                                     None, True)
    assert verdict == "UNREACHABLE" and code == 2, (verdict, code)
    verdict, code, _ = route_verdict(["audit:finding"],
                                     list(DEFAULT_AUDIT_LABELS),
                                     None, True)
    assert verdict == "UNREACHABLE" and code == 2, (verdict, code)

    # 11 — malformed criterion is rejected loudly
    for bad in ({"version": 2}, {}, {"services": [{}]}):
        try:
            evaluate_criterion(bad, ok_resource, sweep_ok)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed criterion accepted: {bad}")

    print("OK: closure_live_state_gate self-test 12/12 cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Closure-time live-state cross-check (#2925 Option A)")
    parser.add_argument("--self-test", action="store_true",
                        help="hermetic fixture verdict-matrix proof (no net)")
    parser.add_argument("--subject", type=int, default=None,
                        help="subject issue number the closing act targets")
    parser.add_argument("--criterion-file", default=None,
                        help="path to the declared recovery criterion JSON")
    parser.add_argument("--criterion-json", default=None,
                        help="inline declared recovery criterion JSON")
    parser.add_argument("--labels", default=",".join(DEFAULT_AUDIT_LABELS),
                        help="comma-separated platform-audit label scope set")
    parser.add_argument("--strict", action="store_true",
                        help="also refuse platform-audit closures that carry "
                             "no declared criterion (NO_CRITERION -> exit 1)")
    parser.add_argument("--emit-evidence", default=None,
                        help="write the full evidence JSON document to PATH")
    parser.add_argument("--tower-url", default=DEFAULT_TOWER_URL,
                        help="tower MCP endpoint override")
    parser.add_argument("--timeout", type=float, default=45.0,
                        help="per-tower-call timeout seconds")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.subject is None:
        parser.error("--subject is required (or use --self-test)")
    return run_gate(args)


if __name__ == "__main__":
    sys.exit(main())
