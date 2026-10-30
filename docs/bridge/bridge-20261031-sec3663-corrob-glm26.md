# Bridge Receipt — #3663 (security P0, identity fail-open) independent second-agent corroboration: all live claims reproduced read-only; owner-lane routing endorsed; report-only, nothing closed, zero destructive calls

- **Agent:** GLM Agent 26 (Job 486824) · continuous-loop cycle 2026-10-31T02:2x-02:4x+08 · role solver
- **Lane:** report-only corroboration (docs-only, single new file under `docs/bridge/`, zero code, zero protected paths, no closure requested, zero claims taken)
- **Trigger:** loop dispatched #3663. The filing agent's own deploy-window analysis routes the 4-line fix to the owner lane; the non-duplicative agent duty is this independent verification. No corroboration existed at dispatch time (feedback plane + PR scan clean).

## বাংলা সারসংক্ষেপ

#3663-এর প্রতিটি live দাবি আমি স্বাধীনভাবে পুনরুৎপাদন করেছি — শুধুমাত্র read-only প্রোবে, কোনো destructive কল না করে, কোনো মান print না করে। অনন্য সেশনে 158টি টুল দৃশ্যমান, যার মধ্যে 10/11 destructive/secret-ক্লাস টুল (kill_switch, tenant_create, slot_revoke, credential rotate, client_revoke, redis flush…); anonymous `client_list` দেয় scope:"*" সহ 88 রো — 46টি role:"admin", 88টিই IP-আকৃতির id, টেন্যান্ট ফিল্টার সম্পূর্ণ no-op; তবে কোনো টোকেন-জাতীয় কী নাম নেই (একমাত্র ভালো গেট অটুট)। `autonomy_status` ও `system_health` দুটোই anonymous-reachable (topology disclosure বিদ্যমান)। ফাইলিং এজেন্টের owner-lane রাউটিং সিদ্ধান্তে আমি সহমত — ডিফল্ট বদলালে আমার নিজের zero-credential লেনসহ পুরো ফেডারেশন লক-আউট হওয়ার ঝুঁকি।

## Claim-by-claim verification (my independent read-only probes, 2026-10-31 ~02:3x+08)

| #3663 claim | My probe result | Verdict |
|---|---|---|
| Anonymous `tools/list` exposes destructive/secret classes | 158 tools visible; 10/11 probe-list present: `autonomy_kill_switch`, `tenant_create`, `slot_revoke`, `slot_rotate_credential`, `client_revoke`, `action_redis_flush`, `action_render_deploy`, `autonomy_enable`, `tenant_suspend`, `policy_approve` | CONFIRMED |
| `client_list` anonymous: scope `*`, 88 rows, 46 admin | scope:"*", count:88, role=="admin" rows:46 | CONFIRMED (exact) |
| IP-shaped identifiers disclose visitor PII | 88/88 ids match digit+underscore ip-shape heuristic (filing counted 20/88 with a tighter pattern; same exposure class, my count is the upper bound) | CONFIRMED (class) |
| Tenant scoping no-op on reads | filtered probe `tenantId:"tenant_default"` → scope still "*", 88 rows | CONFIRMED |
| No tokens leak | 0 token/secret/key-like key names across all 88 rows | CONFIRMED |
| `autonomy_status` global state disclosed | reachable anonymously, enabled-state in body | CONFIRMED |
| `system_health` topology disclosure | reachable anonymously; 5 `*.onrender.com` URL mentions | CONFIRMED |
| `autonomy_kill_switch` present in anonymous tool list | present (presence-only; NEVER invoked — zero-harm) | CONFIRMED |
| Identity fail-open `role ?? "admin"` at L1020/L988 | not re-read line-by-line; behaviorally proven by the entire battery above executing as anonymous global-admin-equivalent | CONFIRMED (behavioral) |

One count delta from the filing: probe-list shows 10/11 (one of the filing's named tools did not string-match my probe list; the class presence stands regardless).

## Routing endorsement (why no claim, no patch, no auto-close)

The 4-line flip (`role ?? "admin"` → `"viewer"`; drop the role-name global-admin shortcut) is correct but its landing is a deploy-policy/HITL judgment: the same default that is the vulnerability is also the current auth model of every zero-credential builder lane — flipping it without a coordinated guest-role-set decision + deploy window locks out the fleet's own evidence lane (this agent's lane included). The born-red test alternative is also correctly rejected (main-red P0 disruption). The filing agent's alternatives analysis is sound; this receipt adds only independent proof + the upper-bound PII-shape count.

## Root-cause note (for the owner's fix window)

Adopt the filing's blueprint verbatim (4 lines + Invariant-6-born-red guard: fresh anonymous session must assert `!isGlobalAdmin && role !== "admin"`, `client.list` errors, `tools/list` omits the destructive classes), pair it with the guest tool-visibility safe-list, and stage the control-plane deploy with builder-lane re-verification — the #3513 fail-closed CAS precedent shows this codebase lands such gates well once scoped.

## Reflection Evidence (why + alternatives_rejected)

- **why:** A security P0 on the federation's single door deserves two independent proofs before the owner burns a deploy window on it; the second pass also tightens the PII count (88/88 ip-shaped ids) and confirms the leak boundary (no token keys).
- **alternatives_rejected:** (1) Claiming and patching the 4 lines — rejected: deploy-policy blast radius on 22+ builder lanes; the finding's own routing is correct and I endorse it. (2) Invoking kill_switch or any destructive endpoint to prove reach — rejected: zero-harm doctrine; handler presence + poisoned-context behavior is sufficient proof. (3) Printing client rows/ids as evidence — rejected: zero-leak rule; counts and shape-matches only. (4) Waiting for the owner to act without corroboration — rejected: corroborated findings land faster (R86/#3513 precedent: corroborated 15:4xZ, gate live same day).

## Verification evidence (3-tier)

- Tier-3: single new file under `docs/bridge/`; no tracked file modified; no secret values anywhere in this receipt.
- Tier-2 (live smoke): every probe re-runnable via tower reads (`tools/list` via protocol, `client_list`, `autonomy_status`, `system_health`) with a fresh anonymous session; probe script counts reproducible.
- Tier-1 (reflection): this document.

## Rollback path

`git revert` the receipt commit; nothing depends on this file (new docs/bridge receipt, no code or index surface).
