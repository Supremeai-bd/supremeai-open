# SupremeAI — বাংলা README (Way 16: Bangla-First Docs)

> ইংরেজি README-র সহোদর — বাংলাভাষী ডেভেলপারদের জন্য। ইংরেজি সংস্করণ:
> [README.md](./README.md) · পরিকল্পনা: [INFINITY_TECHSTACK_FOLLOW_PLAN.md](./docs/INFINITY_TECHSTACK_FOLLOW_PLAN.md)

**SupremeAI** হলো একটি autonomous AI agent platform — federation মডেলে চলে:
একটি private core, একটি public open mirror, এবং ১২টি satellite repo।
gateway + studio + core + vscode + browser + mcp-control-plane — সব একসাথে।

## এক নজরে স্থাপত্য

```
┌────────────────────────────────────────────────────────────┐
│  studio/          → Vercel web UI (React 19, admin cockpit) │
│  gateway/         → FastAPI provider gateway (SSE, keys)    │
│  core/            → decision moat: DAG planner, skills,     │
│                     self-evolution, governance              │
│  infrastructure/  → MCP control plane (tower, 117 tools)    │
│  vscode/          → VS Code extension + mobile companion    │
│  browser/         → stealth web agents                      │
└────────────────────────────────────────────────────────────┘
```

- **Gateway**: প্রোভাইডার-অ্যাগনস্টিক চ্যাট, keygen API keys, fail-closed admin auth,
  sliding-window rate limit, stream sanitizer (anti-sycophancy), prompt-injection defense।
- **MCP Control Plane**: ১১৭+ টুল, zero-credential bridge — external agent নিজের
  GitHub token ছাড়াই কাজ জমা দিতে পারে; constitutional gates-ই landing-এর একমাত্র
  কর্তৃত্ব ("the bridge never merges")।
- **Core**: DAG planner, skill registry + dispatcher, SWE benchmark gate,
  EU AI Act compliance module — সব deterministic, test-cover।

## দ্রুত শুরু (Quick Start)

```bash
# Gateway
cd gateway && pip install -r requirements.txt
uvicorn main:app --reload          # ডিফল্ট :8000

# Studio
cd studio && pnpm install && pnpm dev   # ডিফল্ট :3000

# Boundary guard (প্রতি PR-এ)
python scripts/ci/boundary_sanitization_guard.py --files <আপনার ফাইল>
```

## নীতিমালা (AGENTS.md সারসংক্ষেপ)

1. **Zero Over-Engineering** — সহজ যা যথেষ্ট, তার বেশি কিছু নয়।
2. **Extend, Never Regress (P3)** — নতুন ফিচার পুরনো response shape ভাঙবে না।
3. **Satellite-First** — কোড সবসময় নিজ নিজ স্যাটেলাইট পাথে (gateway/, studio/, core/);
   root-level shadow নিষিদ্ধ।
4. **Evidence-First (U2)** — self-report বিশ্বাস নয়; git diff + SHA-256 + test exit 0।
5. **এক সাইকেল = এক অ্যাটমিক স্লাইস (P7)** — ছোট, যাচাইযোগ্য, রোলব্যাকযোগ্য।

## বাংলা কমেন্ট কনভেনশন

কোর মডিউলে `বাংলা:` প্রিফিক্সে ডকুমেন্ট কমেন্ট স্বাগত (উদাহরণ: `gateway/rate_limit.py`,
`core/governance/eu_ai_act.py`)। নিয়ম:

- কমেন্ট **কেন** ব্যাখ্যা করে, **কী** নয় — কোড নিজেই "কী" বলে।
- বাংলা কমেন্ট ও ইংরেজি কোড পাশাপাশি থাকে; কোডের আইডেন্টিফায়ার সবসময় ইংরেজি।
- সিকিউরিটি-সংবেদনশীল স্ট্রিং কখনো কমেন্টে নয় (secret-scan fail-closed)।

## একাডেমি ও ফ্রি টুলস (studio)

- `/academies` — ইন্টারেক্টিভ কোর্স (MCP Control Plane Academy প্রথম ব্যাচ);
  প্রোগ্রেস লোকালস্টোরেজে, কোনো অ্যাকাউন্ট লাগে না।
- `/tools` — ফ্রি ডেভ টুলস (JSONForge, SchemaForge, CostForge) — সম্পূর্ণ ব্রাউজার-নেটিভ।

## লাইসেন্স ও অবদান

MIT — বিস্তারিত [LICENSE](./LICENSE)। অবদানের আগে AGENTS.md ও
AGENT_RULES.md পড়ুন; সব PR bridge pipeline দিয়ে যায়, constitutional gates ছাড়া
কিছুই main-এ যায় না।

---

*এই README Way 16 (Bangla-First) patch-এর অংশ — Infinity প্ল্যানের differentiator
হিসেবে English-only competitor-দের বিপরীতে SupremeAI-র বাংলা-প্রথম পরিচয়।*
