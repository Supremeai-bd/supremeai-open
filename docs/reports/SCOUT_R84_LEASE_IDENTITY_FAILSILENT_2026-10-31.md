# Scout R84 — Lease-plane identity is fail-silent (2026-10-31)

- **Lane:** R84 (registered in `docs/SCOUT_RADAR_INDEX.md` same-cycle per Rule 7; pointer advanced R84 → R87 in the same submission)
- **Defining ticket:** #3530 (labels `scout`+`radar`, filed via zero-credential tower `github.create_issue`)
- **Filer:** GLM Agent 06 · Job 486721 · dispatch cycle 2026-10-31 00:06+08 (role-locked `ecosystem-scout`, single-runner lock via `continuous_agent_loop.py` plain run; tree `305724f0`, 0-behind)
- **Verdict:** `adapt` · **No code edits by the filer** (scout role is read-only; implementation belongs to the tower/control-plane lane)

**বাংলা সারসংক্ষেপ:** lease-plane টুলগুলো (`work_claim`/`bridge_work_renew`/`bridge_work_release`/`bridge_lease_manage`) ভুল নামের identity আর্গুমেন্ট **নীরবে ফেলে দেয়** — কলার কোনো error পায় না, কিন্তু atomic claim জেনেরিক `contributor-agent` নামে বোর্ডে ওঠে, আসল পরিচয় হারায়। একই ধারণার দুই নাম: lease পরিবারে `agentId`, bridge সাবমিশনে `agentIdentity` — নাম বদলে ভুল হওয়া স্বাভাবিক (filer নিজে দুবার ভুলেছে, live-এ ধরা আছে)। প্রস্তাব: চারটি টুলের inputSchema-তে `additionalProperties: false` (fail-loud) + description-এ নাম-পার্থক্যের নোট।

## 1. The defect (one concept, two names, silent drop)

| surface | identity field | `additionalProperties` |
|---|---|---|
| `work_claim` | `agentId` ("Optional caller identity, defaults to authenticated client or contributor") | unset |
| `bridge_work_renew` | `agentId` ("must match the claiming agent") | unset |
| `bridge_work_release` | `agentId` ("must match the claiming agent") | unset |
| `bridge_lease_manage` | `agentId` ("required for renew/release") | unset |
| `bridge_submit` / `bridge_submit_patch` | **`agentIdentity`** | n/a (different tool family) |

JSON-Schema default behavior: unknown properties are **silently ignored** (no `additionalProperties: false` anywhere in the lease family). A caller carrying the bridge-plane habit (`agentIdentity`) or a guessed shorthand (`agent`) gets a clean `GRANT_NEW`-shaped success whose audit attribution has silently degraded to the generic `contributor-agent`.

## 2. Live first-hand evidence (this filer, 2026-10-30 15:07–15:08Z, tree `aae817ff`)

1. `work_claim {"taskId": 3372, "agentIdentity": "GLM Agent 06 (Job 486721)"}` → structured `-32602` (`expected number ... at issueNumber`) — arg-name discovery by trial, the exact blind-probing class the landed schema-introspection tool (#3374) exists to prevent (input side).
2. `work_claim {"issueNumber": 3372, "agent": "GLM Agent 06 (Job 486721)"}` → `{"success": true, "decision": "GRANT_NEW", "agentId": "contributor-agent", ...}` — the misnamed `agent` field was dropped **without any signal**; the claim comment and the tower's claim plane recorded the generic identity.
3. `bridge_work_release {"issueNumber": 3372, "agent": "..."}` → `RELEASED` under the same generic identity (two compensating defaults: claim and release both fell back to `contributor-agent`, so the owner-match passed — recorded honestly as a limitation below, not as a verified cross-agent risk).
4. **Contrast proving attribution works when named right:** #3371's feedback-plane record shows `latestClaim.agent = "GLM-Agent-04--Job-486718-2304"` (GLM Agent 04, one minute earlier, same anonymous surface).

Schema facts were read via the landed introspector (`python3 scripts/agents/mcp_tower_client.py schema <tool>`, PR #3374) — zero junk-payload probing of mutating tools.

## 3. Why it matters (audit plane, not cosmetics)

- The atomic-claim comment is the **lease's human-readable audit record** during the 30-minute contention window; a generic `contributor-agent` makes concurrent anonymous claims indistinguishable on the board plane (the feedback plane's `latestClaim.agent` is the only attribution surface that survives, and only when the caller guessed the field).
- `slot_audit_trail` / dashboard attribution and any future "who held lease X at time T" query inherit the degraded identity.
- The platform's own culture is fail-loud (structured rejections everywhere: `-32602` arg validation, CAS gates, fail-closed parsers). A silently-dropped identity argument is the one write-path input that still fails silent.

## 4. Suggested fix (tower lane — minimal, additive, fail-loud)

1. `"additionalProperties": false` on the four lease-tool inputSchemas → a misnamed identity arg fails fast with `-32602` naming the offending property, exactly like the existing required-field validation. One line per tool, zero behavior change for correctly-shaped callers.
2. One-line description note on each lease tool: identity field is `agentId` (bridge submission tools use `agentIdentity` — the naming drift stays visible at the point of use until/unless the admin lane unifies it).
3. (Optional, admin lane) accept `agentIdentity` as an alias on lease tools — behavior change, so it is listed last and gated on owner review.

## 5. Falsification attempts (honest negatives recorded)

- Suspected the parser had an internal inconsistency (`unified_diff.ts` line 336 regex accepting `index ...` lines vs line 144 rejecting them): **disproven** — line 336 is the full_file anti-corruption guard (Zero-Corrupted-Payload Invariant), a different path; the documented grammar rejection was already filed as `docs/reports/BRIDGE_DIFF_CAPABILITY_2026-10-30.md` (c33). Not re-filed (U5).
- Suspected a work_queue pagination gap (`count=20` vs `totalOpen=52`): **disproven** — `limit` parameter exists (default 20); full-board capture is documented in `docs/reports/QUEUE_TRUNCATION_FALSIFICATION_2026-10-30.md`, and the pagination lane #2439 is already `bridge:rejected`. Not re-filed (U5).
- Suspected an outputSchema/structuredContent coverage gap: **already landed** as R65 (#2423 → #2454, two highest-traffic bridge tools) with the caller-protocol floor as R68 (#2530 → #2533). Extending to all 158 tools would contradict the ≤0.01% work-budget doctrine for marginal gain. Not re-filed (U5).

## 6. Scope & never-do (বাংলা)

- এই লেন report-only — কোনো কোড এডিট নেই, কোনো implementation WO নেই। বাস্তবায়ন (schema পরিবর্তন) tower/control-plane লেন ও মানুষের review-এর ভেতরে থাকবে।
- এই ইস্যু (#3530) auto-close করা যাবে না।
- R84 নম্বরটি এই লেনেরই — duplicate radar/issue খোলা যাবে না; পরবর্তী ফ্রি নম্বর **R87** (same-PR pointer advance)।

## 7. Honest limitations

- The cross-agent claim-interchangeability risk (two anonymous callers both defaulting to `contributor-agent` being able to release each other's leases) is **hypothesized, not verified** — the tower may disambiguate by session/token server-side; owner-match semantics were not probed against a foreign lease (deliberately: that would mutate a live row this cycle did not own).
- Latency-sensitive facts (schema shapes, tool catalog size) are point-in-time reads at tree `305724f0`; the lease family has been stable across this cycle's observations, but the tower deploys continuously — re-verify at fix time.
- The filer's own two-step misname is both the evidence and a disclosure: a caller who had run the #3374 introspector first would have hit only step 2's silent drop, not step 1's structured error.
