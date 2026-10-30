#!/usr/bin/env python3
"""Closure-time live-state gate — mechanical cross-check before any closing artifact.

Lineage: #2132 (queue_consistency_probe) family. Filed as scout(R79) #2925,
proposal Option A, repo-reachable slice.

What this is
------------
Before a closing artifact is produced for a platform-audit subject issue
(merge auto-close, verdict write, closing comment), this probe evaluates the
issue's OWN declared recovery criterion against zero-credential tower read
tools (resource_status / health_full_sweep). It is the mechanical after of the
manual prototype executed in #2897 (29th proof sweep).

Verdict contract (#2704 shape — "a silently under-scanned sweep is worse than
a loud failure", applied to the closing act):

    exit 0  PASS      -> closing artifact may proceed; evidence JSON on stdout
    exit 2  REFUSED   -> criterion FAILED: closing artifact is refused, run is
                         downgraded to evidence-only; stderr fail-loud line +
                         evidence JSON (criterion output attached) on stdout
    exit 3  UNKNOWN   -> tower unreachable / resource unknown / subject not in
                         registry: fail-loud, NEVER treated as pass

Scope honesty (what this slice deliberately does NOT do):
- It does not block the tower-side auto-resolve writer itself (controller slice
  -> Option B, tower-owner lane). It gives every repo-reachable actor and guard
  a mechanical, auditable refusal signal.
- Registry covers subjects whose recovery criterion the audit chain already
  established verbatim on the board. Unknown subjects exit 3 (loud), so the
  gate cannot be silently bypassed by an unregistered subject.

Usage:
    python3 scripts/closure_live_state_gate.py --subject 2225 \
        [--closing-artifact "merge auto-close for #2225"] \
        [--tower-url https://supremeai-mcp-tower.onrender.com/mcp] \
        [--evidence-out /tmp/gate_2225.json]

Exit codes: 0 PASS, 2 REFUSED (criterion FAILED), 3 UNKNOWN (fail-loud),
            4 usage/internal error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

TOWER_URL_DEFAULT = "https://supremeai-mcp-tower.onrender.com/mcp"

# ---------------------------------------------------------------------------
# Recovery-criterion registry — verbatim sources from the audit chain.
# Each entry: source ticket(s) + mechanical predicates. Predicates are
# conservative: anything that cannot be positively confirmed counts as FAIL.
# ---------------------------------------------------------------------------

CRITERIA_REGISTRY: dict = {
    "2225": {
        "source": "#2738 recovery criterion (recovery sweep #2897 29th proof)",
        "verbatim": (
            "both services' updatedAt advance past 2026-10-24T08:32:47Z "
            "AND lastDeployStatus: live"
        ),
        "subject_title_hint": "render-primary / render-worker update_failed while HTTP 200",
        "predicates": [
            {
                "kind": "resource_status_in",
                "resourceId": "render/render-primary",
                "allowed": ["healthy", "live"],
            },
            {
                "kind": "resource_status_in",
                "resourceId": "render/render-worker",
                "allowed": ["healthy", "live"],
            },
            {
                "kind": "health_evidence_not_contains",
                "resourceId": "render/render-primary",
                "needle": "update_failed",
            },
            {
                "kind": "health_evidence_not_contains",
                "resourceId": "render/render-worker",
                "needle": "update_failed",
            },
            {
                "kind": "policy_pending_empty",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Tower client (zero-credential MCP JSON-RPC, session per run)
# ---------------------------------------------------------------------------

def tower_rpc(tower_url: str, session: str | None, payload: dict, timeout: float = 30.0):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session:
        headers["mcp-session-id"] = session
    req = urllib.request.Request(
        tower_url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sid = resp.headers.get("mcp-session-id")
        body = resp.read().decode()
    return sid, body


def tower_call(tool: str, arguments: dict, tower_url: str, timeout: float = 30.0) -> dict:
    """Initialize a throwaway MCP session and call one read tool."""
    sid, body = tower_rpc(
        tower_url,
        None,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "closure-live-state-gate", "version": "1.0"},
            },
        },
        timeout=timeout,
    )
    tower_rpc(tower_url, sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    payload = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    _, body = tower_rpc(tower_url, sid, payload, timeout=timeout)
    for line in body.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if "error" in data:
                raise RuntimeError(f"tower tool error: {data['error']}")
            texts = [
                c.get("text", "")
                for c in data.get("result", {}).get("content", [])
                if c.get("type") == "text"
            ]
            out = "\n".join(texts)
            try:
                return json.loads(out)
            except (json.JSONDecodeError, ValueError):
                return {"raw": out}
    raise RuntimeError("tower returned no SSE data payload")


# ---------------------------------------------------------------------------
# Fetcher abstraction: production fetcher hits tower; tests inject mocks.
# ---------------------------------------------------------------------------

def default_fetch(tool: str, arguments: dict) -> dict:
    return tower_call(tool, arguments, TOWER_URL_DEFAULT)


# ---------------------------------------------------------------------------
# Predicate evaluation — every unknown/missing datum is a FAIL, never a pass.
# ---------------------------------------------------------------------------

def eval_predicate(pred: dict, fetch) -> dict:
    kind = pred.get("kind")

    if kind == "resource_status_in":
        try:
            res = fetch("resource_status", {"resourceId": pred["resourceId"]})
        except Exception as exc:  # unreachable tower counts as UNKNOWN upstream
            raise TowerUnreachable(f"resource_status {pred['resourceId']}: {exc}") from exc
        status = str(res.get("status", "")).lower()
        allowed = {a.lower() for a in pred.get("allowed", [])}
        ok = status in allowed
        return {
            "kind": kind,
            "resourceId": pred["resourceId"],
            "observed": status or None,
            "allowed": sorted(allowed),
            "verdict": "PASS" if ok else "FAIL",
        }

    if kind == "health_evidence_not_contains":
        rid = pred["resourceId"]
        needle = pred["needle"]
        short = rid.split("/", 1)[-1]
        try:
            sweep = fetch("health_full_sweep", {})
        except Exception as exc:
            raise TowerUnreachable(f"health_full_sweep: {exc}") from exc
        snapshot, checked_at = None, None
        # Real shape: snapshots is a dict keyed by provider name; each entry
        # carries status / checkedAt / evidence {kind, summary}. A legacy
        # services-list shape is tolerated alongside.
        snapshots = sweep.get("snapshots") if isinstance(sweep, dict) else None
        if isinstance(snapshots, dict):
            for key, snap in snapshots.items():
                prov = str(snap.get("provider", "")) if isinstance(snap, dict) else ""
                if short == key or short == prov or key.endswith(short):
                    snapshot, checked_at = snap, (snap or {}).get("checkedAt")
                    break
        if snapshot is None and isinstance(sweep, dict):
            for svc in sweep.get("services") or []:
                name = str(svc.get("name") or svc.get("resourceId") or svc.get("id") or "")
                if short in name:
                    snapshot, checked_at = svc, svc.get("checkedAt")
                    break
        if not isinstance(snapshot, dict):
            return {
                "kind": kind,
                "resourceId": rid,
                "observed": "evidence-plane-missing",
                "verdict": "FAIL",
            }
        ev = snapshot.get("evidence")
        evidence_text = ev.get("summary", "") if isinstance(ev, dict) else str(ev or "")
        status = str(snapshot.get("status", ""))
        hit = needle.lower() in evidence_text.lower() if evidence_text else None
        if hit is None:
            return {
                "kind": kind,
                "resourceId": rid,
                "observed": f"snapshot-present-but-evidence-empty(status={status or 'unknown'})",
                "verdict": "FAIL",
            }
        return {
            "kind": kind,
            "resourceId": rid,
            "needle": needle,
            "checkedAt": checked_at,
            "snapshotStatus": status,
            "evidence_excerpt": evidence_text[:240],
            "verdict": "FAIL" if hit else "PASS",
        }

    if kind == "policy_pending_empty":
        try:
            pend = fetch("policy_list_pending", {})
        except Exception as exc:
            raise TowerUnreachable(f"policy_list_pending: {exc}") from exc
        # Real shape is a bare array; dict shapes tolerated (#2704: parse wide,
        # judge loud — never treat an unparseable plane as a pass).
        items = pend if isinstance(pend, list) else None
        if items is None and isinstance(pend, dict):
            items = pend.get("pending", pend.get("items"))
        if items is None:
            return {"kind": kind, "observed": "unreadable", "verdict": "FAIL"}
        return {"kind": kind, "pending_count": len(items), "verdict": "PASS" if not items else "FAIL"}

    return {"kind": str(kind), "observed": "unrecognized-predicate-kind", "verdict": "FAIL"}


class TowerUnreachable(Exception):
    """Raised when a tower read is impossible — maps to exit 3 UNKNOWN."""


def evaluate_criterion(entry: dict, fetch) -> dict:
    results = []
    for pred in entry.get("predicates", []):
        results.append(eval_predicate(pred, fetch))
    verdict = "PASS" if all(r["verdict"] == "PASS" for r in results) else "FAIL"
    return {"verdict": verdict, "predicates": results}


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------

def run_gate(subject: str, closing_artifact: str | None, fetch, now_iso: str | None = None) -> dict:
    entry = CRITERIA_REGISTRY.get(str(subject))
    if entry is None:
        return {
            "verdict": "UNKNOWN",
            "reason": "subject-not-in-registry",
            "subject": subject,
            "registeredSubjects": sorted(CRITERIA_REGISTRY.keys()),
            "checkedAt": now_iso or datetime.now(timezone.utc).isoformat(),
        }
    try:
        outcome = evaluate_criterion(entry, fetch)
    except TowerUnreachable as exc:
        return {
            "verdict": "UNKNOWN",
            "reason": "tower-unreachable",
            "detail": str(exc),
            "subject": subject,
            "checkedAt": now_iso or datetime.now(timezone.utc).isoformat(),
        }
    evidence = {
        "gate": "closure_live_state_gate",
        "lineage": "#2132 queue_consistency_probe family; scout(R79) #2925 Option A repo-reachable slice",
        "subject": subject,
        "criterionSource": entry.get("source"),
        "criterionVerbatim": entry.get("verbatim"),
        "closingArtifact": closing_artifact,
        "checkedAt": now_iso or datetime.now(timezone.utc).isoformat(),
        **outcome,
    }
    if evidence["verdict"] == "FAIL" and closing_artifact:
        evidence["adjudication"] = (
            f"CLOSING REFUSED for '{closing_artifact}' — downgrade to evidence-only "
            f"(criterion FAILED; attach this evidence to the proof plane)"
        )
    return evidence


EXIT_CODES = {"PASS": 0, "FAIL": 2, "UNKNOWN": 3}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Closure-time live-state gate (R79/#2925 Option A slice)")
    ap.add_argument("--subject", required=True, help="subject issue number (registry key)")
    ap.add_argument("--closing-artifact", default=None, help="description of the closing act being gated")
    ap.add_argument("--tower-url", default=TOWER_URL_DEFAULT)
    ap.add_argument("--evidence-out", default=None, help="write evidence JSON to this path as well")
    args = ap.parse_args(argv)

    def fetch(tool, arguments):
        return tower_call(tool, arguments, args.tower_url)

    evidence = run_gate(args.subject, args.closing_artifact, fetch)
    payload = json.dumps(evidence, indent=2, ensure_ascii=False)
    if args.evidence_out:
        with open(args.evidence_out, "w") as fh:
            fh.write(payload + "\n")
    verdict = evidence.get("verdict", "UNKNOWN")
    if verdict == "FAIL":
        print(
            f"CLOSURE GATE: REFUSED — subject #{args.subject} recovery criterion FAILED "
            f"(fail-loud, #2704 shape); closing artifact downgraded to evidence-only",
            file=sys.stderr,
        )
    elif verdict == "UNKNOWN":
        print(
            f"CLOSURE GATE: UNKNOWN — {evidence.get('reason', 'unreadable plane')}; "
            f"refusing to pass silently (a silently under-scanned sweep is worse than a loud failure)",
            file=sys.stderr,
        )
    print(payload)
    return EXIT_CODES.get(verdict, 3)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # internal error -> loud, never a silent pass
        print(f"CLOSURE GATE: INTERNAL ERROR — {exc}", file=sys.stderr)
        sys.exit(4)
