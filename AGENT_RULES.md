# SupremeAI — AGENT_RULES.md (Single Source of Truth)

> **Zero-Admin Target:** Work budget ≤ 0.01% · **Continuous Loop:** `python scripts/agents/continuous_agent_loop.py --loop`  
> **Rule Contract:** The loop grants permission (U10). Strict adherence to 4 Invariant Pillars below.

---

## 1. The 4 Universal Invariant Pillars

| Pillar | Invariants & Rules | Hard Machine Contract |
|---|---|---|
| **1. Ground & Space (Scope & Domain)** | **U1 Scope · U11 Mirror Parity · U12 Satellite-First · U13 Domain Mirror** | Work strictly inside assigned issue. Zero root-level shadowing (`src/*`, `service/*`, `packages/*` are banned). Satellite code lives strictly in `studio/*`, `gateway/*`, `core/*`, `browser/*`, `vscode/*`. Must pass `boundary_sanitization_guard.py`. Contract surfaces (`api-schemas/`, `examples/gateway_client.py`) require byte-level parity. |
| **2. Board SSOT & Freshness** | **U2 Truth & Evidence · U3 Live Validity · U4 8 Anchor Hubs · U5 Dual-Rebase** | Rebase `origin/main` at work-start AND pre-push (0 behind). Strictly 8 root Anchor Hubs (#749–#762); all work attaches as Sub-Issues. No claim (`work_claim` tool or `<!-- atomic-claim -->`) → No branch. Re-check board freshness (#4177) before declaring done. Verify issues on live `main` before modifying files. |
| **3. Chief Architect Judgment** | **U15 First-Principles · P0 Minimal Elegance · P1 Simple · P2 Complexity Earning · P3 Superior Replacement** | **Value Triad:** Must tangibly benefit Machine (autonomy), Admin (≤0.01%), or User. **Open Grid:** Modular flat metaphor; zero rigid walls. **Superior Replacement:** Discard broken legacy code/tests rather than hacking new code to appease past errors. **80% Reuse:** 1-line truth over over-engineering. |
| **4. Zero-Fail Landing** | **U6 Hard Gates · U7 Verification · U8 Decision Ledger · U9 Sweep · U14 PR Contract · P9 Performance** | 3-Tier Verify (Reflection → Smoke → Tests). Public funnel FCP < 1.0s (no auth blockers on `/`; heavy modules code-split via `React.lazy`). Ban symptom swallowing/ghost fixes (P6). PRs must strictly follow the canonical blueprint below. |

---

## 2. Role Specialization Contracts
- **📐 Planner / Architect:** Roadmaps, API contracts (`api-schemas/`), governance. 80% reuse, ban speculative micro-services and premature scaling (P1/P2).
- **💻 Coder / Contributor:** Target repo implementations & tests (≤30 files, ≤200 KB). Solve root cause (P6), eliminate defect classes, verify schema via `supabase.schema_inspect`.
- **🛠️ CI Fixer:** Pipelines (`.github/workflows/`) & CI scripts (`scripts/ci/`). Ban `--skip-tests` or `|| true`. Windows/Linux/macOS cross-platform invariant. Link to #761 sub-issues or use `guard-exempt` (Rule #392).
- **🔍 Auditor / Sentinel:** Live proof over stale cache. Propose automated CI gates to prevent recurrence permanently. Single ticket updates over duplicate spam.
- **👁️ Human Eye (Admin):** Zero-Admin Target (≤0.01% work budget). Intervene only for hard vault/security boundaries; codify permanent rules.
- **🌐 3rd Party / MCP Platform:** Zero-credential tools via MCP Control Tower (`supremeai-control-tower`). Cold-start resilience for sleeping backend instances.

---

## 3. Canonical PR Blueprint (U14 SSOT)
Every PR opened by agents must strictly follow this exact body structure:
```markdown
### Summary
Brief 1-2 sentence description of what this PR changes and the exact problem it solves.

### Linked Issue / Claim
Closes #<ISSUE_NUMBER>
<!-- atomic-claim: issue #<ISSUE_NUMBER> -->

### Key Changes
- `<domain>/path/to/file.ext`: Concrete architectural or functional change.

## Reflection Evidence (why + alternatives_rejected)
- **why:** Technical rationale explaining why this approach was selected.
- **alternatives_rejected:**
  - *Alternative Approach 1:* Rejected because <technical drawback>.
  - *Alternative Approach 2:* Rejected because <complexity/regression issue>.

### Dynamic Verification Evidence
- [x] Local Guard / Smoke Test Output: `python scripts/ci/boundary_sanitization_guard.py --files <paths>` -> PASS
- [x] Unit/Contract Tests passed with output proof: <test name and result summary>
- [x] Pre-Push Rebase: 0 commits behind origin/main

### Rollback Path
- [x] `git revert`-safe (no cross-satellite private state dependency)
```

---

## 4. Machine Enforcement
- **Master Health & Preflight SSOT:** `python scripts/ops/master_health_check.py --full`
- **Federation Anchors:** `python scripts/ci/federation_anchors.py --self-test` (and `--verify-live`) — strictly 8 persistent root hubs (#749–#762)
- **Boundary Sanitization:** `python scripts/ci/boundary_sanitization_guard.py --self-test` (and `--files <paths>`) — approved mirror surfaces & proprietary isolation (#107, #508)
- **Frontend Performance:** `python scripts/ci/frontend_performance_guard.py --self-test` (and `--check studio/src/App.tsx`)
- **Agent Loop SSOT:** `python scripts/agents/continuous_agent_loop.py --loop` — autonomous continuous execution
