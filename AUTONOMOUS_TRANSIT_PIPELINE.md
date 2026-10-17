1. Claim & Branch: Agent claims issue; webhook creates task branch; agent pushes only there.
2. Webhook PR & CI: Webhook opens PR on supremeai-open; public CI passes -> auto-merges to main.
3. Bridge Barrier: Bridge does not exist before open:main merge; private intake ignores unmerged code.
4. Dual Dispatch: On open:main merge, bridge dispatches code to target satellite and monorepo.
5. Auto-Prune: Once target merges, webhook permanently deletes transit file from supremeai-open.
6. No Claim No Push: Any push without active atomic claim on the issue is blocked fail-closed.
7. No Push to Main: Direct push to main is strictly blocked across all federation repositories.
8. No Agent Branching: Agents cannot create branches; unprovisioned branches are rejected.
9. 30-Min Stale Expiry: If no push arrives within 30 minutes of claim, issue is auto-unclaimed.
10. Anti-Tamper: Any action outside this exact pipeline is treated as intrusion and blocked.
11. Loop Entry: Agent triggers continuous loop on arrival to inspect the live GitHub board.
12. Queue Active Prompt: If open issue exists -> Prompt: "Claim issue, load all CODER rules, and fix inside scope."
13. Queue Empty Prompt: If no issue exists -> Prompt: "Inspect codebase, load all AUDITOR rules, and run audit."
14. Role Contract Routing: Issues matching other domains load exact role rules (ARCHITECT, REVIEWER, CI_FIXER).
15. Continuous Reset: Upon task or audit completion, loop resets immediately to re-poll board with zero sleep.
16. Self-Healing Board: All pipeline failures, merge conflicts, warnings, and audit findings across all repositories auto-create issues on supremeai-open.
17. Deployment Strategy: On target repo merge, agent triggers manual deploy if immediate; otherwise scheduled auto-deploy runs 4x/day on diffs. Monorepo only receives merge sync.
18. Unified Gateway Shield: `supremeai-api` is the single external proxy; all underlying providers (Gemini, Groq, OpenRouter, etc.) are strictly shielded behind it.
19. Vault-Only Provider Keys: Provider credentials remain server-side in the vault; all direct third-party provider key references across federation projects are removed.
20. Internal Failover & Rotation: Dynamic failover chains, token rotation, model degradation, and quota management execute transparently behind `supremeai-api`.
21. One Key SSOT: All downstream apps, agents, studio, and internal modules authenticate exclusively using `SUPREMEAI_API_KEY` (OpenAI-compatible schema).
22. User Quota & Key Issuance: End-user API keys, tenant rate limiting, monetization tiers, and consumption billing are provisioned and governed solely through `supremeai-api`.
23. Lean Tool Diet: MCP Tower purges redundant branch, ad-hoc patching, and duplicate provider tools, cutting tool surface by ~25% to maximize execution speed and eliminate hallucinations.
24. Multi-Transport Protocol Autonomy: Agents autonomously select connection transport (`/mcp`, `/sse`, or `/json`) based on their environment and runtime capabilities.
25. Scoped Dynamic Session URL: Connection endpoints follow `/{protocol}/{provider}/{user}/{datetime}`, ensuring zero collision across 100+ concurrent agents, instant DB traceability, and seamless role transitions.
26. 3-Strike Quarantine: If an issue triggers 3 consecutive CI failures or unclaims, it auto-locks into `status:quarantine`, halting agent retries until admin triage.
27. Institutional Memory & Zero-Residue Retirement: When features, specs, or legacy modules are retired, they are archived permanently into `Supremeai-bd/supremeai-archive` and cleanly pruned from both the active satellite and core monorepo (Zero Residue / Historical SSOT).

---

## 3-Stage Lifecycle & Zero-Residue Data Flow (3-ধাপের ক্লিন ট্রানজিট ও রিটায়ারমেন্ট পাইপলাইন)

```text
       [ External Contributor / Autonomous Agent ]
                           │
                           ▼
        ১. ইনগ্রেস (পাবলিক ট্রানজিট স্টেশন / Ephemeral Mailbox)
           👉 Supremeai-bd/supremeai-open
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
    ২. টার্গেট স্যাটেলাইট (Active)     ২. সেন্ট্রাল মনোরেপো (Sync)
       যেমন: supremeai-browser           Supremeai-bd/supremeai
             │                           │
             └─────────────┬─────────────┘
                           │
          [ open থেকে অটো-প্রুন (মুছে সাফ: rm patches/*) ]
                           │
               (কাজ যখন রিটায়ার্ড / পুরনো হবে)
                           │
                           ▼
           ৩. চূড়ান্ত আর্কাইভ (স্থায়ী প্রাতিষ্ঠানিক মেমোরি)
              👉 Supremeai-bd/supremeai-archive
                           │
           [ স্যাটেলাইট ও মনোরেপো থেকে মুছে সাফ (Zero Waste) ]
```
