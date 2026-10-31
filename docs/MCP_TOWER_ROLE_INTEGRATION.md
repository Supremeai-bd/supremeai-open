# MCP Tower integration contract for the four role skills

## Status

This is an integration design, not a deployed change. At review time the SupremeAI MCP Tower exposed no skill-registration or MCP prompt-management tool in the available catalog. The current connector could read Tower/repository status and use the bridge submission API; that API creates a public work artifact. No code, issue, PR, or Tower configuration was changed by this package.

The public SupremeAI README describes `supremeai-open` as the public agent front door, with `scripts/agents/continuous_agent_loop.py` and internal engines/schedulers/worker daemons in the core satellite. The internal runtime repository was not available to inspect, so the correct implementation target must be confirmed before coding. The MCP control plane also has separate source/licensing boundaries; do not assume that every path hosted in the public mirror is eligible for an external patch.

## Proposed architecture

**Keep three responsibilities separate:**

1. **Continuous loop = task/role authority.** It selects solver or one scheduled role based on the current board and event/condition policy, applies the P0 gate, and constructs one canonical task envelope. Skills do not start agents, claim work, or set cadence.
2. **Role skill = task procedure.** Store each role's reviewed instruction file in the approved repository/runtime. At dispatch, load only the skill whose key exactly matches the selected role and include its immutable version/hash in the task envelope or run record. A missing, invalid, or untrusted skill should fail closed or emit an explicit “skill unavailable” status; never silently substitute another role's prompt.
3. **MCP Tower = capability enforcement.** Bind each runner/client identity to least-privilege tools in Tower policy. A prompt can request an action but cannot authorize it. Keep issue creation, repository writes, adversarial tests, dynamic failover, deployment, secrets, and other mutations restricted by server-side RBAC and the current bridge/runbook policy.

A plausible layout is `scripts/agents/skills/<role>/SKILL.md` in the approved loop repo, but the project owner must decide whether these are public transit artifacts or belong in the private engine repo. Do not store a second divergent copy without a parity mechanism.

## Binding requirements

- Dispatch must be loop-owned: no role can self-invoke, bypass the solver queue, or race an assigned solver.
- Preserve event-driven episode rotation as specified by current `docs/AGENT_LOOP_SPEC.md` §4c; do not implement 4/6/8/12-hour timers merely because the JSON has old-looking fields. First resolve and test the cadence-config/spec drift.
- Preserve P0 drainage, atomic unique issue claims, anti-duplicate checks, per-role single active run, and the external provider/API rate limits.
- Put only role-specific guidance in the skill. Keep universal invariants in the canonical shared policy to avoid copy drift.
- Enforce least privilege server-side: Scout may read/search and file an approved evidence-backed issue; Human Eye may browser/screenshot and file an issue but not edit UI; Rules Breaker may run bounded authorized tests and only explicitly scoped test-only changes; Platform Guardian is read-only by default and may use only an explicitly allowlisted, bounded temporary failover control.
- Do not expose secrets, customer data, private security findings, or proprietary internal policy in public prompt files or run logs.
- Record role ID, selected skill version/hash, envelope/issue ID, scope/ref, tool-policy version, evidence links, stop reason, run outcome, and reviewer/issue feedback. Redact secrets and personal data.
- Feed resolved/rejected outcome labels into the project's approved knowledge store to calibrate evidence thresholds and reduce false positives. Never let an agent silently rewrite its own skill, authority, cadence, or security guard.

## Acceptance tests for a real implementation

1. **Role binding:** each of the four dispatched role identifiers resolves to exactly one expected skill hash; unknown role, missing file, invalid frontmatter, or hash mismatch fails closed with a clear status.
2. **No cross-role leakage:** a Human Eye dispatch cannot load Rules Breaker or Solver instructions; verify using a deterministic unit test.
3. **Permissions are structural:** mock/real Tower policy denies forbidden operations even when a prompt asks for them. Test, at minimum, Human Eye source edit, Scout repo write, Rules Breaker production mutation, and Platform Guardian durable config change.
4. **Allowed narrow paths:** test that the explicitly configured issue-create path is available to audit roles; bounded `tests/adversarial/` writes require scoped authorization; dynamic failover requires a configured tool, threshold, healthy alternate, expiry, audit log, and rollback.
5. **Dispatch invariants:** solver has priority; P0 drainage holds routine roles; one scheduled role runs per idle cycle; rotation state follows current episode semantics; claims and submissions are idempotent; duplicate dispatch is demoted without clock-based starvation.
6. **Prompt-evidence contract:** each role prompt demands evidence, uncertainty, duplicate checks, and an honest completion state; empty/no-finding runs can succeed without fabricated issues.
7. **Learning guard:** run outcome feedback may update the approved knowledge record, but cannot mutate skill files, role permissions, scheduling logic, or canonical policy without a reviewed code/administrative path.
8. **Parity and rollback:** if loop behavior changes, update the authoritative spec and required public/private parity contract; include tests and a `git revert`-safe rollback.

## Required workflow before deployment

Confirm the owning repository and permitted paths, open/identify a specific work order, claim it through the Tower when required, implement only within declared scope, run the loop's complete verification suite, submit through `bridge_submit_patch`/`bridge_submit`, and let CI plus human/admin review decide. Do not edit `main`, directly push to a satellite, or treat these local files as active Tower configuration.
