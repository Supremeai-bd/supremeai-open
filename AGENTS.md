# SupremeAI — AGENTS.md

> **Agent Universal Constitution**  
> **Freedom:** Agent controls **HOW** to solve an assigned task inside its contract.  
> **Control:** Admin/System controls **WHERE, WHAT, ACCESS, LIMITS, STOPPING and major architectural decisions**.  
> **Canonical Rules:** [`AGENT_RULES.md`](./AGENT_RULES.md) · **Admin Work Budget:** ≤ 0.01% (Zero-Admin)

---

## 1. Visual Task Architecture (Federation Flow at a Glance)

```mermaid
flowchart TD
    subgraph INGRESS ["1. Ingress Pathways (§2)"]
        P1["Pathway 1: MCP Control Tower<br>(Zero-Credential Bridge)"] --> OPEN["Supremeai-bd/supremeai-open<br>(Public SSOT & Task Hub)"]
        P2["Pathway 2: Public Fork & PR<br>(External Web AI / Contributors)"] --> OPEN
        P3["Pathway 3: Ephemeral JIT Lease<br>(Automated CLI Runners)"] --> OPEN
    end

    subgraph LOOP ["2. The 8-Step Agent Lifecycle (§3)"]
        OPEN --> S1["1. Understand & 2. Load Rules"]
        S1 --> S2["3. Inspect State & Preflight (§2.4)"]
        S2 --> S3["4. Atomic Claim (No Claim = No Branch/Work)"]
        S3 --> S4["5. Smallest Safe Diff (≤ 30 files, ≤ 200 KB)"]
        S4 --> S5["6. 3-Tier Verification (Reflection → Smoke → Tests)"]
        S5 --> S6["7. PR Record + 8. Board Freshness Re-Check (#4177)"]
    end

    subgraph TRANSIT ["3. Ephemeral Transit & Landing (§4)"]
        S6 --> GATE{"Merge Gate<br>(Fail-Closed)"}
        GATE -- Green --> MERGE["Landing to main"]
        MERGE --> DISPATCH["Dispatch to Target Repository<br>(Monorepo / 1 of 12 Satellites)"]
        DISPATCH --> PRUNE["Auto-Prune Transit Patch<br>(Zero-Residue #416)"]
    end

    classDef hub fill:#1d76db,stroke:#fff,stroke-width:2px,color:#fff;
    classDef gate fill:#d93f0b,stroke:#fff,stroke-width:2px,color:#fff;
    class OPEN hub;
    class GATE gate;
```

---

## 2. Work Submission Pathways (Zero-Admin ≤ 0.01%)

| Pathway | Who & When | Mechanism |
|---|---|---|
| **1. MCP Control Tower (Primary)** | Claude, Cursor, Antigravity, Web bots | Zero-credential: tools provide context; proxy bot commits & opens PR. Endpoint: `https://supremeai-mcp-tower.onrender.com/mcp` |
| **2. Public Fork & PR** | External agents without credentials | Fork `supremeai-open`, push to fork, PR against `main`. Automated pipeline ports & verifies. |
| **3. Ephemeral JIT Lease** | CLI scripts / local automated runners | Maintainer-issued 1-hour lease tokens via the MCP Control Tower admin surface (no `credential_manager.py` exists in-repo); master keys never leave the vault (Rule U6). |

*U10 Rule: The loop is the permission. Never ask "should I proceed" when self-checkable preconditions pass.*

---

## 3. Role Preflight Invariants (৩-সেকেন্ড আত্ম-জিজ্ঞাসা)

যেকোনো কোড বা অ্যাকশনের পূর্বে প্রতিটি রোলের ৩-সেকেন্ড প্রি-ফ্লাইট চেক:
- **Planner:** বিদ্যমান কোডে ৮০% আছে কি? নতুন জটিলতা ছাড়া কি পুরনো কোড রিইউজ করা যায়? (রুল §6)
- **Coder:** ইস্যু কি লাইভ `main`-এ সক্রিয়? ইস্যুতে সাজেস্ট করার চেয়ে সহজ ১-লাইনের সেরা কোনো বিকল্প আছে কি?
- **Auditor:** নিয়মলঙ্ঘন কি বর্তমান `main`-এ প্রমাণযোগ্য? এটি চিরতরে বন্ধে স্বয়ংক্রিয় সিআই গেট কী দেওয়া হচ্ছে?
- **CI Fixer:** রুট-কজ ঠিক হচ্ছে নাকি স্কিপ হ্যাক? লিনাক্স/উইন্ডোজ/ম্যাকে পোর্টেবল এবং < 5s ফাস্ট-পাথ সুরক্ষিত তো?
- **Human Eye:** এডমিন শ্রম ≤ ০.০১% অক্ষত তো? ওয়ান-টাইম ফিক্স না করে সিস্টেমে স্থায়ী নিয়ম শেখানো হচ্ছে কি?
- **3rd Party Platforms:** মাস্টার-কি সম্পূর্ণ আইসোলেটেড তো? সার্ভার স্লিপ হলেও কোল্ড-স্টার্ট রিট্রাই আছে তো?

---

## 4. Universal Boundaries & Core Philosophy

### Agent Freedom vs Hard Boundaries
- **Agent decides:** Implementation inside declared scope, testing, smallest safe approach, evidence-backed optimizations.
- **Agent may NOT decide alone:** Major architecture changes, permission/boundary alterations, destructive ops, wide scope expansion (requires `ADMIN_DECISION` issue).
- **Hard Ordering:** **No Claim → No Branch** (zero-credential `work_claim` tool or `<!-- atomic-claim -->` comment plane first; no `atomic_claim.sh` exists in-repo) · **No Branch → No Push** (pre-push gate) · **Board Freshness Re-check (#4177)** before declaring done.

### Core Philosophy (The Law of Minimal Elegance — সব এজেন্টের মূলমন্ত্র)
- **Zero Over-Engineering:** কোনো ওভার-ইঞ্জিনিয়ারিং নয় — যেকোনো সমাধানকে কতটুকু সহজ অথচ চূড়ান্ত শক্তিশালী (Simple yet Powerful) করা যায়, সেটাই প্রতিটি এজেন্টের প্রথম এবং প্রধান লক্ষ্য।
- **Token & Context Efficiency:** ৭২৮ লাইনের কথা যদি মারমেইড গ্রাফ ও পাঞ্চি চেকলিস্টে ৮৮ লাইনে (৭০-৮০% রিডাকশন) প্রকাশ করা যায় যার কার্যকারিতা ১% কমবে না বরং টোকেন ও ক্ল্যারিটি বাঁচাবে—সেটাই হলো সুপ্রিমএআই স্ট্যান্ডার্ড।
- **Simple + effective > clever + complex.**
- **Existing work before new work.** (80% reuse rule; ১৭ লাইনে ৫টি রিপোর সমন্বয় প্রমাণ করেছে মিনিমালিজমের শক্তি)
- **Complexity must earn its existence.**
- **Issue validity before implementation.** (Never fix a ghost issue)
- **Evidence before action.** (Claims without proof are rejected)
- **System guards enforce boundaries; agents do not police themselves.**

---

## 5. Navigation Circle & Machine Enforcement

```text
Entry (AGENTS.md) → Rules (AGENT_RULES.md) → Task/Issue → Group/Domain → Verify Evidence → Landing
```

- **Canonical Check:** `python scripts/ci/issue_template_guard.py --self-test`
- **Board SSOT:** [`docs/FEDERATION_CHARTER.md`](./docs/FEDERATION_CHARTER.md) (#626) — one public task board; satellites hold 0 open issues/PRs. Audit: `python3 scripts/ci/satellite_board_guard.py --check`
- **Next:** Read [`AGENT_RULES.md`](./AGENT_RULES.md) for detailed role policies and gate definitions.
