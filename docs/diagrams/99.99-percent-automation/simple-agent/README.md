# Simple Agent System (lean)

সহজ অংশগুলো (keep): single door (MCP Tower), একক কমান্ড লুপ, মেকানিক্যাল গার্ড, সেলফ-হিলিং।
বাদ দিন (drop): ৭-স্যাটেলাইট রোলিং-ট্রেইন, মনোরেপো কনসোলিডেশন, আর্কাইভ/রিটায়ারমেন্ট ফ্লো।

Files: `MASTER.md`, `LOOP.md`, `GUARDS.md`.
---
## MASTER.md
```mermaid
flowchart LR
    A[Agent] --> T[MCP Tower (single door)]
    T --> L[continuous_agent_loop.py]
    L --> D{board scan + cadence}
    D -->|issue exists & cadence ok| P[pick top P0 issue]
    D -->|cadence over or no issue| R[specialized role]
    P --> X[coder: claim→fix→verify→submit]
    R --> X
    X --> G[4-tier guards]
    G -->|pass| PR[Tower auto-PR]
    G -->|fail| I[auto P0 fix issue]
    PR --> LAND[land + deploy]
    LAND --> CLEAN[prune transit]
    I --> L
```

## LOOP.md
```mermaid
flowchart TD
    L[loop] --> S[scan board]
    S --> C{cadence timer over?}
    C -- yes --> ROLE[dispatch role]
    C -- no --> E{claimable issue?}
    E -- yes --> TOP[pick top priority]
    E -- no --> ROLE
    TOP --> PAYLOAD[JSON payload: issue+rules+scope]
    ROLE --> PAYLOAD
    PAYLOAD --> AGENT[agent executes]
```

## GUARDS.md
```mermaid
flowchart TD
    A[attempt change] --> T1[1. AGENTS.md rules]
    T1 --> T2[2. pre-commit hooks]
    T2 --> T3[3. Tower CAS gate]
    T3 --> T4[4. remote CI]
    T4 -->|all pass| OK[land + deploy]
    T4 -->|any fail| FAIL[fail-closed + auto P0 issue]
```
