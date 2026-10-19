# IDE Extension Orchestrator — সম্পূর্ণ বাস্তবায়ন পরিকল্পনা (বাংলা)

> **উৎস:** `C:\Users\N\Downloads\SupremeAI-এর agent workfl.md` (ব্যবহারকারীর মূল প্রস্তাব) + `supremeai-open` repo-এর বিদ্যমান skill ক্যাটালগ, manifest schema, progressive loader, এবং AGENTS.md সংবিধান।
> **লক্ষ্য:** ব্যবহারকারীর IDE-এ ইনস্টল করা একাধিক AI extension-কে role-based worker হিসেবে সমন্বয় করার জন্য একটি ছোট, নির্ভরযোগ্য, vendor-agnostic coordination layer তৈরি করা।
> **নীতি:** Law of Minimal Elegance — নতুন বড় agent fleet বানানো নয়; বিদ্যমান capability পুনঃব্যবহার, configurable role, durable state, user control.

---

## ১. মূল প্রস্তাবের মূল্যায়ন (Evaluation of the Source Plan)

### ১.১ যা সঠিক ও শক্তিশালী (Strengths)

1. **Multi-Role Separation** — একটি AI-কে সব করতে না দিয়ে Planner → Coder → Reviewer → Fixer → Verifier-এ ভাগ করা। এটি hallucination ও scope creep কমায়।
2. **"শুধু Skill যথেষ্ট নয়" উপলব্ধি** — Skill শুধু নিয়ম লেখে; আসল control লাগে Adapter Boundary / Host API / Command Execution / MCP Bridge / File Handoff। এটি বাস্তবসম্মত সবচেয়ে গুরুত্বপূর্ণ অন্তর্দৃষ্টি।
3. **Bounded Review Loop** — সরাসরি merge না করে reviewer feedback নিয়ে fix loop, সর্বোচ্চ ১–২ রাউন্ড।
4. **Persistent Task Contract** — `.ide-orchestrator/tasks/<task-id>/`-এ structured JSON + Markdown দিয়ে state সংরক্ষণ।
5. **Discover Before Designing** — extension capability inventory আগে, পরে design। এটি "ghost capability" প্রতিরোধ করে।
6. **Adapter Boundary** — workflow logic-কে extension-specific integration থেকে আলাদা রাখা।
7. **Safety & Workspace Integrity** — sequential write, read-only reviewer, no overwrite, no secret leak, cancel/resume।

### ১.২ যা অসম্পূর্ণ বা ঝুঁকিপূর্ণ (Gaps / Risks)

1. **Extension-specific assumptions** — প্রস্তাবিত mapping (CodeRabbit, Cline, Roo, Ralph Loop, GSD) নির্দিষ্ট vendor-এর উপর নির্ভর করে। এক্সটেনশন বদলালে পুরো plan ভেঙে যায়। → **সমাধান:** capability-based config, vendor name hardcode না করা।
2. **Programmatic control gap** — Cline/Roo-এর AI session headless API-তে চালানো সবসময় সম্ভব নয়। → **সমাধান:** adapter contract-এ `manual` mode + file handoff; honest reporting ("controlled automatically" vs "prompt prepared").
3. **State machine অসম্পূর্ণ** — `queued → planning → planned → implementing → reviewing → fixing → verifying → completed` প্রস্তাব আছে, কিন্তু transition validation, idempotency, resume-after-restart বিস্তারিত নেই।
4. **Adapter contract অসম্পূর্ণ** — operations list আছে কিন্তু input/output schema, timeout, cancellation, partial failure handling নেই।
5. **Evidence contract দুর্বল** — "completion evidence" বলা হয়েছে কিন্তু কী গণ্য হবে (changed files + test output + diff hash) সংজ্ঞায়িত নয়।
6. **Config schema নেই** — `.ide-orchestrator/config.json`-এর exact schema, validation, migration নেই।
7. **Testing scenarios** — list আছে কিন্তু acceptance criteria ও automated test harness নেই।
8. **Repo integration** — এই repo-তে বিদ্যমান skill system (`skills/`, `manifest_schema.py`, `progressive_loader.py`) আছে; plan-এ তাদের সাথে integration উল্লেখ নেই। এই plan-এ সেটা যোগ করা হবে।

### ১.৩ মূল সিদ্ধান্ত (Key Decisions Locked)

- **Vendor-agnostic config** — extension name hardcode নয়; capability registration + role assignment config-এ।
- **Honest automation reporting** — কোন stage automatic, কোনটা manual handoff, স্পষ্ট লেবেল।
- **Smallest reliable integration** — প্রথমে ৩ role (Planner, Coder, Reviewer) + manual handoff; পরে Fixer/Verifier + programmatic adapters।
- **Reuse existing skill infra** — `skills/` registry, enriched contract (permission_level, memory_policy, evidence_requirements, stop_conditions), progressive loader।
- **Storage default** `.ide-orchestrator/` কিন্তু configurable + `.gitignore` support।

---

## ২. লক্ষ্য ও Scope

### ২.১ In Scope (এই plan-এ যা হবে)

- `ide-extension-orchestrator` skill-এর SKILL.md + adapter contract reference + config example + templates + setup/test guide।
- Persistent task contract schema (JSON) + Markdown templates।
- Adapter contract (interface + 3 adapter modes: `programmatic`, `cli`, `manual`).
## ৩. আর্কিটেকচার (Architecture)

### ৩.১ লেয়ার ডায়াগ্রাম

```
┌─────────────────────────────────────────────────────────────┐
│  User Task Input                                            │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Coordinator Skill (ide-extension-orchestrator)             │
│  - role assignment, stage transitions, handoff routing     │
│  - adapter selection, timeout/cancel, evidence validation   │
└──┬──────────┬──────────┬──────────┬──────────┬─────────────┘
   ▼          ▼          ▼          ▼          ▼
Planner   Implementer  Reviewer   Fixer    Verifier
   │          │          │          │          │
   └──────────┴──────────┴──────────┴──────────┘
              │  (shared task contract files)
              ▼
┌─────────────────────────────────────────────────────────────┐
│  Adapters (programmatic | cli | manual)                     │
│  - extension A, B, C (config-registered)                    │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  .ide-orchestrator/  (persistent state + handoff files)     │
└─────────────────────────────────────────────────────────────┘
```

### ৩.২ মূল উপাদান

| উপাদান | দায়িত্ব |
|---|---|
| Coordinator Skill | workflow orchestration, state transitions, handoff routing, evidence gate |
| Config (`config.json`) | extension registration, capability discovery result, role→extension mapping |
| Adapter Layer | extension-specific invocation abstraction (discover/check/submit/read/timeout/cancel) |
| Task Contract | per-task JSON state + Markdown instructions/results |
| Storage | `.ide-orchestrator/` (configurable path, gitignore-aware) |

### ৩.৩ Design Principle (অপরিবর্তনীয়)

- নতুন agent intelligence বানানো নয়; বিদ্যমান extension capability পুনঃব্যবহার।
- Role configurable, vendor name hardcode নয়।
- Orchestration state durable, user in control।
- Honest automation: automatic vs manual handoff স্পষ্ট লেবেল।

---

## ৪. ফাইল স্ট্রাকচার (File Structure)

### ৪.১ Skill ফোল্ডার (repo-তে `skills/ide-extension-orchestrator/`)

```
skills/ide-extension-orchestrator/
├── SKILL.md                          # enriched contract frontmatter + body
├── references/
│   └── adapter-contract.md           # adapter interface + modes
├── assets/
│   ├── config.example.json           # extension registration example
│   └── templates/
│       ├── task.json                 # task state template
│       ├── plan.md                   # planner output template
│       ├── handoff.md                # stage handoff template
│       ├── review.md                 # reviewer output template
│       └── report.md                 # final report template
└── scripts/
    └── validate_task.py              # state transition + schema validator (stdlib)
```

### ৪.২ Runtime Storage (workspace-এ `.ide-orchestrator/`)

```
.ide-orchestrator/
├── config.json                       # extension regs + role mapping (SSOT of capability)
├── .gitignore                        # runtime artifacts excluded (optional)
└── tasks/<task-id>/
    ├── task.json                     # persistent state machine
    ├── plan.md                       # approved plan
    ├── handoffs/
    │   ├── 01-plan.md               # planner output
    │   ├── 02-implement.md          # implementer instruction + result
    │   ├── 03-review.md             # reviewer findings
    │   ├── 04-fix.md                # fixer result
    │   └── 05-verify.md             # verifier result
    ├── review.md                     # consolidated review findings
    ├── diff.patch                    # captured diff (for reviewer)
    └── report.md                     # final report
```

---

## ৫. রোল সংজ্ঞা (Role Definitions)

| Role | দায়িত্ব | ডিফল্ট permission | Read/Write |
|---|---|---|---|
| Planner | task বোঝা, scope/steps/risks/acceptance criteria তৈরি; code modify নয় | read | read-only |
| Implementer | approved plan অনুযায়ী scoped change; changed files + decisions + test evidence রিপোর্ট | write | write |
| Reviewer | diff independent review; severity + file ref + evidence + recommended fix | read | read-only |
| Fixer | confirmed findings fix; unrelated change নয় | write | write |
| Verifier | tests/lint/typecheck/build চালানো; actual result রিপোর্ট, unexecuted pass দাবি নয় | read (exec) | exec |

**নিয়ম:** এক extension একাধিক role পেতে পারে; এক role-এ একাধিক extension assign সম্ভব। Selection: capability + availability + configured preference (vendor name নয়)।

---

## ৬. স্টেট মেশিন (State Machine)

### ৬.১ Lifecycle

```
queued → planning → planned → implementing → reviewing → fixing → verifying → completed
```

Supporting states: `blocked`, `failed`, `cancelled`।

### ৬.২ Transition Rules (validation)

- প্রতিটি transition persist করতে হবে (task.json + timestamp + actor)।
- `planning → planned` শুধু তখনই যখন plan + acceptance criteria বৈধ।
- `implementing → reviewing` শুধু তখনই যখন changed files evidence আছে।
- `reviewing → fixing` শুধু তখনই যখন valid findings আছে; না থাকলে `reviewing → verifying`।
- `fixing → reviewing` loop, সর্বোচ্চ `max_review_rounds` (default 2)।
- Loop cap পৌঁছালে → `blocked` + user decision required।
- `verifying → completed` শুধু তখনই যখন acceptance criteria evaluation + actual check results recorded।
- Extension timeout → `blocked` (not `completed`)।

### ৬.৩ Idempotency

- Task ID = `task-<yyyymmdd>-<slug>-<short-hash>` (unique)।
- Re-run same task ID → resume from last persisted stage (idempotent stage entry)।
- Branch per task id (autonomous-developer convention reuse)।

---

## ৭. টাস্ক কন্ট্র্যাক্ট স্কিমা (Task Contract Schema)

### ৭.১ `task.json`

```json
{
  "task_id": "task-20261020-auth-bug-a1b2",
  "created_at": "2026-10-20T00:00:00Z",
  "updated_at": "2026-10-20T00:00:00Z",
  "user_request": "Fix authentication bug in SupremeAI",
  "stage": "queued",
  "max_review_rounds": 2,
  "review_round": 0,
  "scope": {
    "allowed_paths": ["src/auth/**"],
    "prohibited_paths": [".github/**", "secrets/**"],
    "destructive_ops_allowed": false
  },
  "acceptance_criteria": [],
  "roles": {
    "planner": "ext-gsd",
    "implementer": "ext-cline",
    "reviewer": "ext-coderabbit",
    "fixer": "ext-cline",
    "verifier": "ext-antigravity"
  },
  "evidence": {
    "changed_files": [],
    "diff_hash": null,
    "tests_run": [],
    "tests_passed": null
  },
  "blockers": [],
  "history": [
    { "stage": "queued", "at": "2026-10-20T00:00:00Z", "actor": "coordinator" }
  ],
  "automation_mode": {
    "planner": "programmatic",
    "implementer": "manual",
    "reviewer": "programmatic",
    "fixer": "manual",
    "verifier": "programmatic"
  }
}
```

### ৭.২ Handoff Payload (প্রতিটি stage-এ worker-কে যা যাবে)

- Task ID + original user request
- Current stage + assigned role
- Approved scope + prohibited changes
- Repo/workspace context (relevant files)
- Plan + acceptance criteria
- Previous stage output + evidence
- Required output format
- Completion status, blockers, next stage

### ৭.৩ Evidence Requirements (completion gate)

এক worker "completed" বললেও accept হবে না যদি না থাকে:
- Changed files list (implementer/fixer)
- Diff (or diff hash) (implementer/fixer)
- Test/lint/build actual results (verifier)
- Reviewer findings with severity + file ref (reviewer)
- Plan + acceptance criteria (planner)

---

## ৮. অ্যাডাপ্টার কন্ট্র্যাক্ট (Adapter Contract)

### ৮.১ Interface

```
Adapter:
  discover() -> CapabilityDescriptor   # what extension exposes
  check_availability() -> bool          # installed + responsive
  submit(task_payload) -> SubmissionResult  # invoke or prepare handoff
  read_status(task_id) -> StageStatus   # queued/running/done/failed
  read_output(task_id) -> WorkerOutput  # structured result
  cancel(task_id) -> bool
  on_timeout(task_id) -> TimeoutAction  # block | retry | skip
```

### ৮.২ Adapter Modes

| Mode | ব্যবহার | বাস্তবায়ন |
|---|---|---|
| `programmatic` | extension documented command/API/MCP expose করে | `vscode.commands.executeCommand` / MCP tool call / CLI |
| `cli` | extension CLI/headless interface আছে | subprocess with timeout + stdout capture |
| `manual` | কোনো programmatic interface নেই | exact paste-ready prompt file + result submission back |

### ৮.৩ Honest Reporting (বাধ্যতামূলক)

- `automation_mode` field task.json-এ persist।
- Final report-এ স্পষ্টভাবে লেবেল: "Automatically controlled" vs "Manual handoff prepared"।
- কখনো claim করা যাবে না যে extension automatically controlled হয়েছে যখন শুধু prompt prepared হয়েছে।

### ৮.৪ Capability Discovery (Discover Before Designing)

প্রথম run-এ coordinator করবে:
1. Installed extensions enumerate (Antigravity/VS Code extension host)।
2. প্রতিটির exposed commands/API/MCP/CLI check।
3. `config.json`-এ `discovered_capabilities` লিখবে।
4. User-কে registration confirm করতে বলবে (no auto-assumption)।

**নিষিদ্ধ:** invented command IDs, undocumented internal APIs, private endpoints, session-cookie extraction, brittle UI automation (default solution হিসেবে)।

---

## ৯. কনফিগারেশন স্কিমা (Config Schema)

### ৯.১ `config.json`

```json
{
  "version": "1.0.0",
  "storage_path": ".ide-orchestrator",
  "max_review_rounds": 2,
  "task_timeout_seconds": 300,
  "extensions": {
    "ext-gsd": {
      "name": "Get Shit Done",
      "adapter_mode": "programmatic",
      "capabilities": ["planning", "task-breakdown"],
      "commands": { "plan": "gsd.whatNext" },
      "availability": "unknown"
    }
  },
  "role_assignments": {
    "planner": ["ext-gsd"],
    "implementer": ["ext-cline"],
    "reviewer": ["ext-coderabbit"],
    "fixer": ["ext-cline"],
    "verifier": ["ext-antigravity"]
  },
  "discovered_at": null
}
```

### ৯.২ Validation

- JSON schema validation (stdlib json + custom validator in `scripts/validate_task.py` বা নতুন `validate_config.py`)।
- Unknown adapter_mode → error (not silent fallback)।
- Role assignment-এ extension ID config-এ না থাকলে → error।

---

## ১০. সেফটি ও ওয়ার্কস্পেস ইন্টিগ্রিটি

1. Conflicting write tasks sequentially by default; parallelize only independent + safe।
2. Reviewer read-only wherever possible।
3. Apply change-এর আগে workspace state check (git status clean/dirty)।
4. Unrelated user changes overwrite নয় (diff against baseline)।
5. No credential/API key/private session data in task files/logs।
6. Destructive ops, secret changes, dependency upgrades (material risk), commit/push/release → explicit user authorization।
7. Never silently expand task scope।
8. Cancel, restart recovery, resume interrupted tasks support।
9. Meaningful stage transitions + errors record; excessive data store নয়।
10. Concurrent task writes → file lock (`.ide-orchestrator/.lock`)।

---

## ১১. ইমপ্লিমেন্টেশন ফেজ (Implementation Phases)

### Phase 0 — Discovery & Capability Inventory (Week 1, Day 1-2)
- [ ] Installed extensions enumerate (Antigravity + VS Code)।
- [ ] Exposed commands/API/MCP/CLI per extension document।
- [ ] `config.example.json` populated with discovered capabilities।
- [ ] Gap report: কোন extension programmatic, কোনটা manual only।

### Phase 1 — Skill Scaffold + Manual Handoff (Week 1, Day 3-5)
- [ ] Create `skills/ide-extension-orchestrator/` with SKILL.md (enriched contract)।
- [ ] Adapter contract reference doc।
- [ ] Config example + templates (task.json, plan.md, handoff.md, review.md, report.md)।
- [ ] Manual-handoff flow end-to-end test (Planner→Coder→Reviewer)।
- [ ] Progressive loader discovers new skill (14 indexed)।

### Phase 2 — State Machine + Validator (Week 2, Day 1-3)
- [ ] `scripts/validate_task.py` (stdlib): schema + transition validation।
- [ ] Resume-after-restart logic।
- [ ] Unit tests (unittest, stdlib)।

### Phase 3 — Programmatic Adapters (Week 2, Day 4-7)
- [ ] `programmatic` adapter for at least 1 extension (CodeRabbit review command)।
- [ ] `cli` adapter for at least 1 extension।
- [ ] `manual` adapter (file handoff + result submission)।
- [ ] Timeout/cancel handling।

### Phase 4 — Fixer + Verifier + Report (Week 3)
- [ ] Review-repair loop (bounded, max 2 rounds)।
- [ ] Verifier runs tests/lint/typecheck/build; records actual results।
- [ ] Final report generation (changed files, checks, results, outstanding, criteria met)।

### Phase 5 — Hardening & Docs (Week 3-4)
- [ ] Safety guards (sequential writes, read-only reviewer, no overwrite)।
- [ ] Setup + testing guide।
- [ ] Scenario test matrix (Section ১২) execute + report।

---

## ১২. টেস্ট স্কেনারিও ম্যাট্রিক্স (Test Scenarios)

| # | Scenario | Expected |
|---|---|---|
| 1 | One Planner + one Implementer | plan → implement → evidence recorded |
| 2 | Planner + Implementer + independent Reviewer | review findings with severity + file ref |
| 3 | Reviewer rejects → returns to Implementer | fix loop, round counter increments |
| 4 | One extension unavailable / timeout | `blocked` state, not `completed`; user notified |
| 5 | Extension manual-handoff only | honest "manual" label; paste-ready prompt file |
| 6 | Task interrupted + resumed | resume from last persisted stage |
| 7 | Tests fail during verification | `failed`/`blocked`; actual results recorded, no false pass |
| 8 | User cancels | `cancelled` state; partial work preserved |
| 9 | Requested change would overwrite unrelated edits | blocked before apply; user decision |
| 10 | Review round cap exceeded | `blocked` + user decision required |

**Report:** কোন scenarios actually tested vs design-level checks — final report-এ স্পষ্ট।

---

## ১৩. রিস্ক ও মিটিগেশন (Risks)

| রিস্ক | মিটিগেশন |
|---|---|
| Extension programmatic API নেই | manual adapter + honest labeling |
| Brittle UI automation | avoid as default; only documented interfaces |
| State corruption on crash | atomic write (temp file + rename); resume logic |
| Scope creep | scope lock in task.json; validator rejects out-of-scope |
| False completion claims | evidence gate; verifier actual results only |
| Vendor lock-in | capability-based config; no hardcoded names |
| Secret leak in task files | redaction rule + audit |
| Concurrent task writes | file lock |

---

## ১৪. পরবর্তী পদক্ষেপ (Next Steps — Actionable)

1. **এখনই:** Phase 0 discovery শুরু — installed extensions enumerate + capability inventory।
2. **তারপর:** Phase 1 skill scaffold (SKILL.md + templates) তৈরি; progressive loader test।
3. **তারপর:** Phase 2 validator + tests।
4. **তারপর:** Phase 3 programmatic adapters (1 extension at a time)।
5. **শেষে:** Phase 4-5 hardening + scenario matrix + docs।

### সিদ্ধান্ত প্রয়োজন (Decision Required)

- **Storage location:** default `.ide-orchestrator/` (configurable) — confirm।
- **First programmatic adapter target:** CodeRabbit review command (recommended, কারণ documented command exists)।
- **Manual-handoff UX:** paste-ready prompt file vs clipboard — recommend file (auditable)।

---

## ১৫. এই repo-র সাথে Integration (supremeai-open)

- Skill ফোল্ডার: `skills/ide-extension-orchestrator/` (enriched contract reuse: permission_level, memory_policy, evidence_requirements, stop_conditions)।
- Manifest schema: `skills/registry/manifest_schema.py` — নতুন skill auto-discovered by `ProgressiveLoader`।
- Tests: `skills/tests/` — add `test_ide_extension_orchestrator.py` (stdlib unittest)।
- Progressive loader count: 13 → 14 (incl. new skill)।
- AGENTS.md / satellite governance: skills satellite SSOT; changes via bridge lane (new-files-only) or admin-lane for existing files।
- Naming: `ide-extension-orchestrator` (NAME_RE: `^[a-z0-9][a-z0-9-]*$` ✓)।

---

## ১৬. চূড়ান্ত নীতি (Final Principle)

> **Build the smallest reliable coordination layer that makes the user's existing extensions work together.**
> Do not rebuild each extension's intelligence. Do not create a large fixed agent hierarchy. Reuse existing extension capabilities, make roles configurable, keep orchestration state durable, and keep the user in control.

---

*এই প্ল্যানটি `supremeai-open` repo-এর skill system, manifest schema, progressive loader এবং AGENTS.md সংবিধানের সাথে aligned। বাস্তবায়ন শুরু করতে Phase 0 discovery দিয়ে শুরু করুন।*

