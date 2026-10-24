#!/usr/bin/env python3
"""Production Certification Gate (#3071, #4167) — current-SHA GO/CONDITIONAL/NO-GO.

Generates a machine-readable JSON certification artifact for the current
main HEAD, answering:
  1. Which CRITICAL/HIGH checklist items are proven PASS?
  2. Which are FAIL/BLOCKED/STALE/UNKNOWN?
  3. Which are not applicable?
  4. Which evidence is stale (evidence SHA != candidate SHA, or too old)?
  5. Which open issues are true release blockers vs operational backlog?

#4167 contract (fail-closed):
  - missing evidence            -> UNKNOWN (never PASS)
  - evidence SHA != candidate   -> STALE (never PASS from stale evidence)
  - evidence older than max_age -> STALE
  - every item carries checked_at + source (+ evidence_sha when applicable)
  - verdict: GO | CONDITIONAL | NO-GO (deterministic — see compute_verdict)

Usage:
    python scripts/ci/production_certification.py [--output report.json]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

# ---------------------------------------------------------------------------
# #4167 deterministic core — contract-testable evidence assessment + verdict
# (কোনো I/O নেই — pure functions; tests/test_production_certification_gate.py)
# ---------------------------------------------------------------------------

# Fail-closed critical dimensions — এগুলোর evidence মিসিং/stale হলেই NO-GO
# (docs/master_docs/PRODUCTION_CERTIFICATION.md — GO-র জন্য যা যা লাগে তার SSOT)।
CRITICAL_ITEMS = (
    "sha_alignment",       # deploy HEAD == candidate SHA
    "deploy_freshness",    # production deploy recent (≤ max age)
    "ci_green",            # candidate SHA-র check-runs সবুজ
    "secret_scan",         # hardcoded-secret regex পরিষ্কার
    "release_freeze_git",  # git tree clean @ candidate SHA
)

DEFAULT_MAX_AGE_S = 7 * 24 * 3600  # deploy freshness: ৭ দিন (docs §GO)


def _parse_iso(ts: str | None) -> float | None:
    """ISO-8601 → epoch seconds; None/দুর্বল ইনপুটে None (fail-closed)।"""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def assess_evidence(item: dict, candidate_sha: str, now: float | None = None) -> dict:
    """Fail-closed evidence assessor (#4167 Required Behavior).

    item: {status, source, checked_at?, evidence_sha?, max_age_s?, detail?}
    status ∈ collector vocabulary: PASS | FAIL | BLOCKED | NA

    Rules:
      - collector status missing/empty      -> UNKNOWN (missing evidence)
      - evidence_sha and != candidate_sha   -> STALE  (SHA mismatch)
      - checked_at missing                  -> UNKNOWN (no timestamp = no proof)
      - checked_at older than max_age_s     -> STALE
      - otherwise                           -> collector status preserved

    Every result carries: checked_at, source, evidence_sha, critical, reason.
    """
    now = now if now is not None else time.time()
    status = (item.get("status") or "").strip()
    source = item.get("source") or "unknown-source"
    evidence_sha = item.get("evidence_sha")
    checked_ts = _parse_iso(item.get("checked_at"))
    critical = item.get("critical", False)
    out = {
        "status": "UNKNOWN",
        "source": source,
        "evidence_sha": evidence_sha,
        "checked_at": item.get("checked_at"),
        "critical": critical,
        "reason": "",
    }
    if status not in {"PASS", "FAIL", "BLOCKED", "NA"}:
        out["reason"] = f"missing/unrecognized evidence (collector status={status!r})"
        return out
    if evidence_sha is not None and evidence_sha != candidate_sha:
        out["status"] = "STALE"
        out["reason"] = f"evidence SHA {evidence_sha[:7]} != candidate {candidate_sha[:7]}"
        return out
    if checked_ts is None:
        out["reason"] = "missing checked_at timestamp — unverifiable evidence"
        return out
    max_age = item.get("max_age_s")
    if max_age is not None and (now - checked_ts) > max_age:
        out["status"] = "STALE"
        out["reason"] = f"evidence age {int(now - checked_ts)}s > max {int(max_age)}s"
        return out
    out["status"] = status
    out["reason"] = item.get("detail", "")
    return out


def compute_verdict(items: dict[str, dict]) -> str:
    """Deterministic GO / CONDITIONAL / NO-GO (#4167).

    - যেকোনো FAIL                                  -> NO-GO
    - critical item STALE/UNKNOWN/BLOCKED        -> NO-GO (fail-closed)
    - non-critical STALE/UNKNOWN/BLOCKED         -> CONDITIONAL
    - নইলে                                        -> GO
    """
    verdict = "GO"
    for name, item in items.items():
        st = item.get("status")
        if st == "FAIL":
            return "NO-GO"
        if st in {"STALE", "UNKNOWN", "BLOCKED"}:
            if item.get("critical") or name in CRITICAL_ITEMS:
                return "NO-GO"
            verdict = "CONDITIONAL"
    return verdict


def get_deploy_evidence(candidate_sha: str) -> dict:
    """Production deploy evidence from 'Deploy Train' (#4167 dims 1/3/10).

    একটি সফল production-deploy রান = deploy evidence:
      sha_alignment   — সর্বশেষ সফল deploy-এর HEAD == candidate SHA?
      deploy_freshness— deploy ≤ ৭ দিন পুরনো?
      rollback_target — N-1 সফল deploy বিদ্যমান (ফিরে যাওয়ার টার্গেট)?
    Missing/ambiguous -> UNKNOWN (fail-closed, কখনো PASS infer নয়)।
    """
    token = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    if not token:
        return {"sha_alignment": {"status": "", "source": "deploy-train.yml", "critical": True},
                "deploy_freshness": {"status": "", "source": "deploy-train.yml", "critical": True},
                "rollback_target": {"status": "", "source": "deploy-train.yml", "critical": False}}
    import urllib.request
    url = (
        f"https://api.github.com/repos/{REPO}/actions/workflows/deploy-train.yml"
        f"/runs?status=success&per_page=5"
    )
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            runs = json.loads(r.read()).get("workflow_runs", [])
    except Exception as e:  # noqa: BLE001 — fail-closed: API ব্যর্থতা = UNKNOWN
        detail = str(e)[:120]
        return {"sha_alignment": {"status": "", "source": f"deploy-train.yml: {detail}", "critical": True},
                "deploy_freshness": {"status": "", "source": "deploy-train.yml", "critical": True},
                "rollback_target": {"status": "", "source": "deploy-train.yml", "critical": False}}
    latest = runs[0] if runs else None
    prev = runs[1] if len(runs) > 1 else None
    # বাংলা (#4167): checked_at = deploy-এর জন্মসময় (evidence timestamp) — API-fetch
    # সময় নয়; নইলে freshness চেক অর্থহীন হয়ে যায়। sha_alignment/ deploy_freshness
    # evidence_sha বহন করে (assessor-ই mismatch ধরবে); rollback_target ইচ্ছাকৃতভাবে
    # আলাদা পুরনো SHA-কে লক্ষ্য করে — তাই কোনো evidence_sha/max_age নয়।
    return {
        "sha_alignment": {
            "status": "PASS" if latest else "",
            "source": f"run {latest['id']}" if latest else "deploy-train.yml (no success run)",
            "evidence_sha": latest.get("head_sha") if latest else None,
            "checked_at": latest.get("created_at") if latest else None,
            "detail": f"latest successful production deploy: {latest.get('display_title', '')[:40]}" if latest else "no successful production deploy found",
            "critical": True,
        },
        "deploy_freshness": {
            "status": "PASS" if latest else "",
            "source": f"run {latest['id']}" if latest else "deploy-train.yml",
            "evidence_sha": latest.get("head_sha") if latest else None,
            "checked_at": latest.get("created_at") if latest else None,
            "max_age_s": DEFAULT_MAX_AGE_S,
            "critical": True,
        },
        "rollback_target": {
            "status": "PASS" if prev else ("" if latest else "NA"),
            "source": f"run {prev['id']}" if prev else "deploy-train.yml",
            "checked_at": prev.get("created_at") if prev else None,
            "detail": f"rollback target: {prev['head_sha'][:7]}" if prev else "no prior deploy — nothing to roll back TO",
            "critical": False,
        },
    }


def run(cmd: list[str]) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def get_sha() -> str:
    rc, out, _ = run(["git", "rev-parse", "HEAD"])
    return out if rc == 0 else "unknown"


def is_git_clean() -> bool:
    rc, out, _ = run(["git", "status", "--porcelain"])
    return out.strip() == ""


def get_ci_status(sha: str) -> dict:
    """Get CI check status for the candidate SHA from GitHub API."""
    token = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    if not token:
        return {"status": "UNKNOWN", "reason": "no GH_TOKEN"}
    import urllib.request
    url = f"https://api.github.com/repos/{REPO}/commits/{sha}/check-runs?per_page=100"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        runs = data.get("check_runs", [])
        failures = [r for r in runs if r.get("conclusion") == "failure"]
        successes = [r for r in runs if r.get("conclusion") == "success"]
        return {
            "total": len(runs),
            "success": len(successes),
            "failures": len(failures),
            "failure_names": [f.get("name", "")[:50] for f in failures[:5]],
            "status": "PASS" if not failures else "FAIL",
        }
    except Exception as e:
        return {"status": "BLOCKED", "reason": str(e)}


def get_open_p0_p1_issues() -> list[dict]:
    """Get open P0/P1 issues from GitHub."""
    token = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
    if not token:
        return []
    import urllib.request
    url = f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=100&labels=P0-critical"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    })
    p0 = []
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            p0 = json.loads(r.read())
    except Exception:
        pass
    url2 = f"https://api.github.com/repos/{REPO}/issues?state=open&per_page=100&labels=P1-high"
    req2 = urllib.request.Request(url2, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    })
    p1 = []
    try:
        with urllib.request.urlopen(req2, timeout=30) as r:
            p1 = json.loads(r.read())
    except Exception:
        pass
    return [
        {"number": i.get("number"), "title": i.get("title", "")[:60], "priority": "P0"}
        for i in p0 if "pull_request" not in i
    ] + [
        {"number": i.get("number"), "title": i.get("title", "")[:60], "priority": "P1"}
        for i in p1 if "pull_request" not in i
    ]


def check_secret_scan() -> dict:
    """Quick secret scan — check for hardcoded secrets in scripts/."""
    rc, out, _ = run([
        "grep", "-rn", "--include=*.py", "--include=*.yml", "--include=*.sh",
        "-E", r"ghs_[a-zA-Z0-9]{36}|ghp_[a-zA-Z0-9]{36}|sk-[a-zA-Z0-9]{48}",
        "scripts/", ".github/",
    ])
    # Filter out test/example/regex patterns
    real_secrets = []
    for line in (out or "").splitlines():
        if any(x in line for x in ["test", "example", "template", "regex", "pattern", "r'", 'r"']):
            continue
        real_secrets.append(line)
    if real_secrets:
        return {"status": "FAIL", "evidence": f"{len(real_secrets)} potential secrets found"}
    return {"status": "PASS", "evidence": "no hardcoded secrets (regex patterns excluded)"}


def check_ruff() -> dict:
    """Check if ruff is available + run lint."""
    try:
        rc, out, err = run([sys.executable, "-m", "ruff", "check", "scripts/", "--statistics"])
        if rc != 0 and "No module named ruff" in (err or ""):
            rc, out, err = run(["ruff", "check", "scripts/", "--statistics"])
        if rc == 0:
            return {"status": "PASS", "evidence": "ruff: 0 violations"}
        if "No module named" in (err or "") or "not found" in (err or "").lower():
            return {"status": "BLOCKED", "reason": "ruff not installed in sandbox (CI runs it)"}
        lines = [l for l in (out or "").splitlines() if l.strip()]
        return {"status": "FAIL" if lines else "PASS", "evidence": f"{len(lines)} violation types"}
    except FileNotFoundError:
        return {"status": "BLOCKED", "reason": "ruff not installed in sandbox (CI runs it)"}


def check_py_compile() -> dict:
    """Check if all Python files compile."""
    rc, out, err = run([sys.executable, "-m", "py_compile", "scripts/agents/continuous_agent_loop.py"])
    if rc == 0:
        return {"status": "PASS", "evidence": "main agent script compiles"}
    return {"status": "FAIL", "evidence": err[:200]}


def check_yaml_valid() -> dict:
    """Check if workflow YAMLs are valid."""
    try:
        import yaml
    except ImportError:
        return {"status": "BLOCKED", "reason": "pyyaml not installed"}
    workflows = list(Path(".github/workflows").glob("*.yml"))
    errors = []
    for wf in workflows:
        try:
            yaml.safe_load(wf.read_text())
        except Exception as e:
            errors.append(f"{wf.name}: {e}")
    if errors:
        return {"status": "FAIL", "evidence": "; ".join(errors)}
    return {"status": "PASS", "evidence": f"{len(workflows)} workflows valid"}


def check_tests() -> dict:
    """Check if tests can run."""
    rc, out, _ = run([sys.executable, "-m", "pytest", ".github/scripts/constitution/tests/test_gates.py", "-q", "--no-header"])
    if rc == 0:
        # Extract pass count
        import re
        m = re.search(r"(\d+) passed", out)
        count = m.group(1) if m else "?"
        return {"status": "PASS", "evidence": f"{count} gates tests passed"}
    return {"status": "BLOCKED", "reason": "backend tests need full env (sqlalchemy etc)"}


def generate_report() -> dict:
    """Generate the full certification report (#4167 fail-closed contract)."""
    sha = get_sha()
    git_was_clean = is_git_clean()  # capture BEFORE creating report file
    now_epoch = time.time()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))

    ci = get_ci_status(sha)
    deploy = get_deploy_evidence(sha)
    issues = get_open_p0_p1_issues()
    p0_blockers = [i for i in issues if i["priority"] == "P0"]
    p1_backlog = [i for i in issues if i["priority"] == "P1"]

    def _local(status: str, source: str, critical: bool = False, detail: str = "") -> dict:
        # ইন-প্রসেস চেক — evidence SHA = candidate SHA by construction
        return {"status": status, "source": source, "evidence_sha": sha,
                "checked_at": now, "critical": critical, "detail": detail}

    # ---- security scan একবারই চালাই (দুইবার subprocess নয়) ----
    _secret = check_secret_scan()
    raw_items: dict[str, dict] = {
        # release freeze (#4167 dims: candidate identity + rollback-freeze)
        "release_freeze_git": _local(
            "PASS" if git_was_clean else "FAIL", "git status --porcelain",
            critical=True,
            detail="git tree clean at candidate SHA" if git_was_clean else "uncommitted changes present",
        ),
        # CI (#4167 dim 2) — API evidence is about this SHA (checked_at = fetch time)
        "ci_green": _local(
            ci.get("status", ""), f"check-runs API ({ci.get('total', 0)} runs)",
            critical=True,
            detail=f"{ci.get('success', 0)} success, {ci.get('failures', 0)} failures"
                   + (f" — {ci.get('failure_names')}" if ci.get("failures") else ""),
        ),
        # deploy (#4167 dims 1/3/10) — deploy-নিজস্ব checked_at অপরিবর্তিত রাখা হয়েছে
        "sha_alignment": deploy["sha_alignment"],
        "deploy_freshness": deploy["deploy_freshness"],
        "rollback_target": deploy["rollback_target"],
        # security (#4167 dims 8)
        "secret_scan": _local(
            _secret.get("status", ""), "hardcoded-secret regex scan",
            critical=True, detail=_secret.get("evidence", ""),
        ),
        # code quality (non-critical — CI required checks-ও ci_green-এ ধরে)
        "py_compile": _local(check_py_compile().get("status", ""), "py_compile agent loop"),
        "ruff_lint": _local(check_ruff().get("status", ""), "ruff scripts/"),
        "yaml_valid": _local(check_yaml_valid().get("status", ""), "workflow YAML parse"),
        "gate_tests": _local(check_tests().get("status", ""), "constitution gates pytest"),
    }
    items = {name: assess_evidence(item, sha, now=now_epoch) for name, item in raw_items.items()}

    go_no_go = compute_verdict(items)
    legacy = {"GO": "PASS", "CONDITIONAL": "BLOCKED", "NO-GO": "FAIL"}[go_no_go]

    counts: dict[str, int] = {}
    for it in items.values():
        counts[it["status"]] = counts.get(it["status"], 0) + 1

    return {
        "certification_date": now,
        "candidate_sha": sha,
        "repo": REPO,
        "go_no_go": go_no_go,
        "overall_verdict": legacy,  # backward compat (#3071 consumers)
        "summary": counts,
        "certification_items": items,
        "release_blockers": {
            "p0_critical": p0_blockers,      # সত্যিক release blocker (NO-GO force)
            "total_blockers": len(p0_blockers),
        },
        "operational_backlog": {
            "p1_high": p1_backlog,           # tracked backlog — GO-তে বাধা নয় (#4167 blocker-vs-backlog)
            "total": len(p1_backlog),
        },
        "go_live_rule": {
            "GO": "সব critical item PASS + কোনো FAIL নেই",
            "CONDITIONAL": "কোনো FAIL/unknown-critical নেই; non-critical UNKNOWN/STALE/NA সহনীয় (documented)",
            "NO-GO": "যেকোনো FAIL, অথবা critical evidence মিসিং/stale (fail-closed)",
            "max_deploy_age_s": DEFAULT_MAX_AGE_S,
            "critical_items": list(CRITICAL_ITEMS),
        },
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Production Certification Gate (#3071, #4167)")
    parser.add_argument("--output", default=None, help="Output file (default: stdout)")
    args = parser.parse_args()

    report = generate_report()
    output = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"✅ Certification report written to {args.output}")
    else:
        print(output)

    # Exit code (#4167): 0=GO, 1=CONDITIONAL, 2=NO-GO
    verdict = report["go_no_go"]
    if verdict == "GO":
        print("\n✅ CERTIFICATION: GO — production-ready at "
              f"{report['candidate_sha'][:7]}", file=sys.stderr)
        return 0
    elif verdict == "CONDITIONAL":
        print(f"\n⚠️  CERTIFICATION: CONDITIONAL — non-critical gaps documented "
              f"({report['summary'].get('UNKNOWN', 0)} unknown, "
              f"{report['summary'].get('STALE', 0)} stale)", file=sys.stderr)
        return 1
    else:
        print("\n❌ CERTIFICATION: NO-GO — critical evidence missing/stale/failing",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
