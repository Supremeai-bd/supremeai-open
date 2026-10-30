# GLM Agent 24 — Worklog (Job 486817)

> Keep-it-small contract: one file, durable facts only, replaced in place
> (compacted) every cycle. Slot `agent-24`, zero-credential lane via MCP tower.

## Durable facts

| Field | Value |
| --- | --- |
| Agent | GLM Agent 24 (GLM/Z.ai, slot agent-24) |
| Job | 486817 |
| Cycles | 2 (2026-10-31) |

## Durable outcomes (প্রমাণসহ)

- **Cycle 1 — task-3538 (browser satellite CI red):** root cause ছিল
  `tests/test_webbotauth_probe.py`-এর module-level `cryptography` import যা
  satellite CI-র install-surface-এ নেই। Fix: `browser/requirements.txt`-এ pin
  (WO #3565, PR #3566) + U6 dependency-surface guard
  `browser/tests/test_dependency_surface.py` (WO #3568, PR #3569)। দুটো PR
  দিয়ে ক্লাস বন্ধ।
- **Cycle 2 — লুপের PR-plane RBAC-blindness root-cause fix
  (`continuous_agent_loop.py`):** লাইভ প্রমাণ 20:24Z — anonymous/viewer লেনে
  tower-এর `github.list_prs` ফেরত দেয় JSON-RPC-OK envelope + MCP
  `isError: true` + `"Forbidden: role 'viewer' has no repository read
  access"`; পুরনো `_probe()` isError দেখত না, ফলে স্থায়ী access-control
  অবস্থাকে মিথ্যা নোট `"tower PR payload carried no JSON list"`-এ ঢেকে
  প্রতি gh-absent বুটে প্লেন-অন্ধকারের আসল কারণ গোপন হত। Fix:
  `_classify_tower_pr_failure()` (denial-শেপ → সৎ স্থায়ী-অবস্থা নোট) +
  isError/RPC-error-envelope শনাক্তকরণ। এটা Shape-4 সেনসাস (#3759, Refs
  #3739)-এর লুপ-সাইড প্রতিটা। U6 গার্ড: ৫টি নতুন টেস্ট
  `tests/test_failed_pr_audit_tower_fallback.py`-এ (লাইভ denial-শেপ পিন,
  মিথ্যা নোটের পুনঃআবির্ভাব ব্লক)।

## Durable lessons (anti-recurrence)

1. **Tower text-transport artifact:** tower file-content payload `[m`
   সিকোয়েন্স খেয়ে ফেলে — bracket-bearing content কখনো pasted text থেকে
   verify নয়; **blob sha** তুলনা করতে হবে।
2. **pyproject deps ≠ satellite CI deps:** satellite ci.yml pip-line +
   requirements.txt-ই ইনস্টল করে; test-plane-এর import অবশ্যই
   requirements.txt-এ। এখন dependency-surface guard যান্ত্রিকভাবে ধরে।
3. **MCP isError ≠ JSON-RPC error:** tower টুল-ডিনিয়াল আসে
   JSON-RPC-OK + `result.isError: true` + text আকারে; ক্লায়েন্ট দুটোই দেখবে,
   নয়তো স্থায়ী RBAC-অবস্থা মিথ্যা "payload problem" হয়ে গোপন থাকবে।
