<!--
SupremeAI Open — Pull Request template (#392).

The "## Reflection Evidence (why + alternatives_rejected)" section is
constitutionally REQUIRED — the knowledge-sharing-guard workflow fails closed
without it. The linked issue must also carry an ACTIVE claim (status:claimed /
status:in-progress label, or an atomic-claim marker comment) before this PR
exists — the claim-guard workflow fails closed otherwise (AGENTS.md Step 4:
no claim, no work).

Admin escape hatch: the 'guard-exempt' label bypasses both guards.
-->

## Summary
<!-- What does this PR change, and why? One or two sentences. -->

## Linked Issue / Claim
<!-- e.g. "Closes #123" — the issue must be claimed BEFORE this PR exists.
     Claim planes accepted by claim-guard: status:claimed / status:in-progress
     label, OR an atomic-claim marker comment posted by the agent loop. -->

## Type of Change
- [ ] `feat` / `fix` / `docs` — Open contributor change

## Reflection Evidence (why + alternatives_rejected)
- **why:** <replace: one-paragraph rationale for the chosen approach>
- **alternatives_rejected:**
  - <replace: alternative approach 1, rejected because ...>
  - <replace: alternative approach 2, rejected because ...>

## Dynamic Test Evidence
<!-- 3-tier verification contract — SSOT: docs/AGENT_LOOP_SPEC.md §4 -->
- [ ] Reflection check (why + alternatives_rejected above are real, not placeholders)
- [ ] Boot smoke test
- [ ] Test suite

## Rollback Path
- [ ] `git revert`-safe (no private state dependencies)
