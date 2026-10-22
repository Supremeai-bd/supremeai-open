# S0.2 — Structured PR Evidence Envelope — Full Specification

Task issue: #457 · Seq S0.2 of the Simplification Roadmap · P0-critical
Author: Z.ai Code autonomous contributor (session web-26454b1b, zero-credential bridge lane)
Status: DELIVERED — spec + reference implementation + executable contract tests (prep lane; submit on claim)

---

## 1. Problem — text-scraping guards reject valuable work

PR guards today scrape PR bodies with regex and keyword ladders. Battle
record from the last 24 hours alone:

| Incident | Guard | False failure mode |
|---|---|---|
| WO #435 rejected | claim-guard | issue lookup + label scraping failed on a valid delivery; maintainer rescue needed |
| PR #462 intake | auto_bridge_pr_opener | PR did not open because the literal keyword Reflection: was missing from the body |
| PR #462 CI | Knowledge Sharing Guard | section heading format mismatch stopped an otherwise green delivery |
| PR #462 CI | Boundary Sanitization Guard | a new (legitimate) subtree under scripts/ tripped an allowlist string check |

None of these failures were about the WORK. They were about how prose was
parsed. Every regex ladder has the same three defects: brittle to wording,
silent on partial matches, and impossible to unit-test against future
bodies. Design principle violated: make the correct path the only path —
today the correct path is whatever phrasing the regex author imagined.

## 2. Solution — one envelope, parsed once, asserted by structure

Every bridge-delivered PR carries ONE machine-readable evidence block:

    <!-- pr-evidence-envelope v1 -->
    {
      "schema": "pr-evidence-envelope/1",
      "task_issue_ref": 457,
      "claim_marker_id": "atomic-claim:issue=457,agent=zai,ts=...",
      "reflection_why": "structured assertions replace regex ladders",
      "alternatives_rejected": ["keep regex ladders", "require new CI service"],
      "scope_paths": ["docs/S02_STRUCTURED_EVIDENCE_SPEC.md"],
      "file_digests": {"docs/S02_STRUCTURED_EVIDENCE_SPEC.md": "sha256:..."},
      "rollback_path": "git revert bridge branch commits; additive only",
      "agent_id": "zai-web:web-26454b1b",
      "created_ts": "2026-10-17T03:30:00Z"
    }
    <!-- /pr-evidence-envelope -->

Guards that consume structured fields (claim-guard, Knowledge Sharing,
Boundary, intake dedup) switch from scraping prose to asserting fields:
exact keys, exact types, exact formats. One parser, one schema version,
fail-closed on anything else.

## 3. Normative field contract

| Field | Type | Rule | Guard consumer |
|---|---|---|---|
| schema | string | must equal pr-evidence-envelope/1 | all (version gate) |
| task_issue_ref | integer | positive; issue must exist and be open | claim-guard |
| claim_marker_id | string | verbatim marker id from the task issue's atomic-claim comment | claim-guard (comment plane) |
| reflection_why | string | non-empty, 16..500 chars | Knowledge Sharing |
| alternatives_rejected | string array | 1..5 items, each non-empty | Knowledge Sharing |
| scope_paths | string array | 1..30 items; none may hit protected paths | Boundary |
| file_digests | object | key = scope path, value = sha256-hex (64 chars, optional sha256: prefix) | byte-verify layer |
| rollback_path | string | non-empty | landing/revert automation |
| agent_id | string | non-empty, printable | audit trail |
| created_ts | string | ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ) | audit trail |

Validation is fail-closed: any unknown extra field is IGNORED (forward
compatibility), any missing/malformed known field is a hard error with a
stable code. Unknown fields never break old guards; missing fields always
do — this is the same asymmetry that keeps claim-guard honest.

## 4. Error codes (stable, machine-checkable)

| Code | Meaning |
|---|---|
| E_NO_ENVELOPE | no marker block found in body |
| E_BAD_SCHEMA | schema field missing or wrong version |
| E_BAD_ISSUE_REF | task_issue_ref not a positive integer |
| E_NOT_CLAIMED | referenced issue has no live claim for agent |
| E_CLAIM_MARKER_MISMATCH | claim_marker_id does not match the issue's marker comment |
| E_BAD_DIGEST | file_digests value not sha256-hex |
| E_SCOPE_PROTECTED | scope path hits .github/ docs/ledger/ docs/master_docs/ prisma/ .env |
| E_EMPTY_WHY / E_NO_ALTERNATIVES | reflection fields empty or out of range |
| E_BAD_TIMESTAMP | created_ts not ISO-8601 UTC |

## 5. Guard integration — replace, do not stack

- auto_bridge_pr_opener: scans for the envelope marker (exact string) instead of the Reflection: keyword; if present, the PR opens.
- Knowledge Sharing Guard: satisfied by construction — the reference implementation renders the human-readable section FROM the envelope fields, so prose and structure can never disagree.
- claim-guard: task_issue_ref + claim_marker_id give it two exact strings to assert instead of scraping labels and comments heuristically. Fail-closed semantics unchanged.
- Boundary Sanitization Guard: scope_paths is the checked list; the allowlist assertion becomes a set operation, and the renderer emits the path list so humans see it too.
- landing.yml byte-verify: file_digests allow sha256 verification at merge time — closing the loop the S0.1 delivery already proved manually (3/3 files byte-identical on main).

## 6. Acceptance criteria (machine-checked)

1. Envelope round-trips: build -> parse returns identical fields.
2. Garbage bodies (no marker, truncated JSON, wrong types) parse to None — never raise, never half-validate.
3. All nine error codes are reachable from pure-function tests.
4. render_reflection_section output contains the exact heading the Knowledge Sharing Guard requires: Reflection Evidence (why + alternatives_rejected).
5. Protected-path detection covers all five protected prefixes plus credential-pattern filenames.
6. Digest validation accepts bare hex and sha256:-prefixed hex only.
7. Suite runs offline (unit) and gains a skip-until-landed live layer (contract) exactly like the S0.1 suite.

## 7. Migration path

- S0.2 (this spec): envelope defined, renderer guarantees the Reflection section, guards MAY consume it now.
- S0.4: tower tool consolidation — bridge_submit_patch gains an evidenceEnvelope argument and the tower embeds the envelope into the PR body at creation time; the PR body becomes a projection of structured data, never hand-written prose.
- Removal of the old regex ladders is gated on guards consuming the envelope for one full week without a false reject (the S0.1 week proved the pattern).

## 8. V2 Intelligent Role-Specific Knowledge Envelope

While V1 captures basic PR mechanics, **V2 (`pr-knowledge-envelope/2`)** captures cognitive, architectural knowledge tailored to SupremeAI's 7 canonical agent roles. Upon landing in `main`, `landing.yml` autonomously parses and ingests these entries into Supabase (`knowledge_base`, `learned_facts`) and Qdrant (`supremeai_memory`).

```json
<!-- pr-knowledge-envelope v2 -->
{
  "schema": "pr-knowledge-envelope/2",
  "task_issue_ref": 100,
  "role": "coder" | "auditor" | "ci-fixer" | "planner" | "human-eye" | "third-party" | "ecosystem-scout",
  "knowledge": { ...role-specific fields... }
}
<!-- /pr-knowledge-envelope -->
```

### The 7 Canonical Role Knowledge Contracts:

1. **`coder` (Contributor / Developer)**
   - `fix_mechanism`: Technical explanation of HOW the solution works (code/logic flow, not superficial description).
   - `why_this_way`: Architectural and simplicity justification for choosing this design.
   - `alternatives_rejected`: `[{"method": "...", "why_rejected": "..."}]` (concrete rejected approaches).
   - `pitfalls_to_avoid`: Known edge cases, concurrency gotchas, or regression hazards.

2. **`auditor` (Sentinel / Rules-Breaker)**
   - `audit_methodology`: Exact probing technique used (AST parsing, live MCP calls, grep signatures).
   - `alternative_audit_methods`: Other scanning techniques considered (e.g. static typecheck vs mock execution).
   - `improper_audit_traps`: How NOT to audit this (avoiding aggressive traffic, side-effects, or false positive traps).
   - `prevention_gate`: Automated CI check or contract test deployed to permanently prevent recurrence.

3. **`ci-fixer` (Infrastructure / Workflow)**
   - `root_cause_analysis`: True underlying failure root cause (strictly banning skip-test or `|| true` hacks).
   - `cross_platform_guarantee`: Verification of deterministic execution across Linux, Windows, and macOS.
   - `fast_path_quota_impact`: Preservation of <5s fast paths and free runner minutes.

4. **`planner` (Architect / Spec Designer)**
   - `reused_components`: 80% reuse rule evidence: existing federation modules/abstractions reused.
   - `rejected_speculative_complexity`: Premature scaling or speculative modularity deliberately avoided.
   - `contract_compatibility`: Backward compatibility guarantee and zero-drift verification.

5. **`human-eye` (Supervisory / Governance)**
   - `permanent_system_learning`: Permanent rule, template, or automated check taught to the system.
   - `admin_work_budget_check`: Verification that administrative manual overhead remains <= 0.01%.

6. **`third-party` (MCP Control Tower & Bridge)**
   - `zero_credential_preservation`: Verification that master keys remain vaulted and zero-credential boundary holds.
   - `cold_start_resilience`: Timeout, circuit-breaking, or cold-start retry mechanisms implemented.

7. **`ecosystem-scout` (Platform Sentinel)**
   - `board_parity_finding`: Status of satellite 0-issues / 0-PRs mandate and anchor hub integrity.
   - `drift_detected_and_remedied`: Any specification or implementation drift detected and resolved.

## 9. References

- Task issue #457 · siblings #456 (landed via PR #462), #458, #459
- Ingestion engine: `scripts/ci/ingest_pr_knowledge.py` (V2 role parser + Supabase/Qdrant auto-ingestion)
- Battle record: WO #435 (claim-guard false reject), PR #462 (opener keyword miss + Knowledge Sharing miss + boundary subtree miss)
- Deliverables: `scripts/tower/pr_evidence_envelope.py` (reference impl), `tests/test_s02_evidence_envelope.py` (dual-mode suite), `tests/test_ingest_pr_knowledge.py`

