# S0.4 — Tower Tool Consolidation 9→5 with sha256 Receipts — Full Specification

Task issue: #459 · Seq S0.4 of the Simplification Roadmap · P2-medium
Author: Z.ai Code autonomous contributor (session web-26454b1b, zero-credential bridge lane)
Status: DELIVERED — spec + mapping registry + no-regression tests (prep lane; fires on claim)

---

## 1. Problem — surface area is cognitive load

The tower catalog grew organically to 9 tools (plus work_claim in
073166b1 and work.next speced in S0.3 — heading for 11). Every agent must
learn the whole matrix; every RBAC rule, rate limit, and doc page
multiplies per tool. The 22-line transit doctrine's principle — single
path per intent — demands fewer, sharper doors.

Current catalog (live @ probe 2026-10-17 03:30Z):
system_summary, system_health, slot_status, agent_heartbeat, agent_status,
bridge_guide, bridge_work_queue, bridge_work_order, bridge_submit_patch
(+ work_claim deployed, + work.next speced).

## 2. Target — five core tools

| # | Tool | Absorbs | Kind |
|---|---|---|---|
| 1 | status(scope?) | system_summary, system_health, slot_status, agent_status, agent_heartbeat | read (+ presence write) |
| 2 | work.claim | (unchanged, S0.1 landed) | write |
| 3 | work.next | (unchanged, S0.3) | read |
| 4 | bridge.submit | bridge_submit_patch | write |
| 5 | bridge.work | bridge_work_queue, bridge_work_order | read |

bridge_guide is NOT absorbed: guides belong in docs (one README section),
not in a tool catalog — surface area cut by deletion, not by hiding.

agent_heartbeat's presence signal is absorbed by work.claim: a claim or
renewal IS the heartbeat (30-min TTL lease already proves liveness).
Agents that only heartbeated now claim-renew instead — one less verb.

## 3. No-regression guarantee (machine-checked, not promised)

Every legacy tool maps to exactly ONE (tool, argument transform) pair.
The mapping registry in scripts/tower/tool_consolidation_reference.py is
the single source of truth; the test suite proves FULL COVERAGE: zero
orphans, zero ambiguity, deterministic transforms. If a future catalog
edit breaks a mapping, the suite fails before agents do.

    system_summary()      -> status(scope="system")
    system_health()       -> status(scope="health")
    slot_status()         -> status(scope="slots")
    agent_status(a?)      -> status(scope="agent", agentId=a?)
    agent_heartbeat(a, s) -> work.claim(renews) OR status(scope="agent") for pure read
    bridge_guide()        -> REMOVED (docs/BRIDGE_GUIDE.md carries it)
    bridge_work_queue()   -> bridge.work(view="queue")
    bridge_work_order(id) -> bridge.work(taskId=id)
    bridge_submit_patch() -> bridge.submit(evidenceEnvelope from S0.2)

## 4. sha256 receipts (the second half of #459's title)

bridge.submit's response gains a machine-readable receipt:

    receipt {
      "commit": "<branch head sha>",
      "files": [ {"path": "...", "bytes": n, "sha256": "<64hex>"} ],
      "tree_sha256": "<64hex over sorted path+digest list>",
      "verified": true
    }

This kills the manual byte-verify boilerplate every agent wrote until now
(doctrine q did it with two layers of scripting). The receipt makes
verification a response field, not a process. Reference implementation:
build_submission_receipt() in the registry file — the TS port returns the
same shape. Fail-closed: a file read failure yields verified=false, never
a partial digest list.

## 5. Migration (three phases, zero downtime)

1. SHADOW: new tools deploy alongside old ones (this is already true for work_claim).
2. ALIAS: old names become thin aliases that log deprecation warnings in responses; agents migrate at their own pace (fleet WOs unaffected — U4).
3. REMOVE: old names deleted only after 7 consecutive days with zero legacy calls (tower audit log as the counter).

RBAC consolidates too: the default-deny mistake that locked work_claim
(WATCH item) gets one policy table for five tools — allowlist per tool,
one place, no per-tool surprises.

## 6. Acceptance criteria

1. Registry maps ALL 9 legacy tools; suite asserts full coverage (no orphan).
2. Ambiguity check: no legacy tool maps to two destinations.
3. Receipt builder: correct sha256 for known inputs, sorted determinism, verified=false on read failure.
4. Heartbeat semantics: claim-renew counts as presence (tested via S0.1 matrix import — SSOT).
5. bridge_guide removal is a documented decision, not an oversight (registry entry kind="REMOVED").
6. Suite runs offline (unit) + skip-until-landed live layer (S0.x pattern).

## 7. References

- Task issue #459 · siblings #456 (landed), #457 (WO #464), #458 (WO #465)
- Catalog probe record: 2026-10-17 03:30Z (9 tools) + work_claim RBAC finding (WATCH)
- Siblings' SSOT chain: docs/S01_ATOMIC_CLAIM_SPEC.md (matrix), docs/S02 (envelope), docs/S03 (queue)
- Deliverables: scripts/tower/tool_consolidation_reference.py, tests/test_s04_tool_consolidation.py
