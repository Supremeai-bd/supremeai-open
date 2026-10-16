# CLAIM_GUARDS — Operator Hand-off for #392 (Claim Gate + Knowledge Sharing Guard)

**Issue #392 (P1-high, handoff:coder)** · delivery: hybrid lane. The bridge intake
**hard-blocks `.github/` writes** (`bridge_submit_patch` rejects protected paths —
measured this session: `Path '.github/workflows/pipeline.yml' is protected (.github/)`),
so the two guard jobs and the PR template ride as **byte-exact copy-paste blocks**
below, while every bridgeable artifact ships direct in the same work order:

| Artifact | Delivery |
|---|---|
| `scripts/ci/auto_bridge_pr_opener.py` | **direct** (ships in the WO; guard-compliant PR bodies + claim precheck) |
| `tests/test_ci_guards.py` | **direct** (ships in the WO; 17 checks, 2 auto-skip until §1/§4 applied) |
| `pipeline.yml` guard jobs | **hand-off** (§1 + §2 below) |
| `.github/PULL_REQUEST_TEMPLATE.md` | **hand-off** (§4 below) |

## 1. `claim-guard` — insert into `.github/workflows/pipeline.yml`

Anchor: **between the end of `duplicate-pr-guard` (final line
`echo "✅ No competing duplicate PRs detected for: $ISSUES"`) and
`boundary_sanitization_guard:`**. Purely additive; house style mirrors the three
existing zero-checkout guards.

```yaml
  claim-guard:
    name: "🎫 Claim Gate Guard (#392)"
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - name: Verify referenced issue carries an active claim (event-context only, no checkout)
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_LABELS: ${{ join(github.event.pull_request.labels.*.name, ' ') }}
          HEAD_REF: ${{ github.event.pull_request.head.ref }}
          REPO: ${{ github.repository }}
        run: |
          echo "Claim Gate (AGENTS.md Step 4: no claim, no work) — referenced issues: PR #${{ github.event.pull_request.number }}"
          # অ্যাডমিন escape hatch — হাউজ প্যাটার্ন (issue-reference-guard এর মতো)
          if [[ "$PR_LABELS" == *"guard-exempt"* ]]; then
            echo "✅ 'guard-exempt' label present — guard skipped."; exit 0
          fi
          # বট-জেনারেটেড ব্রাঞ্চ অনুমোদিত (branch-naming-guard এর হাউজ প্যাটার্ন —
          # dependabot ইত্যাদি ক্লেইম লিখতে পারে না; regression এড়াতে exempt)
          if [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot|all-contributors|gh-readonly)/ ]] \
             || [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot)\[?[a-z_]* ]]; then
            echo "✅ Automated/bot branch — claim gate not applicable."; exit 0
          fi
          # Issue extraction — duplicate-pr-guard এর সাথে অভিন্ন ভোকাবুলারি
          TARGET_ISSUES=$(echo "$PR_TITLE $PR_BODY" | grep -ioE '(closes|fixes|resolves) #[0-9]+' | grep -oE '#[0-9]+' || true)
          BRANCH_ISSUES=$(echo "$HEAD_REF" | grep -oE 'issue-?[0-9]+' | grep -oE '[0-9]+' | sed 's/^/#/' || true)
          ISSUES=$(printf "%s\n%s" "$TARGET_ISSUES" "$BRANCH_ISSUES" | grep -E '^#[0-9]+' | sort -u || true)
          if [ -z "$ISSUES" ]; then
            # Fallback to general issue references (issue-reference-guard এ ধরা আছে; এখানে শুধু claim যাচাই)
            ISSUES=$(echo "$PR_TITLE $PR_BODY" | grep -oE '#[0-9]+' | sort -u || true)
          fi
          if [ -z "$ISSUES" ]; then
            echo "✅ No issue reference found — issue-reference-guard owns that failure; claim gate passes."
            exit 0
          fi
          # Claim predicate (fail-closed, SSOT vocabulary aligned with stale_claim_releaser):
          #   PASS ① labels contain status:claimed / status:in-progress
          #   PASS ② labels contain an active bridge:* label (a filed Bridge Work Order IS
          #          the zero-credential claim vehicle — agents cannot write status labels)
          #   PASS ③ an <!-- atomic-claim --> comment exists, UNLESS status:unclaimed
          #          (the released-marker from stale_claim_releaser) vetoes comment-based claims
          #   FAIL closed when no referenced issue shows any active claim.
          CLAIMED=""
          for iss in $ISSUES; do
            iss_num="${iss#"#"}"
            DATA=$(gh issue view "$iss_num" --repo "$REPO" --json labels,comments 2>/dev/null || true)
            [ -z "$DATA" ] && continue
            LABELS=$(echo "$DATA" | jq -r '(.labels // [])[] | .name' 2>/dev/null || true)
            if echo "$LABELS" | grep -qx "status:claimed" || echo "$LABELS" | grep -qx "status:in-progress"; then
              CLAIMED="$iss (status label)"; break
            fi
            if echo "$LABELS" | grep -q "^bridge:"; then
              CLAIMED="$iss (bridge work order)"; break
            fi
            if echo "$LABELS" | grep -qx "status:unclaimed"; then
              continue
            fi
            if echo "$DATA" | jq -r '(.comments // [])[] | .body' 2>/dev/null | grep -q '<!-- atomic-claim -->'; then
              CLAIMED="$iss (atomic-claim comment)"; break
            fi
          done
          if [ -n "$CLAIMED" ]; then
            echo "✅ Active claim found: $CLAIMED"; exit 0
          fi
          echo "::error::PR opened without a prior claim on Issue(s) $ISSUES. Per AGENTS.md Step 4 (No claim, no work), claim the issue before creating a branch or PR."
          echo "Claim vocabulary: 'status:claimed'/'status:in-progress' label, '<!-- atomic-claim -->' comment, or a filed Bridge Work Order (bridge:* label)."
          echo "(Admin escape hatch: add the 'guard-exempt' label.)"
          exit 1
```

## 2. `knowledge-sharing-guard` — insert immediately after `claim-guard`

```yaml
  knowledge-sharing-guard:
    name: "📚 Knowledge Sharing Guard (#392)"
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - name: Verify PR body carries Reflection Evidence (event-context only, no checkout)
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_BODY: ${{ github.event.pull_request.body }}
          PR_LABELS: ${{ join(github.event.pull_request.labels.*.name, ' ') }}
          HEAD_REF: ${{ github.event.pull_request.head.ref }}
        run: |
          echo "Knowledge Sharing Guard (AGENTS.md §2/§5: reflection evidence mandatory) — PR #${{ github.event.pull_request.number }}"
          if [[ "$PR_LABELS" == *"guard-exempt"* ]]; then
            echo "✅ 'guard-exempt' label present — guard skipped."; exit 0
          fi
          if [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot|all-contributors|gh-readonly)/ ]] \
             || [[ "$HEAD_REF" =~ ^(dependabot|github-actions|copilot)\[?[a-z_]* ]]; then
            echo "✅ Automated/bot branch — reflection template not applicable."; exit 0
          fi
          BODY_FILE=$(mktemp)
          printf '%s' "$PR_BODY" > "$BODY_FILE"
          trap 'rm -f "$BODY_FILE"' EXIT
          if ! grep -q "## Reflection Evidence" "$BODY_FILE"; then
            echo "::error::PR body missing required '## Reflection Evidence (why + alternatives_rejected)'. AGENTS.md mandates knowledge capture on every contribution."
            echo "Add the section (see .github/PULL_REQUEST_TEMPLATE.md):"
            echo "  ## Reflection Evidence (why + alternatives_rejected)"
            echo "  - **why:** <rationale and approach>"
            echo "  - **alternatives_rejected:**"
            echo "    - <alternative approach rejected because ...>"
            echo "(Admin escape hatch: add the 'guard-exempt' label.)"
            exit 1
          fi
          # Non-empty '- **why:**' answer (same-line text required)
          # '<' rejects the template placeholder '<!-- ... -->' so an unfilled template fails closed
          if ! grep -Eq '^[[:space:]]*-[[:space:]]*\*\*why:\*\*[[:space:]]+[^[:space:]<]' "$BODY_FILE"; then
            echo "::error::'## Reflection Evidence' found but '- **why:**' is empty or a placeholder."
            exit 1
          fi
          # Non-empty alternatives_rejected: inline text on the label line OR at least one
          # non-empty sub-item below it (within the reflection section).
          # awk discipline: 'exit' still runs END — the verdict is computed in END from flags.
          if ! awk '
            f && /\*\*alternatives_rejected:\*\*/ {
              found = 1
              rest = $0
              sub(/.*\*\*alternatives_rejected:\*\*[[:space:]]*/, "", rest)
              if (rest != "") { ok = 1; exit }
              while ((getline line) > 0) {
                if (line ~ /^[[:space:]]*-[[:space:]]*[^[:space:]]/) { ok = 1; exit }
                if (line ~ /^[^[:space:]]/) { ok = 0; exit }
              }
              ok = 0
              exit
            }
            /## Reflection Evidence/ { f = 1 }
            END { if (!found || ok != 1) exit 1 }
          ' "$BODY_FILE"; then
            echo "::error::'## Reflection Evidence' found but '- **alternatives_rejected:**' is empty."
            echo "Document at least one alternative that was considered and discarded."
            exit 1
          fi
          echo "✅ Reflection Evidence present with non-empty 'why' and 'alternatives_rejected'."
```

## 3. Design contract (why these predicates)

- **Claim vocabulary (SSOT, aligned with `scripts/ci/stale_claim_releaser.py`)**:
  PASS = `status:claimed` / `status:in-progress` label · an open `bridge:*` label
  (a filed Bridge Work Order **is** the zero-credential claim vehicle — external
  agents cannot write status labels) · an `<!-- atomic-claim -->` comment.
  `status:unclaimed` (the released-marker written by the releaser) **vetoes**
  comment-based claims; a label-based claim always wins (re-claim re-adds the label).
- **Bot exemption** (both guards): `dependabot|github-actions|copilot|all-contributors|gh-readonly`
  branches — house pattern from `branch-naming-guard`; bots cannot claim or reflect,
  and blocking them would regress existing automation.
- **Knowledge-sharing checks**: `## Reflection Evidence` header required; `- **why:**`
  must carry same-line text (leading `<` rejected so the unfilled template
  `<!-- ... -->` placeholder fails closed); `- **alternatives_rejected:**` needs
  inline text or >=1 non-empty sub-item. awk discipline: `exit` still runs `END` —
  the verdict is computed in `END` from flags.
- **`guard-exempt`** label bypasses both guards (admin escape hatch, per the issue).

## 4. `.github/PULL_REQUEST_TEMPLATE.md` — create with exactly this content

````markdown
# Summary & Purpose

<!-- What changed and why. One paragraph. -->

## Claim & Work Order

<!-- Reference the claimed issue: `Closes #N` — per AGENTS.md Step 4 (no claim, no work),
     the issue must carry an active claim BEFORE this branch was created:
     a `status:claimed`/`status:in-progress` label, an `<!-- atomic-claim -->` comment,
     or a filed Bridge Work Order (bridge:* label). -->

## Reflection Evidence (why + alternatives_rejected)

- **why:** <!-- rationale and approach — the design decision this PR embodies -->
- **alternatives_rejected:**
  - <!-- alternative approach considered and discarded, because ... -->

## Test Evidence (3-tier contract)

<!-- 1. Reflection check (git grep anchors) 2. Boot smoke test 3. Test suite -->

## Rollback Path

<!-- git revert-safe? config/migration side effects? -->
````

## 5. Post-apply verification (fail-closed round trip)

1. `bash -n` both extracted run blocks (extract via `yq` or an equivalent `python3 -c` YAML snippet) — syntax clean.
2. `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/pipeline.yml'))"` — 16 jobs total.
3. `python3 tests/test_ci_guards.py` → **17/17, 0 skips** (the two gated checks
   `test_pipeline_carries_both_guard_jobs` / `test_pr_template_exists_with_reflection_section`
   auto-skip with a pointer here until §1/§4 are applied).
4. Tier-1 reflection check per the issue: `git grep -n "claim-guard" .github/workflows/pipeline.yml`.
5. Open a scratch PR against an unclaimed issue → both guards fail closed with the
   documented `::error::` messages; add `guard-exempt` → both pass.

## 6. Scope notes

- **Deliverable 3 of the issue (`scripts/agents/continuous_agent_loop.py` reflection
  injection) is intentionally NOT in this slice**: two queued bridge WOs (#378, #379)
  already book that file — a third editor reproduces the same-path exclusion class
  that killed #347/G1. The `build_pr_body()` change here already covers bridge-lane
  PRs; the loop-side injection remains for the WO that lands after those.
- The opener's PR-body change is **pair-consistent** with knowledge-sharing-guard:
  pre-guard PR bodies would fail the new guard, so both ship in the same change.
- Router audit: `scripts/ci/*` + `tests/*` have no dispatch case arm → central
  monorepo always receives; this doc rides `docs/*` → `Supremeai-bd/supremeai`.
