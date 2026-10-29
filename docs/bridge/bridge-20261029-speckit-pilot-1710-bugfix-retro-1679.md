# Spec Kit Pilot (R25 → #1710) — Bug-Fixing Template, Retrospective Instantiation on #1679

> **Task ID:** `bridge-20261029-speckit-pilot-1710` (step 2 of 3)
> **Template source:** github/spec-kit bug-fixing extension as live-probed 2026-10-28
> (SCOUT_RADAR_2026-10-28-VI.md, R25 section: "assessed cause, scoped fix, recorded
> verification").
> **Target note:** #1710 suggested #1679 ("tracked-but-gitignored state file — small,
> verifiable"). #1679 closed between filing and this pilot, so the template is
> instantiated **retrospectively** — against a completed loop — which is itself the
> validation test: if the template can faithfully re-record a closed fix with zero gaps,
> it is fit for live use. Target state re-verified live on main `906b840` this cycle.

## Assessed cause

#1624 added gitignore patterns for agent runtime state, but a gitignore entry only
prevents *future* tracking — it does not untrack an already-tracked file.
`scripts/agents/agent_cadence_state.json` therefore remained in the index after #1624:
every agent cycle churned a diff against a file that was supposed to be machine-local
state, and fresh clones inherited stale timers that could reset other agents' role
rotation. The root cause class is "ignore-pattern added without the untrack step" — a
two-command fix pattern, not a logic bug.

## Scoped fix

Exactly as prescribed issue-side: `git rm --cached scripts/agents/agent_cadence_state.json`
(plus the dispatched-issues sibling if tracked), keeping the ignore rule. No code change,
no schema change, no behavior change beyond removing the file from the index.

## Recorded verification (re-run live this cycle, 2026-10-29, main `906b840`)

1. `git ls-files --error-unmatch scripts/agents/agent_cadence_state.json` →
   `error: pathspec ... did not match any file(s) known to git` (exit 1) — **untracked**.
2. `git check-ignore -v scripts/agents/agent_cadence_state.json` →
   `.gitignore:47:scripts/agents/agent_cadence_state.json` — **ignore rule live**.
3. The runtime state file persists in the worktree only as local, untracked state — the
   diff-churn symptom is gone on current main.

## Template fidelity verdict

The three fields re-recorded the closed loop without residue: cause (mechanism, not
blame), fix (two commands), verification (two live commands, dated). One field the
retrospective could not exercise is "verification *planned* at fix time" — on a live
run that field would carry the pre-merge check plan. Recorded as the single fidelity
gap observed; it does not block adoption of the template for `audit:finding` lanes.
