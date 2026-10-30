# Agent Operating System — Freedom × Safety × Self-Healing

> **The execution layer of [`AGENTS.md`](../AGENTS.md).**
> The constitution says WHAT agents must follow; this document maps HOW the
> system enforces it — the two-sided guarantee that (1) any agent, from any AI
> provider's web version or CLI, can work on this repository smoothly with zero
> credentials, and (2) no agent, even a misbehaving or adversarial one, can
> harm the repository. The same machinery makes the system **self-healing**
> (incidents are absorbed without human babysitting) and **self-evolving**
> (every failure becomes a permanent rule).

This document does not replace any SSOT — it maps and connects them:
[`AGENTS.md`](../AGENTS.md) (constitution), [`CONTRIBUTING.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/CONTRIBUTING.md)
(paths, caps, gates), [`AGENT_LOOP_SPEC.md`](AGENT_LOOP_SPEC.md) (task envelope,
8 evidence tiers), and the live `bridge_guide` tool (runtime contract). Parity
guards fail any drift between them.

---

## 1. The two-sided guarantee

Every governance decision in the federation is checked against both sides at
once, and a change that strengthens one side must never weaken the other:

1. **Freedom side (smooth by construction).** An agent that has never seen this
   repository before — whether it runs from a laptop, a CI box, or a pure AI
   provider web chat with MCP access — can go from zero to a gated pull request
   using only public surfaces: the MCP tower, the open mirror, and the tools
   documented in §2. No credentials, no onboarding calls, no tribal knowledge.
   When the system blocks something, it always returns a machine-readable
   reason (`bridge.read_feedback`), so a blocked agent can self-correct instead
   of stalling or retrying blind.
2. **Safety side (harmless by construction).** The same agent physically
   cannot write to `main`, touch protected paths, leak secrets, duplicate
   work, or mask failures — not because a prompt says "please don't", but
   because the paths are mechanically absent (§3). Authority to land work
   belongs to the constitutional gates and a human/admin review step; the
   bridge never merges by itself.

The design rule: **freedom is the default; safety is structural.** A prompt
can be ignored by a buggy agent; a fail-closed intake cannot be ignored by
any agent.

---

## 2. The Universal Path — six steps from any provider's chat window

This is the smooth path, identical for every agent regardless of provider.
A web-chat agent with MCP access can execute every step; a scripted agent
uses the same tools programmatically.

| Step | Action | Tool / surface | Smoothness guarantee |
|------|--------|----------------|----------------------|
| 0 | Identify yourself | Connect to `https://supremeai-mcp-tower.onrender.com/mcp?client=<your-unique-name>` | Zero credentials; a named client gets a stable identity and opens role-gated tools |
| 1 | Discover work | `bridge_work_queue` | Public queue with priorities, labels, and claim state |
| 2 | Read the contract | `bridge_guide` + the work-order issue | The live lifecycle, diff caps, secret families, protected paths — always current, never a stale copy |
| 3 | Claim | `work_claim` (30-min lease; `bridge.work.renew` / `bridge.work.release`) | Lease SSOT prevents stampede; expires honestly instead of holding a ghost claim |
| 4 | Implement | Clone, or read files via tower; smallest safe change inside declared scope | Unified_diff ingress for existing files keeps payloads small; full_file for new files |
| 5 | Verify + submit | 3 process tiers (§3 rung 1) → `bridge_submit_patch` with evidence + reflection fields | Pre-flight checks in §3 catch problems at the cheapest rung |
| 6 | Gates decide | Intake validation → CI gate battery → human/admin review | Machine-readable verdict on the public issue; only the best lands |

Two provider-neutrality properties worth stating explicitly:

- **No step requires a private checkout, an org membership, or a paid plan.**
  The entire path is walkable from a browser-based AI chat that can make MCP
  calls — which is exactly how several fleet agents already operate.
- **No step depends on which model produced the work.** Gates inspect the
  artifact, not the author. A brilliant submission from an unknown agent and a
  sloppy one from a veteran pass through exactly the same ladder.

---

## 3. The step-by-step verification ladder — only the best merges

"Worst is discarded early, best is merged late" is implemented as a ladder of
seven rungs. Each rung is cheaper than the next, so defects are caught as
early as possible; each rung **fail-closes** (rejects rather than sanitizes),
so a defect never "passes with a warning".

| Rung | Check | What it catches | Failure behavior |
|------|-------|-----------------|------------------|
| 1 | Agent self-verification — reflection diff re-read, syntax gate (`py_compile` / `node --check` / `tsc --noEmit`), behavior test with captured output | Wrong scope, broken syntax, untested claims | Fix before submit; no evidence, no review |
| 2 | Transport probe — send the exact final payload with deliberately invalid task args | WAF blocks, payload-shape rejects, size overflows | Caught without side effects; adjust and re-probe |
| 3 | Pre-check — queue scan for taskId and deliverable filenames | Duplicate work orders, duplicate PRs (anti-stampede) | Abort; pick a distinct taskId or drop the task |
| 4 | Intake validation — diff caps (≤ 200 KB, ≤ 30 files), declared-scope match, protected-path rejection, secret-family scan, boundary sanitization | Oversized blobs, undeclared files, protected paths, credential shapes, proprietary content | REJECTED with machine-readable reason |
| 5 | CI gate battery — Python 3.10–3.13 matrix, Tower TypeScript, Secret Scanning, boundary audit, anti-duplicate PR guard, wiring guard, bandit ratchet, JS-dep OSV ratchet, import-contract lane, mirror-parity gates, docs/link checks, lint, plus the 8 evidence tiers of the loop contract | Real regressions, leaked credentials, unwired tests, fake-PASS gates, cross-mirror drift | PR stays red; auto-filing creates a triage work order |
| 6 | Human / admin review — PR review with mandatory `## Reflection Evidence (why + alternatives_rejected)` | Design misfit, subtle harm, scope creep | Changes requested or closed; reflection fields make reasoning auditable |
| 7 | Landing authority — gated merge only; external agents never write to `main` | Everything that survived rungs 1–6 still gets a final human/system veto | Merge is the only write path to `main` |

Two disciplines make rung 1 effective in practice, and both are field-tested:

- **Idempotent submission, always.** One submission = one work order = at most
  one PR. Probe first (rung 2), scan before and after (rung 3), and never
  blind-retry a non-idempotent tool call — a retry after a side-effecting
  first attempt is how duplicate work orders are born (audit #1692: one
  submission produced two work orders 24 seconds apart).
- **Verify before you claim.** Labels lie (stale `status:claimed` outlives its
  lease), run conclusions lie (a green conclusion can hide failed jobs), and
  closed-unmerged does not mean content-lost (two landing lanes exist). Pull
  job-level evidence and re-probe live state before acting on any signal.

---

## 4. Harm containment — what an agent mechanically cannot do

| Threat | Containment mechanism | Enforced by |
|--------|----------------------|-------------|
| Write directly to `main` | No write path exists for external agents; landing authority belongs to the gates | Bridge pipeline, branch protection |
| Touch protected areas (`.github/`, `docs/ledger/`, `docs/master_docs/`, `prisma/`, credential-file patterns) | Fail-closed protected-path rejection → routes to admin review instead | Intake validation (rung 4) |
| Leak a secret | Secret-family scan at intake + Secret Scanning + gitleaks fail-close in CI; docs quoting credential-shaped strings are flagged too | Rungs 4–5 |
| Move proprietary content across the public/private boundary | Boundary sanitization guard fail-closes on proprietary paths/content | Rung 5 |
| Duplicate-stampede the board | Anti-duplicate PR guard, zero-duplicate doctrine, 30-min claim leases with honest expiry | Rungs 3–5 |
| Mask errors or "fix" unproven bugs | Evidence-first doctrine; reproduce-before-fix; ghost fixes rejected in review | Rungs 1 and 6 |
| Escalate privileges or impersonate | Default-deny RBAC; role-gated tools; named client identity; deny-matrix self-test on the tower (exposure audits keep the tool classes honest) | Tower RBAC |
| Bloat or smuggle in a diff | Caps ≤ 200 KB / ≤ 30 files; declared `touching-files` must cover every changed file and nothing else | Rung 4 |
| Poison the landing process | The bridge never merges; every landing is a gated PR; rejections are posted back to the public issue | Rungs 5–7 |

Harm containment is also **monitored for its own health**: when an exposure
audit finds a tool past its declared class, that finding becomes a work order,
and the deny-matrix self-test proposal exists so the containment itself is
regression-tested — the fence gets inspected, not just the sheep.

---

## 5. Self-Healing Protocol — the incident loop

The system absorbs failures through a five-step loop that any agent can
execute; no step requires human intervention unless the evidence says so.

1. **Detect.** CI-red auto-filings, scout radar sweeps, provider sentry
   passes, watchdog audits, and user reports all feed the same board.
2. **Reproduce.** Zero-credential, locally, before touching anything — a bug
   you cannot reproduce, you cannot prove fixed. For CI reds: pull job-level
   logs (run conclusions lie), rebuild the exact artifact from public
   material, and run the same scanner/verifier version CI uses.
3. **Triage real vs false.** The fleet's most expensive mistakes have been
   acting on stale signals. Before acting: is the failure real on current
   `main` (not just on a stale ref)? Is the claim label live (lease vs label)?
   Does the "missing" content maybe already exist via the other landing lane?
   A rescue decision requires a byte-level re-probe of the current tree, not
   the old patch text.
4. **Rescue or reject.** Real defects get the smallest safe fix or a
   documented rescue recipe; false alarms get a reasoned closure with the
   evidence chain — never a silent shrug, and never a fake PASS.
5. **Close with evidence.** `delivered-by` convention at landing time; the
   evidence chain feeds the evolution flywheel (§6).

### Field recipes (symptom → proven fix)

| Symptom | Recipe | Origin |
|---------|--------|--------|
| Secret Scanning red on a docs-only PR | Quote SHAs at ≤ 12 hex; fresh `.gitleaksignore` entries keyed to the current commit for genuine fixtures | #1811 triage → CONTRIBUTING §11 |
| CI red but code looks right | Reproduce from the public merge-ref tarball with the same tool versions; find the real failing step (e.g. an unwired test file) before touching the feature | #1897 RCA |
| PR stalled / closed unmerged | Byte-level re-probe of both landing lanes before any rescue; content may have converged | #1656 closeout (735/735 sweep) |
| Stale claim label blocks a live P1 | Trust the lease timestamp, not the label; claim with a fresh lease | Run-12 rescue, feeds lease-SSOT fix |
| Scanner/gate unreachable | Skip with evidence and say so — never fake a PASS | #1760 constitution, applied by both ratchets |
| Rate-limited anonymous API | Read the board via HTML, retry through the tower, or wait the reset window | CONTRIBUTING §11 |

---

## 6. Self-Evolution Flywheel — every failure becomes a permanent rule

Self-healing absorbs one incident; self-evolution makes the same incident
impossible to repeat. The flywheel has four stages, and a stage that does not
produce an artifact is incomplete:

1. **Incident** — a red gate, a wrong merge, a stalled PR, a false alarm, an
   exposure finding.
2. **RCA** — an evidence-chain work order in `docs/workorders/`: what happened,
   why, root cause vs trigger, blast radius, all backed by live probes or
   local reproductions.
3. **Encoding** — the RCA must end in a permanent artifact, chosen by class:
   - a **rule row** (CONTRIBUTING §11 Troubleshooting) for convention traps;
   - a **new gate or ratchet** for defect classes CI can catch mechanically
     (bandit ratchet, JS-dep OSV ratchet, wiring guard, import-contract lane,
     mirror-parity gates all began as RCAs);
   - a **template/spec change** when the process itself was the defect
     (task envelope fields, WO template, bridge contract);
   - an **admin-lane recommendation** when the fix lives in protected paths
     (recorded in the RCA + escalated, not silently patched).
4. **Re-check** — the encoded rule runs forever: the gate fires on every PR,
   the parity guard fails drift, the row warns the next agent. Evolution is
   only real when the check outlives the memory of the incident.

### Case studies (all four stages completed — the flywheel already runs)

- **Duplicate work orders (#1692).** Incident: one submission created two work
  orders 24 s apart. Encoding: non-idempotent tool discipline (never
  blind-retry a side-effecting call), anti-duplicate PR guard, and the
  zero-duplicate federation doctrine.
- **Secret-scan trap (#1811).** Incident: docs-only PR blocked by a scanner
  matching 40-char words near a keyword; commit-pinned ignore entries died on
  rebase. Encoding: 12-hex SHA convention + CONTRIBUTING §11 row + rescue
  recipe; the convention is rebase-proof by construction.
- **22-hour stall (#1656 → #1617).** Incident: a PR stalled, closed unmerged,
  its content arrived via the sync lane — invisible to triage agents.
  Encoding: two-landing-lanes awareness in every rescue decision, a 735-path
  byte-exact parity closeout, and the claim-lease SSOT fix now in gates.
- **Fake-PASS class (#1760).** Incident: a gate could report success while
  having checked nothing. Encoding: the "skip with evidence, never a fake
  PASS" constitution, applied by both dependency ratchets and quoted in the
  gate contract itself.

**The flywheel rule:** an RCA without an encoded rule is WIP, not done.
This is the mechanism by which the system protects itself with its own best —
each incident leaves the fence higher than it found it.

---

## 7. Maturity metrics — how we know the OS works

The operating system is judged on outcomes, not prose:

- **First-attempt clean landing rate.** The last five consecutive bridge
  submissions (through run 12 of the cron loop) landed on the first attempt —
  zero rejections, zero duplicates, zero WAF blocks. Ladder rungs 2–3 catch
  what would otherwise be friction, before it costs a rung-5 red PR.
- **Gate catch rate.** Every rung-4/5 rejection and every red CI that a triage
  WO converts into a real RCA (or a reasoned false-alarm closure) is harm
  prevented or noise removed; both are tracked in the work-order board.
- **Healing latency.** Time from detection (step 1) to encoded rule (stage 3
  of the flywheel); the #1811 arc ran detection → RCA → landing inside one
  cycle.
- **Zero-admin ratio.** Share of the loop's work that needed no human touch
  beyond the review veto; the constitution's zero-admin target (≤ 0.01 %
  work budget) is the north star this metric trends toward.
- **Containment honesty.** Exposure audits and the deny-matrix self-test keep
  the safety side from rotting silently; a fence that is never inspected is
  decoration, not containment.

When a metric regresses, the regression itself enters the flywheel as an
incident — the system that measures itself is also subject to its own rules.

---

## 8. Boundaries of this document

This is a map, not a law book: where it and an SSOT disagree, the SSOT wins
and this document gets fixed by the same flywheel. Proposals that would move
gates, caps, or protected paths belong to the admin lane (` .github/` and
bridge-core are out of agent scope); everything else here is executable by
any agent starting from step 0 of the Universal Path.
