# S08 — Mistake Immunity / Bridge Opener Hardening Spec (task #485)

Status: r1 · 2026-10-17 · Author: Z.ai Code (session web-26454b1b)
Scope: exact hunks for `scripts/ci/auto_bridge_pr_opener.py` (pre-existing,
operator-side) + regression additions for `tests/test_ci_guards.py`.
Offline reference + tests ship new-file: `scripts/ci/bridge_opener_hardening_reference.py`,
`tests/test_s08_mistake_immunity.py` (29 tests). Eliminates the 4
intake friction points: claim hoarding (#479 enforcement cross-check),
brittle punctuation check, lossy PR body generation (Knowledge Sharing
Guard #392 failures), stale base drift (Stale-Base Guard #161).

## 1. Fix 2 — Robust punctuation parser (opener line ~170)

Hunk A — `wo_carries_reflection` regex (task-literal):

```python
# BEFORE:
    return bool(re.search(r"Reflection\s*:\s*\S", wo_body or "", re.IGNORECASE))
# AFTER:
    return bool(re.search(r"Reflection\s*[:\u2014\u2013-]\s*\S", wo_body or "", re.IGNORECASE))
```

Accepts colon, em-dash, en-dash, hyphen. Case-insensitive and unanchored
exactly as the task specifies. Empty body stays fail-closed (False).

## 2. Fix 3 — Lossless PR body transfer

Hunk B — insert after `wo_carries_reflection`:

```python
EVIDENCE_HEADINGS = ("## Test Evidence", "## Reflection Evidence")


def extract_evidence_sections(wo_body: str) -> str:
    """Lossless evidence transfer (#485): carry the WO's Test Evidence /
    Reflection Evidence sections VERBATIM (including the
    (why + alternatives_rejected) heading suffix and the
    - **why:** / - **alternatives_rejected:** bullets) into the PR body
    so Knowledge Sharing Guard (#392) passes first-shot. Heading match is
    prefix-based; each section ends before the next "## " heading.
    Missing sections -> empty string (PR body shape unchanged)."""
    sections: list[str] = []
    lines = (wo_body or "").splitlines()
    for heading in EVIDENCE_HEADINGS:
        capture = False
        buf: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(heading):
                capture = True
                buf.append(line)
                continue
            if capture and stripped.startswith("## "):
                break
            if capture:
                buf.append(line)
        if buf:
            sections.append("\n".join(buf).strip())
    return "\n\n".join(sections)
```

Hunk C — in `create_pr_for_work_order`, build and append the sections:

```python
# BEFORE (pr_body f-string ends with):
Refs #{wo_num}
"""
# AFTER:
    evidence_sections = extract_evidence_sections(body)
    pr_body = f"""## Claim & Work Order
Submitted via [Bridge Work Order #{wo_num}](https://github.com/{repo}/issues/{wo_num}) on branch `{branch}`.

## Summary & Purpose
{pr_title}

{closes_line}
Closes #{wo_num}
Refs #{wo_num}
{evidence_sections}"""
```

## 3. Fix 4 — Fresh-base checkout / auto-sync

Hunk D — insert after `get_existing_pr_for_branch`:

```python
def fetch_origin_main_sha(repo: str = UPSTREAM_REPO) -> str | None:
    """#485: latest origin/main SHA before evaluating branches."""
    cmd = ["git", "ls-remote", f"https://github.com/{repo}.git", "main"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.split()[0]
    except Exception:
        pass
    return None


def branch_base_status(branch: str, repo: str = UPSTREAM_REPO) -> str | None:
    """#485: GitHub compare status main...branch
    (ahead | identical | behind | diverged | None on error)."""
    cmd = ["gh", "api", f"repos/{repo}/compare/main...{branch}", "--jq", ".status"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            return res.stdout.strip() or None
    except Exception:
        pass
    return None
```

Hunk E — in the `run_auto_bridge_pr_opener` loop, after the
existing-PR skip and before the Claim Gate block:

```python
# Stale-Base Guard prevention (#485): evaluate base drift first.
status = branch_base_status(branch, repo)
if status in ("behind", "diverged"):
    print(
        f"  [WO #{wo_num}] Branch base is {status} vs main; "
        f"attempting clean rebase onto origin/main."
    )
    if auto_open:
        ok, detail = rebase_branch_onto_main(branch, repo)
        if not ok:
            print(f"    ❌ Stale-base auto-sync failed: {detail}")
            actions.append(
                {
                    "wo": wo_num,
                    "branch": branch,
                    "status": "skipped-stale-base",
                    "error": detail,
                }
            )
            continue
    else:
        print("    [DRY-RUN] Would rebase onto origin/main.")
        actions.append({"wo": wo_num, "branch": branch, "status": "stale-base-plan"})
        continue
```

Hunk E2 — helper next to the above (executed only under --auto-open):

```python
def rebase_branch_onto_main(branch: str, repo: str = UPSTREAM_REPO) -> tuple[bool, str]:
    """Clean-rebase auto-sync (#485). Force-with-lease keeps the push safe;
    any conflict aborts the rebase fail-closed (branch left untouched)."""
    steps = [
        ["git", "fetch", "origin", "main"],
        ["git", "rebase", "origin/main", branch],
    ]
    for cmd in steps:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)
            return False, (res.stderr or res.stdout).strip()[:400]
    push = subprocess.run(
        ["git", "push", "--force-with-lease", "origin", branch],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if push.returncode != 0:
        return False, (push.stderr or push.stdout).strip()[:400]
    return True, "rebased onto origin/main"
```

## 4. Fix 1 — Claim-hoarding detection (test bullet 3)

`tests/test_ci_guards.py` gains a deterministic detector over claim
events (S0.1 marker plane): an agent with more than one live claim
(ts <= now < expires_at, closed issues excluded) is flagged — enforcing
task #479's single-active-claim quota at the intake layer. Reference:
`bridge_opener_hardening_reference.detect_concurrent_claims`
(deterministic, ascending agents, TTL/closed aware, fail-closed on
malformed events).

## 5. Tier mapping (task #485 contract)

1. Tier 1: python3 scripts/ci/auto_bridge_pr_opener.py --self-test —
   Hunk B/C functions are importable; extend run_self_test with the
   punctuation + evidence-propagation asserts (or keep self-test as-is
   and rely on tests/test_ci_guards.py Hunk F). Offline parity:
   python3 -m unittest test_s08_mistake_immunity (29 tests) and
   bridge_opener_hardening_reference.py --self-test.
2. Tier 2: --auto-open against mock WOs with em-dash typography —
   extract_evidence_sections returns the full verbatim sections, so the
   generated PR body carries why + alternatives_rejected (first-shot
   Knowledge Sharing Guard pass).
3. Tier 3: existing guards (branch-naming, issue-ref, duplicate-pr)
   untouched — all hunks are additive; the only modified line is the
   Hunk A regex.

## 6. Reference files (pure-new-file lane)

- scripts/ci/bridge_opener_hardening_reference.py — REFLECTION_RE,
  extract_evidence_sections, fresh_base_verdict/rebase_plan,
  detect_concurrent_claims, --self-test.
- tests/test_s08_mistake_immunity.py — 29 offline tests: typography
  variants (colon/em/en/hyphen, case, spacing), verbatim section
  transfer incl. heading suffix, section-terminator behavior, verdict
  mapping, deterministic plans, quota detection (expiry, closed,
  ordering), fail-closed inputs.
