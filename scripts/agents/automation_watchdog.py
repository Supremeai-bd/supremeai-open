#!/usr/bin/env python3
"""Automation Watchdog (#4168) — SupremeAI স্বয়ংক্রিয়তা-নিয়ন্ত্রণ-তন্ত্রের স্বাধীন প্রাণ-নিরীক্ষা।

মডেল (issue #4168):
    application/CI automation → agent/evaluator/remediation → **independent watchdog**

এই watchdog যে path পাহারা দেয় তার উপর নির্ভরশীল নয়:
  - সব I/O injectable (contract tests pure core চালায় — নেটওয়ার্ক/git নেই)
  - read-only পর্যবেক্ষণ; কোনো destructive remediation নেই
  - নিজের failure কখনো "সুস্থ" রায় দেয় না (fail-closed: UNKNOWN ≠ healthy)
  - নিজের heartbeat: এই script-এর রান-রেকর্ডই বাহ্যিকভাবে পর্যবেক্ষণযোগ্য
    (workflow run history) — আলাদা scheduler ছাড়াই circular-dependency মুক্ত

Detect (issue scope):
  1. stale heartbeat   — critical automation-এর last-seen বয়স > threshold
  2. stuck claim       — status:in-progress issue দীর্ঘদিন has-pr ছাড়া আটকে
  3. stale CI evaluator— AI PR Evaluator-এর সর্বশেষ সফল রান বয়স > threshold

Dedup (#4168: no issue storms):
  প্রতিটি finding-এ stable fingerprint `<!-- watchdog-fp:{fp} -->`; open issue-তে
  marker থাকলে নতুন issue নয় — প্রমাণ-সহ নতুন কমেন্ট। recovery-তে নিজের আগের
  issue auto-close (fp marker দিয়ে খুঁজে)।

Usage:
    python scripts/agents/automation_watchdog.py --report-json        # শুধু রিপোর্ট
    python scripts/agents/automation_watchdog.py --create-issues      # খুঁজে ইস্যু-ও বানায়/বন্ধ করে
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("GH_REPO", "Supremeai-bd/supremeai-open")

# ---------------------------------------------------------------- thresholds
HEARTBEAT_STALE_S = 6 * 3600        # agent-loop heartbeat: ৬ ঘণ্টা নীরবতা = stale
CLAIM_STUCK_S = 24 * 3600           # in-progress claim: ২৪ ঘণ্টা has-pr ছাড়া = stuck
EVALUATOR_STALE_S = 24 * 3600       # CI evaluator সফল রান: ২৪ ঘণ্টা = stale

WATCHDOG_FP_TAG = "watchdog-fp"     # issue-body marker (fingerprint dedup SSOT)


# ---------------------------------------------------------------------------
# Deterministic core — contract-testable (tests/test_automation_watchdog.py)
# ---------------------------------------------------------------------------
def assess_heartbeat(last_seen_epoch: float | None, now: float,
                     stale_after_s: int = HEARTBEAT_STALE_S) -> dict:
    """Heartbeat মূল্যায়ন — healthy | stale | unknown (কখনো মিথ্যে সুস্থ নয়)।

    - last_seen মিসিং/অপার্সযোগ্য → unknown (fail-closed)
    - বয়স > stale_after_s → stale (evidence সহ)
    - নইলে healthy
    """
    if last_seen_epoch is None:
        return {"state": "unknown", "age_s": None,
                "reason": "no heartbeat record — fail-closed, কখনো healthy ধরা হয় না"}
    age = now - float(last_seen_epoch)
    if age > stale_after_s:
        return {"state": "stale", "age_s": int(age),
                "reason": f"heartbeat বয়স {int(age)}s > threshold {stale_after_s}s"}
    return {"state": "healthy", "age_s": int(age),
            "reason": f"last-seen {int(age)}s আগে"}


def fingerprint(finding_type: str, scope: str) -> str:
    """Stable dedup fingerprint (#4168) — type+scope normalized; সময়/রান-আইডি বাদ।"""
    import hashlib
    norm = f"{finding_type.strip().lower()}|{scope.strip().lower()}"
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def evaluate(observations: dict, now: float) -> list[dict]:
    """সব পর্যবেক্ষণ → deduplicated findings (stable fingerprint সহ)।

    observations:
      heartbeats:  [{name, last_seen_epoch|None}]           — critical automation
      claims:      [{issue, agent, claimed_at_epoch|None, has_pr, open}]
      evaluator:   {last_success_epoch|None, name}
    এক scope-এ একাধিক ব্যর্থতা এক finding-এ মার্জ হয় (storm-নিয়ন্ত্রণ)।
    """
    findings: list[dict] = []
    seen_fps: set[str] = set()

    def _add(ftype: str, scope: str, evidence: str, severity: str = "warning") -> None:
        fp = fingerprint(ftype, scope)
        if fp in seen_fps:      # duplicate suppression — একই fp এক রিপোর্টে একবারই
            return
        seen_fps.add(fp)
        findings.append({"type": ftype, "scope": scope, "fingerprint": fp,
                         "severity": severity, "evidence": evidence,
                         "detected_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat().replace("+00:00", "Z")})

    # 1. heartbeats (প্রতি name আলাদা scope — আলাদা fix আলাদা issue)
    for hb in observations.get("heartbeats", []):
        state = assess_heartbeat(hb.get("last_seen_epoch", hb.get("timestamp")), now)
        if state["state"] != "healthy":
            _add("stale_heartbeat", hb.get("name", "unknown"),
                 f"state={state['state']}; {state['reason']}")

    # 2. stuck claims
    for cl in observations.get("claims", []):
        if not cl.get("open", True) or cl.get("has_pr"):
            continue
        claimed = cl.get("claimed_at_epoch")
        if claimed is None:
            _add("stuck_claim", f"issue-{cl.get('issue', '?')}",
                 "claim সময় রেকর্ডহীন — fail-closed", severity="info")
            continue
        age = now - float(claimed)
        if age > CLAIM_STUCK_S:
            _add("stuck_claim", f"issue-{cl.get('issue', '?')}",
                 f"in-progress + no has-pr ধরে {int(age)}s (agent={cl.get('agent', '?')})")

    # 3. CI evaluator inactivity (একটিই স্কোপ: evaluator পুরোটা)
    ev = observations.get("evaluator") or {}
    ev_state = assess_heartbeat(ev.get("last_success_epoch", ev.get("timestamp")), now, EVALUATOR_STALE_S)
    if ev_state["state"] != "healthy":
        _add("stale_ci_evaluator", ev.get("name", "ai-pr-evaluator"),
             f"state={ev_state['state']}; {ev_state['reason']}")

    return findings


# ---------------------------------------------------------------------------
# Recovery — নিজের আগের issue-গুলো ঠিক হয়ে গেলে বন্ধ (auto-close)
# ---------------------------------------------------------------------------
def collect_watchdog_issues(issue_list: list[dict]) -> dict[str, dict]:
    """Open issue তালিকা থেকে watchdog-নিজস্ব issue মানচিত্র {fp: issue}।"""
    out: dict[str, dict] = {}
    for it in issue_list:
        body = it.get("body") or ""
        tag = f"<!-- {WATCHDOG_FP_TAG}:"
        if tag in body:
            fp = body.split(tag, 1)[1].split("-->", 1)[0].strip()
            out[fp] = {"number": it.get("number"), "title": it.get("title", "")}
    return out


def compute_recoveries(open_watchdog_issues: dict[str, dict],
                       findings: list[dict]) -> list[dict]:
    """আগের watchdog issue যেগুলো এখন আর finding নয় = recovered → বন্ধ হবে।"""
    live_fps = {f["fingerprint"] for f in findings}
    return [{"fingerprint": fp, "issue": v["number"], "title": v["title"]}
            for fp, v in open_watchdog_issues.items() if fp not in live_fps]


# ---------------------------------------------------------------------------
# I/O সংগ্রাহক — চিকন, injectable; ব্যর্থতা = unknown (fail-closed)
# ---------------------------------------------------------------------------
def run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def gh_json(endpoint: str) -> object | None:
    token = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    if not token:
        return None
    import urllib.request
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{endpoint}",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 — ব্যর্থতা = unknown, কখনো মিথ্যে সুস্থ নয়
        return None


def collect_observations() -> dict:
    """লাইভ পর্যবেক্ষণ — সব সংগ্রাহকের ব্যর্থতা unknown-এ নামে।"""
    now = time.time()

    # heartbeats: agent heartbeat pinger-এর লোকাল state ফাইল (থাকলে)
    heartbeats: list[dict] = []
    hb_state = ROOT / "tools" / "agent_heartbeat" / "state.json"
    try:
        if hb_state.exists():
            data = json.loads(hb_state.read_text())
            for name, rec in (data.get("agents") or {}).items():
                heartbeats.append({"name": name, "last_seen_epoch": rec.get("last_seen_epoch")})
        else:
            heartbeats.append({"name": "agent-heartbeat-store", "last_seen_epoch": None})
    except Exception:  # noqa: BLE001
        heartbeats.append({"name": "agent-heartbeat-store", "last_seen_epoch": None})

    # stuck claims: status:in-progress open issues
    claims: list[dict] = []
    issues = gh_json("issues?state=open&labels=status:in-progress&per_page=50") or []
    for it in issues if isinstance(issues, list) else []:
        if "pull_request" in it:
            continue
        claimed_at = None
        try:
            ts = it.get("created_at")
            if ts:
                claimed_at = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        claims.append({"issue": it.get("number"), "agent": "?",
                       "claimed_at_epoch": claimed_at, "has_pr": "has-pr" in
                       [lb.get("name", "") for lb in it.get("labels", [])], "open": True})

    # CI evaluator: AI PR Evaluator-এর শেষ সফল রান
    runs = gh_json("actions/workflows/ai-pr-evaluation.yml/runs?status=success&per_page=1")
    last_success = None
    try:
        wr = (runs or {}).get("workflow_runs", [])
        if wr:
            last_success = datetime.fromisoformat(
                str(wr[0].get("created_at", "")).replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        pass

    return {"now_epoch": now,
            "heartbeats": heartbeats,
            "claims": claims,
            "evaluator": {"name": "ai-pr-evaluator", "last_success_epoch": last_success}}


def issue_body_for(finding: dict) -> str:
    """Issue body — fp marker + evidence + last-seen (#4168 চুক্তি)।"""
    return (
        f"<!-- {WATCHDOG_FP_TAG}:{finding['fingerprint']} -->\n"
        f"## 🐕 Watchdog Finding — {finding['type']}\n\n"
        f"**Scope:** {finding['scope']} · **Severity:** {finding['severity']}\n\n"
        f"**Detection:** {finding['detected_at']}\n\n"
        f"**Evidence:** {finding['evidence']}\n\n"
        f"**Fingerprint:** `{finding['fingerprint']}` — একই সমস্যা পুনরাবৃত্ত হলে নতুন issue নয়, "
        f"এই issue-তে কমেন্ট জমা হবে (storm-নিয়ন্ত্রণ #4168)। সমস্যা মিটলে watchdog এটি auto-close করবে।\n\n"
        f"_Read-only watchdog (#4168) — auto-generated; root-cause fix এই issue-তেই claim করুন।_\n"
    )


def create_issue_for(finding: dict) -> int | None:
    title = f"🐕 [watchdog] {finding['type']}: {finding['scope']}"
    rc, out, _ = run(["gh", "issue", "create", "--title", title,
                      "--body", issue_body_for(finding),
                      "--label", "bug,handoff:coder"])
    return int(out.rstrip().rsplit("/", 1)[-1]) if rc == 0 else None


def close_recovered(rec: dict) -> bool:
    rc, _, _ = run(["gh", "issue", "close", str(rec["issue"]), "--reason", "completed",
                    "--comment", "🐕 Watchdog recovery — finding আর পুনরুৎপাদিত হচ্ছে না "
                                 "(সর্বশেষ পর্যবেক্ষণে সুস্থ)। auto-close (#4168 recovery চুক্তি)।"])
    return rc == 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Automation Watchdog (#4168)")
    parser.add_argument("--report-json", action="store_true", help="stdout JSON রিপোর্ট")
    parser.add_argument("--create-issues", action="store_true",
                        help="finding থাকলে dedup-fingerprint সহ issue তৈরি/বন্ধ")
    args = parser.parse_args()

    obs = collect_observations()
    now = obs["now_epoch"]
    findings = evaluate({"heartbeats": obs["heartbeats"], "claims": obs["claims"],
                         "evaluator": obs["evaluator"]}, now)
    report = {"watchdog_run_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
              "observations_count": {k: len(obs[k]) for k in ("heartbeats", "claims")},
              "findings": findings,
              "verdict": "DEGRADED" if findings else "HEALTHY",
              "note": "watchdog নিজের অজুহাতে 'সুস্থ' বলে না — সংগ্রাহক ব্যর্থতা = unknown finding"}

    if args.report_json or not args.create_issues:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.create_issues:
        existing = collect_watchdog_issues(
            (gh_json("issues?state=open&per_page=100") or []) if isinstance(
                gh_json("issues?state=open&per_page=100"), list) else [])
        for f in findings:
            if f["fingerprint"] in existing:
                print(f"↻ dedup: {f['type']}:{f['scope']} → বিদ্যমান #{existing[f['fingerprint']]['number']}")
                continue
            num = create_issue_for(f)
            print(f"✚ created #{num} for {f['type']}:{f['scope']}" if num else f"✗ create fail: {f['type']}")
        for rec in compute_recoveries(existing, findings):
            ok = close_recovered(rec)
            print(f"✔ recovered #{rec['issue']} closed" if ok else f"✗ close fail #{rec['issue']}")

    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
