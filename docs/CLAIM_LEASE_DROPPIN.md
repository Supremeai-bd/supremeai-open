# Claim Lease Drop-In — operator hand-off (#375 Phase 2a)

Task ID: `bridge-20261016-claim-lease-dropin-r2` · Agent: `zai-autonomous-contributor`
Provenance: r1 (WO #388, branch `bridge/bridge-20261016-claim-lease-labels-r1`, base `e1c3f86`)
was rejected at intake — both of its target paths do not exist on the private main that
bridge v1 applies against:

```
error: docs/AGENT_PORTAL_SPEC.md: No such file or directory
error: scripts/ci/stale_claim_releaser.py: No such file or directory
```

Fail-closed bridge v1 therefore applied nothing, even though the logic itself was never
invalidated. This r2 carries the SAME state machine in the pure-new-file lane that landed
WO #370 and is now in-gates as #393/#394: everything ships as NEW files, and the wiring
against existing files rides here as byte-exact copy-paste blocks (the WO #376 Appendix A /
#393 §3 pattern).

## What ships in this order (3 NEW paths)

| Path | Kind | Purpose |
| --- | --- | --- |
| `scripts/ci/claim_lease.py` | NEW module | Hermetic claim-lease core: vocabulary, lease clock, evaluator, release plan + comment builder. Zero I/O, zero subprocess, zero environment reads; only stdlib imports. |
| `tests/test_claim_lease.py` | NEW suite | 14 offline test groups (dual-mode: pytest AND plain runner). Imports only the module + stdlib. |
| `docs/CLAIM_LEASE_DROPPIN.md` | NEW doc | This hand-off: contract, wiring diffs, verification, deltas. |

No existing file is touched by the order itself. The operator performs the §3 wiring at
their discretion; until then the module is inert (nothing imports it).

## §1 Contract (the state machine)

Claim SSOT (#375 Phase 2a): **labels + native assignees**.

- A claim exists iff the issue carries a claimed label (`status:claimed`,
  `status:in-progress`) OR has native assignees.
- Lease clock priority:
  1. Latest lease-relevant event (`labeled` with a claimed label, `assigned`) — precise,
     immune to unrelated issue activity.
  2. Issue `updatedAt` fallback — tagged `clock_source: "updatedAt-fallback"`. Honest
     limitation: any activity refreshes it, so it may UNDER-report staleness; it never
     over-releases.
- A claim with no resolvable clock is **never released** (fail-conservative: you cannot
  date a lease, you cannot break it).
- Stage windows: Stage 1 = 10 min (claim → branch), Stage 2 = +30 min (branch → PR,
  i.e. 40 min total).
- Board hygiene exclusions (same as the operator releaser): labels
  `state:seq-hold`, `blocked-by-upstream`, `mirror:private`; any `bridge:`-prefixed
  label; titles starting `audit(` or containing `admin_decision` or `bridge work order`.
- Release plan (pure, ordered): remove claimed labels actually present → add
  `status:unclaimed` (#375 §2 target vocabulary) → clear agent assignees unless
  `--keep-assignees`.
- Legacy comment-regex detection is DEPRECATED: available only via
  `legacy_comments=True` / `--legacy-comments` for the migration window. **Removal
  trigger: #375 Phase 2b** (loop writes claim labels) — delete the flag and
  `CLAIM_PATTERNS` entirely.

## §2 Module API (`scripts/ci/claim_lease.py`)

| Symbol | Kind | Notes |
| --- | --- | --- |
| `CLAIMED_LABELS`, `UNCLAIMED_LABEL`, `EXCLUDED_LABELS` | constants | vocabulary SSOT |
| `STAGE_1_CLAIM_TO_BRANCH_MINUTES`, `STAGE_2_BRANCH_TO_PR_MINUTES` | constants | 10.0 / 30.0 |
| `parse_lease_events(events)` | pure | → `([(dt, kind)], malformed_count)`; malformed skip-AND-count |
| `resolve_lease_clock(issue, events, has_claimed_label, assignees)` | pure | → `(dt, source)`; `(None, None)` = never release |
| `extract_claim_timestamp(issue)`, `is_claim_comment(body)` | pure, legacy | pre-2a semantics preserved |
| `issue_has_remote_branch(num, branch_names)` | pure | boundary-guarded (see §5 deltas) |
| `claimed_candidate_numbers(issues)` | pure | bounds the caller's event fetch |
| `evaluate_graduated_claims(issues, open_pr_refs, remote_branches, ..., now=None, events_by_issue=None, legacy_comments=False)` | pure | the state machine; additive fields `assignees`, `clock_source` |
| `build_release_plan(labels_present, assignees=None, keep_assignees=False)` | pure | ordered op list, executed by caller |
| `build_release_comment(stage, reason, elapsed_min, keep_assignees=False)` | pure | byte-compatible with the historical release comment |

Every function takes its inputs injected; `now` is always a parameter. The module never
calls gh/git and never reads the environment.

## §3 Operator wiring diffs (byte-exact, adapt target as needed)

Anchors below are written against the public observable copy
`scripts/ci/stale_claim_releaser.py` at main (`9fc5d47`, 412 lines). If the private copy
diverged, apply the same three semantic edits at the corresponding sites.

### §3.1 Place the module + import

`scripts/ci/claim_lease.py` sits NEXT to the releaser. In `stale_claim_releaser.py`,
after the existing typing import line (anchor: `from typing import Any, Dict, List, Optional, Set, Tuple`), add:

```python
import claim_lease
```

(While wiring, also extend that typing line with `Sequence` — the pre-existing
`def main(argv: Optional[Sequence[str]] = None)` annotation references an unimported
name; harmless today only because `from __future__ import annotations` makes annotations
lazy.)

### §3.2 Event fetch + SSOT call-site in `main()`

BEFORE (anchor at the original lines ~384-389):

```python
    open_prs = get_open_pr_issue_references(args.repo)
    remote_branches = get_remote_branches(args.repo)
    stale_issues = evaluate_graduated_claims(
        issues,
        open_prs,
        remote_branches,
        claim_to_branch_min=args.claim_to_branch_min,
        branch_to_pr_min=args.branch_to_pr_min
    )
```

AFTER:

```python
    open_prs = get_open_pr_issue_references(args.repo)
    remote_branches = get_remote_branches(args.repo)

    events_by_issue: Dict[int, List[Dict[str, Any]]] = {}
    if not args.legacy_comments and not args.no_fetch_events:
        candidates = claim_lease.claimed_candidate_numbers(issues)
        if candidates:
            print(f"   Fetching lease events for {len(candidates)} claimed candidate(s)...")
            events_by_issue = fetch_lease_events(args.repo, candidates)
            empty = sum(1 for v in events_by_issue.values() if not v)
            if empty:
                print(f"   ⚠️ {empty} candidate(s) returned no usable events — "
                      f"their clocks fall back to updatedAt (tagged in output).")

    stale_issues = claim_lease.evaluate_graduated_claims(
        issues,
        open_prs,
        remote_branches,
        claim_to_branch_min=args.claim_to_branch_min,
        branch_to_pr_min=args.branch_to_pr_min,
        events_by_issue=events_by_issue,
        legacy_comments=args.legacy_comments,
    )
```

The per-issue event fetch (`fetch_lease_events`) stays in the releaser — it is I/O. It
is bounded to claimed-prefiltered candidates only (first page, `per_page=100`) and is
fail-open per issue: a failed fetch yields `[]` and that issue's clock honestly degrades
to the tagged `updatedAt-fallback`.

### §3.3 Release path in `release_issue_claim()`

BEFORE (the whole original body, anchor `def release_issue_claim(repo: str, issue_number: int, stage: int, reason: str, elapsed_min: float) -> bool:`):

```python
    comment = (
        f"⏰ **Graduated Lease Auto-Release (Stage {stage})**\n\n"
        f"- **Trigger:** {reason} (elapsed: {elapsed_min}m)\n"
        f"- **Heartbeat Policy:** Claim-to-branch TTL is 10 min; branch-to-PR TTL is 30 min.\n"
        f"- **Action:** Releasing claim marker back to the public pool.\n\n"
        f"Task is immediately available for `--pick-next` dispatch."
    )
    # Post audit comment
    run_cmd(["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", comment])

    # Remove claimed / in-progress markers
    cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
    for cl in CLAIMED_LABELS:
        cmd.extend(["--remove-label", cl])

    l_code, _, _ = run_cmd(cmd)
    return l_code == 0
```

AFTER (extended signature; callers that pass the new kwargs opt into assignee-aware
release — callers that do not keep the old degradation):

```python
def release_issue_claim(
    repo: str,
    issue_number: int,
    stage: int,
    reason: str,
    elapsed_min: float,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    keep_assignees: bool = False,
) -> bool:
    """Post release comment and execute the label/assignee release plan."""
    comment = claim_lease.build_release_comment(stage, reason, elapsed_min, keep_assignees)
    run_cmd(["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", comment])

    plan = claim_lease.build_release_plan(labels, assignees, keep_assignees)
    remove_labels = [p["label"] for p in plan if p["op"] == "remove_label"]
    add_labels = [p["label"] for p in plan if p["op"] == "add_label"]
    remove_assignees: List[str] = []
    for p in plan:
        if p["op"] == "remove_assignees":
            remove_assignees.extend(p.get("assignees", []))

    ok = True
    if remove_labels or add_labels:
        cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
        for lbl in remove_labels:
            cmd.extend(["--remove-label", lbl])
        for lbl in add_labels:
            cmd.extend(["--add-label", lbl])
        l_code, _, _ = run_cmd(cmd)
        ok = ok and l_code == 0

    if remove_assignees:
        cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
        for login in remove_assignees:
            cmd.extend(["--remove-assignee", login])
        a_code, _, _ = run_cmd(cmd)
        ok = ok and a_code == 0

    return ok
```

In the auto-release loop inside `main()` (anchor
`ok = release_issue_claim(`), pass the plan inputs:

```python
            ok = release_issue_claim(
                args.repo,
                s["number"],
                s["stage"],
                s["reason"],
                s["elapsed_minutes"],
                labels=s["labels"],
                assignees=s.get("assignees") or [],
                keep_assignees=args.keep_assignees,
            )
```

### §3.4 New CLI flags in `main()` argparse block

After the existing `--auto-release` flag line, add:

```python
    parser.add_argument("--legacy-comments", action="store_true",
                        help="DEPRECATED transition mode: detect claims via legacy comment regex "
                             "(#375 Phase 2a default is labels+assignees SSOT). Removal trigger: "
                             "Phase 2b (loop writes claim labels).")
    parser.add_argument("--keep-assignees", action="store_true",
                        help="Do not clear native assignees when releasing a claim")
    parser.add_argument("--no-fetch-events", action="store_true",
                        help="Skip the per-candidate event timeline fetch; lease clock falls back "
                             "to issue updatedAt (coarse, may under-report staleness — tagged in output)")
```

The status-line print (anchor `Claim SSOT:`) may add the same source line the r1 branch
used; cosmetic, optional.

### §3.5 `docs/AGENT_PORTAL_SPEC.md` §3.3 (byte-exact, from r1)

In section 3.3, after the sentence describing the claim marker, add:

```markdown
**Claim SSOT (#375 Phase 2a).** A claim exists iff the issue carries a claimed label
(`status:claimed` / `status:in-progress`) or has native assignees. The lease clock is
the latest lease-relevant issue event (`labeled` with a claimed label, `assigned`);
when events are unavailable it falls back to `updatedAt`, tagged
`updatedAt-fallback` (coarse: never over-releases). A claim with no resolvable clock is
never released. Releases remove claimed labels, add `status:unclaimed`, and clear agent
assignees (`--keep-assignees` opts out). Legacy comment-regex detection survives only
behind `--legacy-comments` and is deleted in #375 Phase 2b.
```

### §3.6 `pipeline.yml` invocation

UNCHANGED. The evaluator keeps its positional signature and all existing record fields;
`assignees` and `clock_source` are additive. Operators who explicitly pass
`--legacy-comments` get the pre-2a behavior for the migration window.

## §4 Verification

- Offline battery: `pytest tests/test_claim_lease.py` OR `python3 tests/test_claim_lease.py`
  — 14 groups, all asserts green in both runners, deterministic (controlled `now`).
  Covers: SSOT invisibility of comment-only claims (T-C, fixtures 1-7), T-A zombie-lease
  (events beat a manipulated fresh `updatedAt`), T-B assignee-only Stage 2, T-B2
  undateable assignee never released, T-F malformed skip-and-count, T-G exclusions,
  legacy parity, T-E release plans (4 shapes), direct clock/prefilter/matcher/formatter
  contracts, byte-identical determinism.
- Post-wiring smoke: `python3 scripts/ci/stale_claim_releaser.py --self-test` then one
  read-only sweep (no `--auto-release`) on a live board; stale records must show
  `clock_source` values (`events` / `updatedAt-fallback` / `legacy-comments`).
- Rollback: delete the two NEW files; revert the §3 edits. No schema, no workflow, no
  config side effects.

## §5 Behavior deltas vs the pre-2a releaser (all tested)

| Delta | Why |
| --- | --- |
| Comment-only claims invisible by default (SSOT) | #375 Phase 2a target state; legacy mode preserves old semantics behind the deprecated flag |
| Events clock beats `updatedAt` | kills the zombie-lease defect (activity refreshes kept leases alive forever) |
| Undateable claims never released | fail-conservative |
| Release adds `status:unclaimed` + clears assignees | #375 §2 vocabulary; `--keep-assignees` opt-out |
| Branch matcher boundary-guarded: issue-12 no longer false-matches an `issue-123` branch | numeric substring collision caused Stage 2 (40m) instead of Stage 1 (10m) for branchless claims — an under-release contract violation; fixed here, delta documented, regression-tested |
| Additive stale-record fields `assignees`, `clock_source` | observability; backward compatible |

## Non-goals

- **#375 Phase 2b** (loop-side claim-label writes, which retire `--legacy-comments`):
  blocked on the `continuous_agent_loop.py` surface — unknowable without private access
  (r1/r2 of WO #379 reached the same conclusion and carried their hunk for an authorized
  operator lane).
- gh/git I/O and comment posting stay in the operator releaser; this order ships logic,
  not credentials.
- No workflow-file edits are included (the `.github/` plane is outside the bridge lane).
