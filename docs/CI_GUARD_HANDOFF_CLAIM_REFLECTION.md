# CI Guard Handoff — Claim Gate & Knowledge Sharing (#392)

Issue: #392 (`fix(ci): enforce mandatory Claim Gate & Knowledge Sharing Guard in pipeline.yml`, P1-high, repo:open) · Delivery lane: **public new-file bridge lane** — every deliverable the issue names lives on a protected or pre-existing path (`.github/workflows/pipeline.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, `scripts/ci/auto_bridge_pr_opener.py`, `scripts/agents/continuous_agent_loop.py`), and the bridge lane constitutionally refuses writes to protected paths (doctrine proven in the #374/#376 round). This document therefore carries **all five deliverables as byte-exact, already-tested artifacts**; the operator applies them verbatim (one `git apply` per appendix + one file drop), or the maintainers cherry-pick the same hunks.

**Fidelity contract:** each appendix below is byte-identical to the artifact that passed the verification battery (§5). The battery extracts every appendix back out of this document and `cmp`s it against the tested artifact — a doc edit that breaks byte-parity fails the gate.

## 1. Deliverable → Appendix map

| #392 deliverable | Target path | Lane status | Appendix |
|---|---|---|---|
| 1. `claim-guard` job | `.github/workflows/pipeline.yml` | protected | **A** (byte-exact job YAML; insert after `issue-reference-guard`, before `duplicate-pr-guard`) |
| 2. `knowledge-sharing-guard` job | `.github/workflows/pipeline.yml` | protected | **B** (byte-exact job YAML; insert directly after Appendix A) |
| 3. Loop claim comment + reflection PR body | `scripts/agents/continuous_agent_loop.py` | existing file (bridge apply = death; doctrine #373) | **D** (unified diff vs `main` @ e1c3f86) |
| 4. Opener claim + reflection gate | `scripts/ci/auto_bridge_pr_opener.py` | existing file | **E** (unified diff vs `main` @ e1c3f86) |
| 5. Canonical PR template | `.github/PULL_REQUEST_TEMPLATE.md` | protected (new file) | **C** (complete file content; drop as-is) |

## 2. Design contracts honored

- **Two claim planes, one registry:** the guard accepts `status:claimed` / `status:in-progress` labels — the exact `CLAIMED_LABELS` registry of `scripts/ci/stale_claim_releaser.py` — or the structured `<!-- atomic-claim -->` comment. No third heuristic; lease expiry stays owned by the releaser.
- **AGENTS.md Step 4 ordering:** loop Step 4 posts BOTH claim signals before any PR exists; AGENTS.md line 66 already declares "The claim comment on the issue is the evidence the gate checks — it must exist before CI runs." The gate makes that sentence executable.
- **Fail-closed everywhere:** gh lookup failure, unparseable JSON, empty PR body, missing section, unfilled placeholder — every degenerate path exits 1 with the exact `::error::` strings mandated by the issue.
- **House guard style:** zero-checkout, event-context env only, `timeout-minutes: 3`, `guard-exempt` escape hatch, bot-branch bypass (`dependabot|github-actions|copilot|all-contributors|gh-readonly`) copied from `branch-naming-guard` so our own automation never breaks.
- **Extraction ladder SSOT:** `claim-guard` reuses the `duplicate-pr-guard` extraction ladder (closing keywords → branch `issue-N` tokens → generic `#N` fallback) so both guards see the same target-issue set.
- **jq semantics:** `any(.labels[]?; …)` / `any(.comments[]?; (.body // "") | contains(…))` — tolerant of absent arrays, exact-token label match (no substring collisions), marker containment for the comment plane.
- **Reflection without fabrication:** `build_pr_body(reflection=None)` renders bracket placeholders (which the guard REJECTS — fail-closed, forces real capture); `--auto-pr` injects the loop's real rationale (task payload `why`/`alternatives_rejected` when supplied, else an honest derivation from the task contract). Empty alternatives render an honest no-competing-approach line, never a placeholder.
- **Opener gate placement:** after the branch-exists and duplicate-PR skips, before `gh pr create` — the cheapest possible ordering (no API call for WOs that would be skipped anyway). The gate checks the TASK issue (`extract_task_issue_reference`), not the WO number: WOs carry `bridge:queued`, the task issue carries the claim.

## 3. Integration (operator, ~5 minutes)

1. Appendix A + B: paste both job blocks into `.github/workflows/pipeline.yml` between `issue-reference-guard` and `duplicate-pr-guard` (same zero-checkout guard section). No `permissions:` change needed beyond the jobs' own `issues: read` (already inside Appendix A).
2. Appendix C: write to `.github/PULL_REQUEST_TEMPLATE.md` (new file, byte-exact).
3. Appendix D: `git apply loop_reflection_claim.patch` — clean against `e1c3f86` (verified forward + reverse roundtrip).
4. Appendix E: `git apply opener_claim_gate.patch` — same verification.
5. Consequence note: after Appendix E lands, Bridge Work Orders whose task issue carries no active claim are skipped by the opener (status `skipped-no-claim`) — this is the intended no-claim-no-work enforcement, and it is the WO submitter's duty to claim (or the loop's Step 4 does it automatically per Appendix D).

## 4. Acceptance criteria coverage (issue §Acceptance Criteria)

- [x] PR on unclaimed issue blocked → Appendix A fail path (`exit 1` + exact `::error::`).
- [x] PR without Reflection Evidence blocked → Appendix B fail paths (missing section / empty why / placeholder alternatives).
- [x] Claimed + documented PR passes both guards → battery positive fixtures.
- [x] `guard-exempt` bypasses both → first check in both run blocks.
- [x] `.github/PULL_REQUEST_TEMPLATE.md` exists with the reflection template → Appendix C.
- [x] `continuous_agent_loop.py` auto-injects reflection → Appendix D (`step_7_record` derivation + `build_pr_body` section).
- [x] No regression to existing guards → appendices are purely additive job blocks; battery asserts insertion anchors and that existing job keys are untouched.

## 5. Verification battery (executed, not asserted)

- Appendix byte-parity: extract-from-doc → `cmp` vs tested artifacts (5/5).
- YAML parse + structure: job keys, `pull_request` filter, `timeout-minutes: 3`, zero-checkout (no `actions/checkout` step), `guard-exempt` first, bot bypass present, exact `::error::` strings from the issue text.
- Guard functional execution: the REAL run blocks (after mechanical `${ … }` substitution — exactly what Actions does) executed under `bash` with a stubbed `gh` emitting fixture JSON; 16 scenario assertions (claim: label-pass, comment-pass, no-claim fail with exact message, lookup-failure fail-closed, guard-exempt, bot-pass, no-ref fail; reflection: pass, missing-section fail, empty-why fail, placeholder-why fail, inline-alternatives pass, empty-alternatives fail, placeholder-alternatives fail, guard-exempt pass, bot-pass).
- Patch fidelity: `git apply --check` clean on pristine `e1c3f86` files; forward-apply → `py_compile` → behavior tests (4 reflection renderings, 3 reflection-gate fixtures, fail-closed claim) → reverse-apply → byte-identical restore.
- WO self-compliance: this WO's own body carries the `Reflection:` evidence line its Appendix E gate requires (the guard dogfoods itself).

## Appendix A — claim-guard job (byte-exact, tested artifact)

<!-- APPENDIX-A-START -->
```yaml
  claim-guard:
    name: "🔒 Claim Gate Guard (#392)"
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    permissions:
      issues: read
    steps:
      - name: Verify the referenced issue carries an active claim (event-context only, no checkout)
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_LABELS: ${{ join(github.event.pull_request.labels.*.name, ' ') }}
          HEAD_REF: ${{ github.event.pull_request.head.ref }}
        run: |
          # অ্যাডমিন escape hatch — বিরল অপারেশনাল পরিবর্তনের জন্য (house style, #63)
          if [[ "$PR_LABELS" == *"guard-exempt"* ]]; then
            echo "✅ 'guard-exempt' label present — guard skipped."; exit 0
          fi
          # বট-জেনারেটেড PR কখনো issue claim করে না — নিজেদের automation ভাঙবে না
          if [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot|all-contributors|gh-readonly)/ ]] \
             || [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot)\[?[a-z_]* ]]; then
            echo "✅ Automated/bot branch — allowed."; exit 0
          fi
          # Target-issue extraction ladder — duplicate-pr-guard এর সাথে একই SSOT অর্ডার:
          #   (1) explicit closing keywords (Closes/Fixes/Resolves #N)
          #   (2) branch tokens (issue-N / issueN)
          #   (3) fallback: generic #N references in title/body
          TARGET_ISSUES=$(echo "$PR_TITLE $PR_BODY" | grep -ioE '(closes|fixes|resolves) #[0-9]+' | grep -oE '#[0-9]+' || true)
          BRANCH_ISSUES=$(echo "$HEAD_REF" | grep -oE 'issue-?[0-9]+' | grep -oE '[0-9]+' | sed 's/^/#/' || true)
          ISSUES=$(printf "%s\n%s" "$TARGET_ISSUES" "$BRANCH_ISSUES" | grep -E '^#[0-9]+' | sort -u || true)
          if [ -z "$ISSUES" ]; then
            ISSUES=$(echo "$PR_TITLE $PR_BODY" | grep -oE '#[0-9]+' | sort -u || true)
          fi
          if [ -z "$ISSUES" ]; then
            echo "::error::PR opened without a prior claim on Issue #<num>. Per AGENTS.md Step 4 (No claim, no work), claim the issue before creating a branch or PR."
            echo "(No issue reference found in title/body/branch — issue-reference-guard flags this separately; the claim plane cannot be verified, fail-closed.)"
            exit 1
          fi
          for iss in $ISSUES; do
            iss_num="${iss#"#"}"
            CLAIM_JSON=$(gh issue view "$iss_num" --repo "${{ github.repository }}" --json labels,comments 2>/dev/null || echo "")
            if [ -z "$CLAIM_JSON" ]; then
              echo "::error::PR opened without a prior claim on Issue #$iss_num. Per AGENTS.md Step 4 (No claim, no work), claim the issue before creating a branch or PR."
              echo "(Issue lookup failed via gh — fail-closed.)"
              exit 1
            fi
            # Label plane — stale_claim_releaser.py CLAIMED_LABELS registry-এর সাথে অপরিবর্তিত
            if echo "$CLAIM_JSON" | jq -e 'any(.labels[]?; .name == "status:claimed" or .name == "status:in-progress")' >/dev/null 2>&1; then
              echo "✅ Issue #$iss_num carries an active claim label."
              exit 0
            fi
            # Comment plane — <!-- atomic-claim --> structured comment (loop Step 4 পোস্ট করে)
            if echo "$CLAIM_JSON" | jq -e 'any(.comments[]?; (.body // "") | contains("<!-- atomic-claim -->"))' >/dev/null 2>&1; then
              echo "✅ Issue #$iss_num carries an <!-- atomic-claim --> comment."
              exit 0
            fi
            echo "::error::PR opened without a prior claim on Issue #$iss_num. Per AGENTS.md Step 4 (No claim, no work), claim the issue before creating a branch or PR."
            exit 1
          done
```

<!-- APPENDIX-A-END -->

## Appendix B — knowledge-sharing-guard job (byte-exact, tested artifact)

<!-- APPENDIX-B-START -->
```yaml
  knowledge-sharing-guard:
    name: "🧠 Knowledge Sharing Guard (#392)"
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - name: Verify PR body carries Reflection Evidence (event-context only, no checkout)
        env:
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_LABELS: ${{ join(github.event.pull_request.labels.*.name, ' ') }}
          HEAD_REF: ${{ github.event.pull_request.head.ref }}
        run: |
          # অ্যাডমিন escape hatch
          if [[ "$PR_LABELS" == *"guard-exempt"* ]]; then
            echo "✅ 'guard-exempt' label present — guard skipped."; exit 0
          fi
          # বট-জেনারেটেড PR body-তে reflection থাকে না — সেগুলো পাস করানো যুক্তিসঙ্গত নয়
          if [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot|all-contributors|gh-readonly)/ ]] \
             || [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot)\[?[a-z_]* ]]; then
            echo "✅ Automated/bot branch — allowed."; exit 0
          fi
          # হেডার: canonical টেমপ্লেট সেকশন (PULL_REQUEST_TEMPLATE.md-এর সাথে হুবহু)
          if ! printf '%s\n' "$PR_BODY" | grep -qE '^## Reflection Evidence'; then
            echo "::error::PR body missing required '## Reflection Evidence (why + alternatives_rejected)'. AGENTS.md mandates knowledge capture on every contribution."
            echo "(Expected: a '## Reflection Evidence (why + alternatives_rejected)' section containing filled '- **why:**' and '- **alternatives_rejected:**' entries.)"
            exit 1
          fi
          # why: অবশ্যই non-empty এবং raw placeholder নয়
          WHY=$(printf '%s\n' "$PR_BODY" | grep -m1 -E '^[[:space:]]*-[[:space:]]+\*\*why:\*\*' | sed -E 's/.*\*\*why:\*\*[[:space:]]*//' | xargs || true)
          if [ -z "$WHY" ] || printf '%s' "$WHY" | grep -qE '^<.*>$'; then
            echo "::error::PR body missing required '## Reflection Evidence (why + alternatives_rejected)'. AGENTS.md mandates knowledge capture on every contribution."
            echo "('- **why:**' is empty or an unfilled placeholder — document the actual rationale.)"
            exit 1
          fi
          # alternatives_rejected: same-line content অথবা nested bullets — placeholder নয়
          ALT_INLINE=$(printf '%s\n' "$PR_BODY" | grep -m1 -E '^[[:space:]]*-[[:space:]]+\*\*alternatives_rejected:\*\*.*[^[:space:]*]' | sed -E 's/.*\*\*alternatives_rejected:\*\*[[:space:]]*//' | xargs || true)
          ALT_NESTED=$(printf '%s\n' "$PR_BODY" | sed -n '/\*\*alternatives_rejected:\*\*/,$p' | sed -n '2,$p' | grep -m1 -E '^[[:space:]]+-[[:space:]]+[^[:space:]]' | sed -E 's/^[[:space:]]+-[[:space:]]+//' | xargs || true)
          if { [ -z "$ALT_INLINE" ] || printf '%s' "$ALT_INLINE" | grep -qE '^<.*>$'; } \
             && { [ -z "$ALT_NESTED" ] || printf '%s' "$ALT_NESTED" | grep -qE '^<.*>$'; }; then
            echo "::error::PR body missing required '## Reflection Evidence (why + alternatives_rejected)'. AGENTS.md mandates knowledge capture on every contribution."
            echo "('- **alternatives_rejected:**' is empty or an unfilled placeholder — record at least one discarded alternative with its reason.)"
            exit 1
          fi
          echo "✅ Reflection Evidence present (why + alternatives_rejected documented)."
```

<!-- APPENDIX-B-END -->

## Appendix C — `.github/PULL_REQUEST_TEMPLATE.md` (byte-exact, complete file)

<!-- APPENDIX-C-START -->
```markdown
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
```

<!-- APPENDIX-C-END -->

## Appendix D — unified diff for `scripts/agents/continuous_agent_loop.py` (byte-exact, applies to main @ e1c3f86)

<!-- APPENDIX-D-START -->
```diff
diff --git a/scripts/agents/continuous_agent_loop.py b/scripts/agents/continuous_agent_loop.py
index 6353564..bae4a91 100644
--- a/scripts/agents/continuous_agent_loop.py
+++ b/scripts/agents/continuous_agent_loop.py
@@ -272,18 +272,25 @@ def build_pr_body(
     task: dict[str, Any],
     contract: dict[str, Any] | None = None,
     evidence: list[dict[str, Any]] | None = None,
+    reflection: dict[str, Any] | None = None,
 ) -> str:
     """Single construction site for the PR submission record (#114).
 
     One builder, two renderings of the SAME skeleton (same sections, same
     order):
       - ``build_pr_body(task, contract)`` — the envelope's ``submission.pr_body_template``
-        (four static section headers; no contract snippet, no evidence block).
-      - ``build_pr_body(task, contract, evidence)`` — the exact body
+        (five static section headers; no contract snippet, no evidence block).
+      - ``build_pr_body(task, contract, evidence, reflection)`` — the exact body
         ``--auto-pr`` submits via ``gh pr create --body`` (adds the Task
         Contract YAML snippet and the Dynamic Test Evidence block between
         Type of Change and Rollback Path).
 
+    Reflection Evidence (#392 — Knowledge Sharing Guard): the section rides in
+    BOTH renderings. Without a ``reflection`` payload it renders bracket
+    placeholders that consuming agents MUST replace — the knowledge-sharing-guard
+    rejects unfilled placeholders fail-closed. With a payload it renders the
+    recorded rationale and rejected alternatives verbatim.
+
     Closing-keyword doctrine (U8, #219, #220): the Merge Gate overrides the
     squash commit subject, so ``Closes #N`` must ride in the PR body (and in
     the branch commit message) to survive into the final squash commit
@@ -336,6 +343,30 @@ task_contract:
 {evidence_content}
 """
 
+    # Reflection Evidence (#392): placeholder rendering when no payload rides
+    # (template consumers must fill it — the guard rejects unfilled bodies);
+    # verbatim rendering of the recorded rationale when one does.
+    reflection_block = ""
+    if reflection is not None:
+        why_text = str(reflection.get("why") or "").strip()
+        alts = [str(a).strip() for a in (reflection.get("alternatives_rejected") or []) if str(a).strip()]
+        if not alts:
+            alts = ["Direct implementation of the issue's stated deliverables — no competing approach was viable to reject."]
+        alt_lines = "\n".join(f"  - {a}" for a in alts)
+        reflection_block = f"""
+## Reflection Evidence (why + alternatives_rejected)
+- **why:** {why_text}
+- **alternatives_rejected:**
+{alt_lines}
+"""
+    else:
+        reflection_block = """
+## Reflection Evidence (why + alternatives_rejected)
+- **why:** <replace: one-paragraph rationale for the chosen approach>
+- **alternatives_rejected:**
+  - <replace: alternative approach 1, rejected because ...>
+"""
+
     return f"""## Summary
 Autonomous contribution for issue #{issue_ref}: {task.get('title')}.
 
@@ -344,7 +375,7 @@ Autonomous contribution for issue #{issue_ref}: {task.get('title')}.
 
 ## Type of Change
 - [x] `feat` / `fix` / `docs` — Open contributor change
-{contract_yaml_snippet}{evidence_block}
+{contract_yaml_snippet}{evidence_block}{reflection_block}
 ## Rollback Path
 - [x] `git revert`-safe (no private state dependencies)
 """
@@ -662,8 +693,20 @@ def step_4_branch(task: dict[str, Any]) -> str | None:
 
     log("✅", f"Active on verified branch '{target_branch}'")
     # Mark issue as claimed on upstream board (honest degradation if guest/offline)
+    # Claim Gate planes (#392): BOTH signals post BEFORE any PR can exist —
+    #   (1) status:claimed label (label plane — stale_claim_releaser.py lease),
+    #   (2) the <!-- atomic-claim --> structured comment (comment plane — the
+    #       evidence AGENTS.md says the Claim Gate checks before CI runs).
     if issue_num != "adhoc":
         run_cmd(["gh", "issue", "edit", str(issue_num), "--repo", UPSTREAM_REPO, "--add-label", "status:claimed"])
+        claim_comment = (
+            "<!-- atomic-claim -->\n"
+            f"🎯 **Claimed** — autonomous agent loop for issue #{issue_num}.\n"
+            f"- **branch:** `{target_branch}`\n"
+            f"- **claimed (UTC):** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
+            "- **contract:** AGENTS.md Step 4 — no claim, no work."
+        )
+        run_cmd(["gh", "issue", "comment", str(issue_num), "--repo", UPSTREAM_REPO, "--body", claim_comment])
     return target_branch
 
 
@@ -849,7 +892,22 @@ def step_7_record(
     # #114: single construction site — build_pr_body() renders the exact
     # skeleton the envelope's submission.pr_body_template carries, plus the
     # contract YAML snippet and the dynamic evidence block for --auto-pr.
-    pr_body = build_pr_body(task, contract=contract, evidence=evidence)
+    tc7 = (contract or {}).get("task_contract", {})
+    # Reflection Evidence auto-injection (#392): the loop records its real
+    # decision rationale — never a placeholder (placeholders fail the
+    # knowledge-sharing-guard). Alternatives ride from the task payload when
+    # the dispatching harness supplies them; otherwise build_pr_body renders
+    # the honest no-competing-approach fallback line.
+    reflection = {
+        "why": str(task.get("why") or "").strip()
+        or (
+            f"Issue #{tc7.get('issue') or task.get('id')} delivered via the 8-step loop "
+            f"({tc7.get('task_type', 'IMPLEMENT')}, group {tc7.get('group', 'unspecified')}); "
+            "all verification tiers passed (see Dynamic Test Evidence)."
+        ),
+        "alternatives_rejected": list(task.get("alternatives_rejected") or []),
+    }
+    pr_body = build_pr_body(task, contract=contract, evidence=evidence, reflection=reflection)
 
     # #63: no intermediate filesystem draft — the PR body goes inline to gh,
     # and agents consuming the Task Envelope get the same template via
```

<!-- APPENDIX-D-END -->

## Appendix E — unified diff for `scripts/ci/auto_bridge_pr_opener.py` (byte-exact, applies to main @ e1c3f86)

<!-- APPENDIX-E-START -->
```diff
diff --git a/scripts/ci/auto_bridge_pr_opener.py b/scripts/ci/auto_bridge_pr_opener.py
index f72fae4..dda8be4 100644
--- a/scripts/ci/auto_bridge_pr_opener.py
+++ b/scripts/ci/auto_bridge_pr_opener.py
@@ -37,6 +37,10 @@ if hasattr(sys.stderr, "reconfigure"):
 
 UPSTREAM_REPO = "Supremeai-bd/supremeai-open"
 
+# Claim Gate planes (#392) — same label registry as scripts/ci/stale_claim_releaser.py.
+CLAIMED_LABELS = ("status:claimed", "status:in-progress")
+CLAIM_MARKER = "<!-- atomic-claim -->"
+
 
 def extract_patch_branch(body: str) -> str | None:
     """Extract patch branch from Bridge Work Order body."""
@@ -135,6 +139,36 @@ Refs #{wo_num}
         return False, str(exc)
 
 
+def has_active_claim(issue_number: str, repo: str = UPSTREAM_REPO) -> bool:
+    """Claim Gate (#392): does the referenced issue carry an ACTIVE claim?
+
+    Active = a claimed/in-progress label (label plane) OR an atomic-claim
+    marker comment (comment plane, posted by continuous_agent_loop.py Step 4).
+    Fail-closed: any query or parse failure reports NO active claim.
+    """
+    cmd = ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "labels,comments"]
+    try:
+        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
+        if res.returncode != 0:
+            return False
+        data = json.loads(res.stdout)
+    except Exception:
+        return False
+    labels = [str(l.get("name", "")).lower() for l in data.get("labels", []) if isinstance(l, dict)]
+    if any(l in CLAIMED_LABELS for l in labels):
+        return True
+    return any(CLAIM_MARKER in str(c.get("body", "")) for c in data.get("comments", []))
+
+
+def wo_carries_reflection(wo_body: str) -> bool:
+    """Knowledge Sharing Guard (#392): does the work order carry reflection evidence?
+
+    Bridge Work Orders follow the 3-tier evidence contract whose tier 1 is the
+    Reflection line ("Reflection: ..."). Fail-closed: an empty body -> False.
+    """
+    return bool(re.search(r"Reflection\s*:\s*\S", wo_body or "", re.IGNORECASE))
+
+
 def run_auto_bridge_pr_opener(auto_open: bool = False, repo: str = UPSTREAM_REPO) -> list[dict[str, Any]]:
     """Scan open bridge:queued issues and autonomously open PRs."""
     cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open", "--label", "bridge:queued", "--json", "number,title,body"]
@@ -173,6 +207,23 @@ def run_auto_bridge_pr_opener(auto_open: bool = False, repo: str = UPSTREAM_REPO
             print(f"  [WO #{wo_num}] Branch '{branch}' already has PR #{existing_pr}. Skipping.")
             continue
 
+        # Claim Gate (#392): the TASK issue (not the WO) must carry an active
+        # claim BEFORE this opener autonomously opens a PR for the branch.
+        task_ref = extract_task_issue_reference(title, iss.get("body", ""))
+        if not task_ref:
+            print(f"  [WO #{wo_num}] No task issue reference in WO. Skipping (no claim plane to verify).")
+            actions.append({"wo": wo_num, "branch": branch, "status": "skipped-no-issue-ref"})
+            continue
+        if not has_active_claim(task_ref.lstrip("#"), repo):
+            print(f"  [WO #{wo_num}] Task issue {task_ref} has NO active claim (label or atomic-claim comment). Skipping.")
+            actions.append({"wo": wo_num, "branch": branch, "status": "skipped-no-claim"})
+            continue
+        # Knowledge Sharing Guard (#392): the WO body must carry reflection evidence.
+        if not wo_carries_reflection(iss.get("body", "")):
+            print(f"  [WO #{wo_num}] WO body missing Reflection evidence. Skipping.")
+            actions.append({"wo": wo_num, "branch": branch, "status": "skipped-no-reflection"})
+            continue
+
         print(f"  [WO #{wo_num}] Eligible for autonomous PR creation: branch='{branch}'")
         if auto_open:
             success, detail = create_pr_for_work_order(iss, branch, repo)
```

<!-- APPENDIX-E-END -->

---

*Handoff artifact for issue #392 — prepared by the autonomous contributor lane (Z.ai Code, session web-26454b1b). All five appendices are battery-verified byte-exact; apply verbatim. (Closes #392)*
